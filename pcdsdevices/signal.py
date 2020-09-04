"""
Module to define ophyd Signal subclass utilities.
"""
# Catch semi-frequent issue with scripts accidentally run from inside module
if __name__ != 'pcdsdevices.signal':
    raise RuntimeError('A script tried to import pcdsdevices.signal '
                       'instead of the signal built-in module. This '
                       'usually happens when a script is run from '
                       'inside the pcdsdevices directory and can cause '
                       'extremely confusing bugs. Please run your script '
                       'elsewhere for better results.')
import logging
import typing
from threading import RLock, Thread

import numpy as np
from ophyd.signal import (DerivedSignal, EpicsSignal, EpicsSignalBase,
                          EpicsSignalRO, Signal, SignalRO)
from ophyd.sim import FakeEpicsSignal, FakeEpicsSignalRO, fake_device_cache
from pytmc.pragmas import normalize_io

from .utils import convert_unit

logger = logging.getLogger(__name__)


class PytmcSignal(EpicsSignalBase):
    """
    Class for a connection to a pytmc-generated EPICS record.

    This uses the same args as the pragma, so you can refer to the pytmc
    pragmas to select args for your components. This will automatically append
    the '_RBV' suffix and wrap the read/write PVs into the same signal object
    as appropriate, and pick between a read-only signal and a writable one.

    Under the hood this actually gives you the RW or RO version of the signal
    depending on your io argument.
    """

    def __new__(cls, prefix, io=None, **kwargs):
        new_cls = select_pytmc_class(io=io, prefix=prefix,
                                     write_cls=PytmcSignalRW,
                                     read_only_cls=PytmcSignalRO)
        return super().__new__(new_cls)

    def __init__(self, prefix, *, io, **kwargs):
        self.pytmc_pv = prefix
        self.pytmc_io = io
        super().__init__(prefix + '_RBV', **kwargs)


def select_pytmc_class(io=None, *, prefix, write_cls, read_only_cls):
    """Return the class to use for PytmcSignal's constructor."""
    if io is None:
        # Provide a better error here than "__new__ missing an arg"
        raise ValueError('Must provide an "io" argument to PytmcSignal. '
                         f'This is missing for signal with pv {prefix}. '
                         'Feel free to copy the io field from the '
                         'pytmc pragma.')
    if pytmc_writable(io):
        return write_cls
    else:
        return read_only_cls


def pytmc_writable(io):
    """Returns `True` if the pytmc io arg represents a writable PV."""
    norm = normalize_io(io)
    if norm == 'output':
        return True
    elif norm == 'input':
        return False
    else:
        # Should never get here unless pytmc's API changes
        raise ValueError(f'Invalid io specifier {io}')


class PytmcSignalRW(PytmcSignal, EpicsSignal):
    """Read-write connection to a pytmc-generated EPICS record."""
    def __init__(self, prefix, **kwargs):
        super().__init__(prefix, write_pv=prefix, **kwargs)


class PytmcSignalRO(PytmcSignal, EpicsSignalRO):
    """Read-only connection to a pytmc-generated EPICS record."""
    pass


# Make sure an acceptable fake class is set for PytmcSignal
class FakePytmcSignal(FakeEpicsSignal):
    """A suitable fake class for PytmcSignal."""
    def __new__(cls, prefix, io=None, **kwargs):
        new_cls = select_pytmc_class(io=io, prefix=prefix,
                                     write_cls=FakePytmcSignalRW,
                                     read_only_cls=FakePytmcSignalRO)
        return super().__new__(new_cls)

    def __init__(self, prefix, io=None, **kwargs):
        super().__init__(prefix + '_RBV', **kwargs)


class FakePytmcSignalRW(FakePytmcSignal, FakeEpicsSignal):
    def __init__(self, prefix, **kwargs):
        super().__init__(prefix, write_pv=prefix, **kwargs)


class FakePytmcSignalRO(FakePytmcSignal, FakeEpicsSignalRO):
    pass


# NOTE: This is an *on-import* update of the ophyd "fake" device cache
fake_device_cache[PytmcSignal] = FakePytmcSignal


class AggregateSignal(Signal):
    """
    Signal that is composed of a number of other signals.

    This class exists to handle the group subscriptions without repeatedly
    getting the values of all the subsignals at all times.

    Attributes
    ----------
    _cache : dict
        Mapping from signal to last known value.

    _sub_signals : list
        Signals that contribute to this signal.
    """

    _update_only_on_change = True

    def __init__(self, *, name, **kwargs):
        super().__init__(name=name, **kwargs)
        self._cache = {}
        self._has_subscribed = False
        self._lock = RLock()
        self._sub_signals = []

    def _calc_readback(self):
        """
        Override this with a calculation to find the current state given the
        cached values.

        Returns
        -------
        readback
            The result of the calculation.
        """

        raise NotImplementedError('Subclasses must implement _calc_readback')

    def _insert_value(self, signal, value):
        """Update the cache with one value and recalculate."""
        with self._lock:
            self._cache[signal] = value
            self._update_state()
            return self._readback

    def _update_state(self):
        """Recalculate the state."""
        with self._lock:
            self._readback = self._calc_readback()

    def get(self, **kwargs):
        """Update all values and recalculate."""
        with self._lock:
            for signal in self._sub_signals:
                self._cache[signal] = signal.get(**kwargs)
            self._update_state()
            return self._readback

    def put(self, value, **kwargs):
        raise NotImplementedError('put should be overriden in the subclass')

    def subscribe(self, cb, event_type=None, run=True):
        """
        Set up a callback function to run at specific times.

        See the `ophyd` documentation for details.
        """

        cid = super().subscribe(cb, event_type=event_type, run=run)
        if event_type in (None, self.SUB_VALUE) and not self._has_subscribed:
            # We need to subscribe to ALL relevant signals!
            for signal in self._sub_signals:
                signal.subscribe(self._run_sub_value, run=False)
            self.get()  # Ensure we have a full cache
        return cid

    def _run_sub_value(self, *args, **kwargs):
        kwargs.pop('sub_type')
        sig = kwargs.pop('obj')
        kwargs.pop('old_value')
        value = kwargs['value']
        with self._lock:
            old_value = self._readback
            # Update just one value and assume the rest are cached
            # This allows us to run subs without EPICS gets
            value = self._insert_value(sig, value)
            if value != old_value or not self._update_only_on_change:
                self._run_subs(sub_type=self.SUB_VALUE, obj=self, value=value,
                               old_value=old_value)


class AvgSignal(Signal):
    """
    Signal that acts as a rolling average of another signal.

    This will subscribe to a signal, and fill an internal buffer with values
    from `SUB_VALUE`. It will update its own value to be the mean of the last n
    accumulated values, up to the buffer size. If we haven't filled this
    buffer, this will still report a mean value composed of all the values
    we've receieved so far.

    Warning: this means that if we only have recieved ONE value, the mean will
    just be the mean of a single value!

    Parameters
    ----------
    signal : Signal
        Any subclass of `ophyd.signal.Signal` that returns a numeric value.
        This signal will be subscribed to be `AvgSignal` to calculate the mean.

    averages : int
        The number of `SUB_VALUE` updates to include in the average. New values
        after this number is reached will begin overriding old values.
    """

    def __init__(self, signal, averages, *, name, parent=None, **kwargs):
        super().__init__(name=name, parent=parent, **kwargs)
        if isinstance(signal, str):
            signal = getattr(parent, signal)
        self.raw_sig = signal
        self._lock = RLock()
        self.averages = averages
        self._con = False
        t = Thread(target=self._init_subs, args=())
        t.start()

    def _init_subs(self):
        self.raw_sig.wait_for_connection()
        self.raw_sig.subscribe(self._update_avg)
        self._con = True

    @property
    def connected(self):
        return self._con

    @property
    def averages(self):
        """The size of the internal buffer of values to average over."""
        return self._avg

    @averages.setter
    def averages(self, avg):
        """Reinitialize an empty internal buffer of size `avg`."""
        with self._lock:
            self._avg = avg
            self.index = 0
            # Allocate uninitalized array
            self.values = np.empty(avg)
            # Fill with nan
            self.values.fill(np.nan)

    def _update_avg(self, *args, value, **kwargs):
        """Add new value to the buffer, overriding old values if needed."""
        with self._lock:
            self.values[self.index] = value
            self.index = (self.index + 1) % len(self.values)
            # This takes a mean, skipping nan values.
            self.put(np.nanmean(self.values))


class NotImplementedSignal(SignalRO):
    """Dummy signal for a not implemented feature."""

    def __init__(self, *args, **kwargs):
        kwargs.pop('value', None)
        super().__init__(value='Not implemented', **kwargs)


class InternalSignal(SignalRO):
    """
    Class Signal that stores info but should only be updated by the class.

    SignalRO can be updated with _readback, but this does not process
    callbacks. For the signal to behave normally, we need to bypass the put
    override.

    To put to one of these signals, simply call put with force=True
    """

    def put(self, value, *, timestamp=None, force=False):
        return Signal.put(self, value, timestamp=timestamp, force=force)

    def set(self, value, *, timestamp=None, force=False):
        return Signal.set(self, value, timestamp=timestamp, force=force)


class UnitConversionDerivedSignal(DerivedSignal):
    """
    A DerivedSignal which performs unit conversion.

    Custom units may be specified for the original signal, or if specified, the
    original signal's units may be retrieved upon first connection.

    Parameters
    ----------
    derived_from : Signal or str
        The signal from which this one is derived.  This may be a string
        attribute name that indicates a sibling to use.  When used in a
        ``Device``, this is then simply the attribute name of another
        ``Component``.

    derived_units : str
        The desired units to use for this signal.  These can also be referred
        to as the "user-facing" units.

    original_units : str, optional
        The units from the original signal.  If not specified, control system
        information regarding units will be retrieved upon first connection.

    user_offset : any, optional
        An optional user offset that will be *subtracted* when updating the
        original signal, and *added* when calculating the derived value.
        This offset should be supplied in ``derived_units`` and not
        ``original_units``.

        For example, if the original signal updates to a converted value of
        500 ``derived_units`` and the ``user_offset`` is set to 100, this
        ``DerivedSignal`` will show a value of 600.  When providing a new
        setpoint, the ``user_offset`` will be subtracted.

    write_access : bool, optional
        Write access may be disabled by setting this to ``False``, regardless
        of the write access of the underlying signal.

    name : str, optional
        The signal name.

    parent : Device, optional
        The parent device.  Required if ``derived_from`` is an attribute name.

    **kwargs :
        Keyword arguments are passed to the superclass.
    """

    derived_units: str
    original_units: str

    def __init__(self, derived_from, *,
                 derived_units: str,
                 original_units: typing.Optional[str] = None,
                 user_offset: typing.Optional[typing.Any] = 0,
                 **kwargs):
        self.derived_units = derived_units
        self.original_units = original_units
        self._user_offset = user_offset
        super().__init__(derived_from, **kwargs)

    def forward(self, value):
        '''Compute derived signal value -> original signal value'''
        if self.user_offset is None:
            raise ValueError(f'{self.name} must be set to a non-None value.')
        return convert_unit(value - self.user_offset,
                            self.derived_units, self.original_units)

    def inverse(self, value):
        '''Compute original signal value -> derived signal value'''
        if self.user_offset is None:
            raise ValueError(f'{self.name} must be set to a non-None value.')
        return convert_unit(value, self.original_units,
                            self.derived_units) + self.user_offset

    @property
    def user_offset(self) -> typing.Optional[typing.Any]:
        """A user-specified offset in *derived*, user-facing units."""
        return self._user_offset

    @user_offset.setter
    def user_offset(self, offset):
        self._user_offset = offset
        self._recalculate_position()

    def _recalculate_position(self):
        """
        Recalculate the derived position and send subscription updates.

        No-operation if the original signal is not connected.
        """
        if not self._derived_from.connected:
            return

        value = self._derived_from.get()
        if value is not None:
            # Note: no kwargs here; no metadata updates
            self._derived_value_callback(value)

    def _derived_metadata_callback(self, *, connected, **kwargs):
        super()._derived_metadata_callback(connected=connected, **kwargs)
        if connected and 'units' in kwargs:
            if self.original_units is None:
                self.original_units = kwargs['units']

    def describe(self):
        full_desc = super().describe()
        desc = full_desc[self.name]
        desc['units'] = self.derived_units
        # Note: this should be handled in ophyd:
        for key in ('lower_ctrl_limit', 'upper_ctrl_limit'):
            if key in desc:
                desc[key] = self.inverse(desc[key])
        return full_desc
