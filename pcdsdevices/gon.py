"""
Module for goniometers and sample stages used with them.
"""
import logging
import numpy as np
from prettytable import PrettyTable
from ophyd import Device
from ophyd import FormattedComponent as FCpt

from .epics_motor import IMS
from .interface import BaseInterface
from .pseudopos import PseudoPositioner, PseudoSingleInterface

logger = logging.getLogger(__name__)


class BaseGon(BaseInterface, Device):
    """
    Basic goniometer, as present in XPP.

    This requires eight motor PV prefixes to be passed in as keyword
    arguments, and they are all labelled accordingly.

    Parameters
    ----------
    name : str
        A name to refer to the goniometer device.

    prefix_hor : str
        The EPICS base PV of the common-horizontal motor.

    prefix_ver : str
        The EPICS base PV of the common-vertical motor.

    prefix_rot : str
        The EPICS base PV of the common-rotation motor.

    prefix_tip : str
        The EPICS base PV of the sample-stage's tip motor.

    prefix_tilt : str
        The EPICS base PV of the sample-stage's tilt motor.
    """

    hor = FCpt(IMS, '{self._prefix_hor}', kind='normal')
    ver = FCpt(IMS, '{self._prefix_ver}', kind='normal')
    rot = FCpt(IMS, '{self._prefix_rot}', kind='normal')
    tip = FCpt(IMS, '{self._prefix_tip}', kind='normal')
    tilt = FCpt(IMS, '{self._prefix_tilt}', kind='normal')

    tab_component_names = True

    def __init__(self, *, name, prefix_hor, prefix_ver, prefix_rot, prefix_tip,
                 prefix_tilt, **kwargs):
        self._prefix_hor = prefix_hor
        self._prefix_ver = prefix_ver
        self._prefix_rot = prefix_rot
        self._prefix_tip = prefix_tip
        self._prefix_tilt = prefix_tilt
        super().__init__('', name=name, **kwargs)


class GonWithDetArm(BaseGon):
    """
    Goniometer with a detector arm, as present in XCS.

    This requires eleven motor PV prefixes to be passed in as keyword
    arguments, and they are all labelled accordingly.

    Parameters
    ----------
    name : str
        A name to refer to the goniometer device.

    prefix_hor : str
        The EPICS base PV of the common-horizontal motor.

    prefix_ver : str
        The EPICS base PV of the common-vertical motor.

    prefix_rot : str
        The EPICS base PV of the common-rotation motor.

    prefix_tip : str
        The EPICS base PV of the sample-stage's tip motor.

    prefix_tilt : str
        The EPICS base PV of the sample-stage's tilt motor.

    prefix_2theta : str
        The EPICS base PV of the detector arm's 2theta rotation motor.

    prefix_dettilt : str
        The EPICS base PV of the detector stage's tilt motor.

    prefix_detver : str
        The EPICS base PV of the detector stage's vertical motor.
    """

    rot_2theta = FCpt(IMS, '{self._prefix_2theta}', kind='normal')
    det_tilt = FCpt(IMS, '{self._prefix_dettilt}', kind='normal')
    det_ver = FCpt(IMS, '{self._prefix_detver}', kind='normal')

    def __init__(self, *, name, prefix_2theta, prefix_dettilt, prefix_detver,
                 **kwargs):
        self._prefix_2theta = prefix_2theta
        self._prefix_dettilt = prefix_dettilt
        self._prefix_detver = prefix_detver
        super().__init__(name=name, **kwargs)


def Goniometer(**kwargs):
    """
    Factory function for Goniometers.

    Returns either a :class:`BaseGon` or :class:`GonWithDetArm` class,
    depending on which prefixes are given.

    This requires either eight or eleven motor PV prefixes, depending on the
    type of goniometer being used, to be passed in as keyword arguments, and
    they are all labelled accordingly.

    Parameters
    ----------
    name : str
        A name to refer to the goniometer device.

    prefix_hor : str
        The EPICS base PV of the common-horizontal motor.

    prefix_ver : str
        The EPICS base PV of the common-vertical motor.

    prefix_rot : str
        The EPICS base PV of the common-rotation motor.

    prefix_tip : str
        The EPICS base PV of the sample-stage's tip motor.

    prefix_tilt : str
        The EPICS base PV of the sample-stage's tilt motor.

    prefix_2theta : str, optional
        The EPICS base PV of the detector arm's 2theta rotation motor.

    prefix_dettilt : str, optional
        The EPICS base PV of the detector stage's tilt motor.

    prefix_detver : str, optional
        The EPICS base PV of the detector stage's vertical motor.
    """

    if all(x in kwargs for x in ['prefix_2theta', 'prefix_dettilt',
                                 'prefix_detver']):
        return GonWithDetArm(**kwargs)
    else:
        return BaseGon(**kwargs)


class XYZStage(BaseInterface, Device):
    """
    Sample XYZ stage.

    Parameters
    ----------
    name : str
        A name to refer to the device

    prefix_x : str
        The EPICS base PV of the sample-stage's x motor.

    prefix_y : str
        The EPICS base PV of the sample-stage's y motor.

    prefix_z : str
        The EPICS base PV of the sample-stage's z motor.
    """

    x = FCpt(IMS, '{self._prefix_x}', kind='normal')
    y = FCpt(IMS, '{self._prefix_y}', kind='normal')
    z = FCpt(IMS, '{self._prefix_z}', kind='normal')

    tab_component_names = True

    def __init__(self, *, name, prefix_x, prefix_y, prefix_z, **kwargs):
        self._prefix_x = prefix_x
        self._prefix_y = prefix_y
        self._prefix_z = prefix_z
        super().__init__('', name=name, **kwargs)


class SamPhi(BaseInterface, Device):
    """
    Sample Phi stage.

    Parameters
    ----------
    name : str
        A name to refer to the Sample Phi stage device.

    prefix_samz : str
        The EPICS base PV of the Sample Phi stage's z motor.

    prefix_samphi : str
        The EPICS base PV of the Sample Phi stage's phi motor.
    """

    sam_z = FCpt(IMS, '{self._prefix_samz}', kind='normal')
    sam_phi = FCpt(IMS, '{self._prefix_samphi}', kind='normal')

    tab_component_names = True

    def __init__(self, *, name, prefix_samz, prefix_samphi, **kwargs):
        self._prefix_samz = prefix_samz
        self._prefix_samphi = prefix_samphi
        super().__init__('', name=name, **kwargs)


class Kappa(BaseInterface, PseudoPositioner, Device):
    """
    Kappa stage, control the Kappa diffractometer in spherical coordinates.

    The kappa's native coordinates (eta, kappa, phi) are mechanically
    convenient, but geometrically awkward to think about. This module
    replaces the coordinates with (e_eta, e_chi, e_phi) like so:

    The radial component is generally fixed such that the sample is at
    the center of rotation, but you may think of `z` as the radial
    component (inverted because the sample is pushed into the center of the
    coordinate system, rather than out from the center.)

    Parameters
    ----------
    name : str
        A name to refer to the Kappa stage device.

    prefix_x : str, optional
        The EPICS base PV of the Kappa stage's x motor.

    prefix_y : str, optional
        The EPICS base PV of the Kappa stage's y motor.

    prefix_z : str, optional
        The EPICS base PV of the Kappa stage's z motor.

    prefix_eta : str
        The EPICS base PV of the Kappa stage's eta motor.

    prefix_kappa : str
        The EPICS base PV of the Kappa stage's kappa motor.

    prefix_phi : str
        The EPICS base PV of the Kappa stage's phi motor.

    eta_max_step : int, optional
        Maximum eta motor step, the largest move eta motor can make without
        user's confirmation. Defaults to 2.

    kappa_max_step : int, optional
        Maximum kappa motor step, the largest move kappa motor can make
        without user's confirmation. Defaults to 2.

    phi_max_step : int, optional
        Maximum phi motor step, the largest move phi motor can make without
        user's confirmation. Defaults to 2.

    kappa_ang : number, optional
        The angle of the kappa motor relative to the eta motor, in degrees.
        Defaults to 50.

    Notes
    --------
    When using the Kappa, it is most convenient to work through the pseudo
    motors:

    `kappa.e_eta`
    `kappa.e_chi`
    `kappa.e_phi`

    Which have the normal motor functionalities (`mv`, `mvr`, `wm`).

    It may be helpful to scan these pseudo motors to find the optimal position,
    but make sure the step size is small enough so that you don't have to
    confirm motion on every step.

    Move commands will block the main thread, and pressing ctrl+c will cancel
    motion.

    The x, y, and z are the sample adjustment motors used to attain center of
    rotation
    """
    x = FCpt(IMS, '{self._prefix_x}', kind='normal')
    y = FCpt(IMS, '{self._prefix_y}', kind='normal')
    z = FCpt(IMS, '{self._prefix_z}', kind='normal')

    eta = FCpt(IMS, '{self._prefix_eta}', kind='normal')
    kappa = FCpt(IMS, '{self._prefix_kappa}', kind='normal')
    phi = FCpt(IMS, '{self._prefix_phi}', kind='normal')

    e_eta = FCpt(PseudoSingleInterface, kind='normal', name='gon_kappa_e_eta')
    e_chi = FCpt(PseudoSingleInterface, kind='normal', name='gon_kappa_e_chi')
    e_phi = FCpt(PseudoSingleInterface, kind='normal', name='gon_kappa_e_phi')

    tab_component_names = True

    tab_whitelist = ['stop', 'wait', 'eta_position', 'kappa_postion',
                     'phi_position', 'e_eta_coord', 'e_chi_coord',
                     'e_phi_coord', 'k_to_e', 'e_to_k', 'mv_e_eta', 'mv_e_chi',
                     'mv_e_phi', 'check_motor_step']

    def __init__(self, *, name, prefix_x, prefix_y, prefix_z,
                 prefix_eta, prefix_kappa, prefix_phi, eta_max_step=2,
                 kappa_max_step=2, phi_max_step=2, kappa_ang=50, **kwargs):
        self._prefix_x = prefix_x
        self._prefix_y = prefix_y
        self._prefix_z = prefix_z
        self._prefix_eta = prefix_eta
        self._prefix_kappa = prefix_kappa
        self._prefix_phi = prefix_phi
        self.eta_max_step = eta_max_step
        self.kappa_max_step = kappa_max_step
        self.phi_max_step = phi_max_step
        self.kappa_ang = kappa_ang
        super().__init__('', name=name, **kwargs)

    def stop(self):
        """Stop the pseudo motors."""
        self.eta.stop()
        self.kappa.stop()
        self.phi.stop()

    def wait(self):
        """Block until the action completes."""
        self.eta.wait()
        self.kappa.wait()
        self.phi.wait()

    @property
    def eta_position(self):
        """Get the eta motor current position."""
        return self.eta.wm()

    @property
    def kappa_position(self):
        """Get the kappa motor current position."""
        return self.kap.wm()

    @property
    def phi_position(self):
        """Get the phi motor's current position."""
        return self.phi.wm()

    @property
    def e_eta_coord(self):
        """Get the azimuthal angle, an offset from eta."""
        e_eta, e_chi, e_phi = self.k_to_e()
        return e_eta

    @property
    def e_chi_coord(self):
        """Get the elevation (polar) angle, a composition of eta and kappa."""
        e_eta, e_chi, e_phi = self.k_to_e()
        return e_chi

    @property
    def e_phi_coord(self):
        """Get the sample rotation angle, an offset from phi to keep it."""
        e_eta, e_chi, e_phi = self.k_to_e()
        return e_phi

    def k_to_e(self, eta=None, kappa=None, phi=None):
        """
        Convert from native kappa coordinates to spherical coordinates.

        If a parameter is left as None, use the live value.

        Parameters
        ----------
        eta : number
            Eta motor position.
        kappa : number
            Kappa motor position.
        phi : number
            Phi motor position.

        Returns
        -------
        coordinates : tuple
            Spherical coordinates.
        """
        if not eta and eta != 0:
            eta = self.eta_position
        if not kappa and kappa != 0:
            kap = self.kappa_position
        if not phi and phi != 0:
            phi = -self.phi_position

        kappa_ang = self.kappa_ang * np.pi / 180

        delta = np.arctan(np.tan(kap * np.pi / 180 / 2.0) * np.cos(kappa_ang))
        e_eta = -eta * np.pi / 180 - delta
        e_chi = 2.0 * np.arcsin(np.sin(kap * np.pi /
                                       180 / 2.0) * np.sin(kappa_ang))
        e_phi = phi * np.pi / 180 - delta

        e_eta = e_eta * 180 / np.pi
        e_chi = e_chi * 180 / np.pi
        e_phi = e_phi * 180 / np.pi
        return e_eta, e_chi, e_phi

    def e_to_k(self, e_eta=None, e_chi=None, e_phi=None):
        """
        Convert from spherical coordinates to the native kappa coordinates.

        If a parameter is left as None, use the live value.

        Parameters
        ----------
        e_eta : number
        e_chi : number
        e_phi : number

        Returns
        -------
        coordinates : tuple
            Native kappa coordinates.
        """
        if not e_eta and e_eta != 0:
            e_eta = self.e_eta_coord
        if not e_chi and e_chi != 0:
            e_chi = self.e_chi_coord
        if not e_phi and e_phi != 0:
            e_phi = self.e_phi_coord

        kappa_ang = self.kappa_ang * np.pi / 180

        delta = np.arcsin(-np.tan(e_chi * np.pi / 180 /
                                  2.0) / np.tan(kappa_ang))
        k_eta = -(e_eta * np.pi / 180 - delta)
        k_kap = 2.0 * np.arcsin(np.sin(e_chi * np.pi /
                                       180 / 2.0) / np.sin(kappa_ang))
        k_phi = e_phi * np.pi / 180 - delta

        k_eta = k_eta * 180 / np.pi
        k_kap = k_kap * 180 / np.pi
        k_phi = -k_phi * 180 / np.pi
        return k_eta, k_kap, k_phi

    def mv_e_eta(self, value):
        """
        Change the e_eta position to value, keeping e_chi and e_phi the same.

        Parameters
        ----------
        value : number
            Position value to set e_eta to.
        """
        try:
            k_eta, k_kap, k_phi = self.e_to_k(eta=value)
            if self.check_motor_step(k_eta, k_kap, k_phi):
                logger.info("Starting now moving things!!!")
                self.eta.mv(k_eta)
                self.kappa.mv(k_kap)
                self.phi.mv(k_phi)
                self.wait()
        except KeyboardInterrupt:
            logger.info("Motion interrupted by ctrl+c")
            self.stop()

    def mv_e_chi(self, value):
        """
        Change the e_chi position to value, keeping e_eta and e_phi the same.

        Parameters
        ----------
        value : number
            Position value to set e_chi to.
        """
        try:
            if value == 0:
                value = 10e-9
            k_eta, k_kap, k_phi = self.e_to_k(chi=value)
            if self.checkMotorStep(k_eta, k_kap, k_phi):
                logger.info("Starting now moving things!!!")
                self.eta.mv(k_eta)
                self.kappa.mv(k_kap)
                self.phi.mv(k_phi)
                self.wait()
        except KeyboardInterrupt:
            logger.info("Motion interrupted by ctrl+c")
            self.stop()

    def mv_e_phi(self, value):
        """
        Change the e_phi position to value, keeping e_eta and e_phi the same.

        Parameters
        ----------
        value : number
            Position value to set the e_phi to.
        """
        try:
            k_eta, k_kap, k_phi = self.E2K(phi=value)
            if self.check_motor_step(k_eta, k_kap, k_phi):
                logger.info("Starting now moving things!!!")
                self.eta.mv(k_eta)
                self.kappa.mv(k_kap)
                self.phi.mv(k_phi)
        except KeyboardInterrupt:
            logger.info("Motion interrupted by ctrl+c")
            self.stop()

    def check_motor_step(self, eta, kappa, phi):
        """
        Check for the motor steps.

        Compare desired movement destinations with current positions. If any of
        the deltas are greater than their respective max step, ask the user for
        confirmation.

        Parameters
        ----------
        eta : number
            Desired eta destination position.
        kappa : number
            Desired kappa destination position.
        phi : number
            Desired phi destination position.

        Returns
        -------
        move_on : bool
           `True` if motor step is smaller than the respective max step and/or
           the user has confirmed yes.
        """
        eta_step = abs(eta - self.eta_position)
        kappa_step = abs(kappa - self.kappa_postion)
        phi_step = abs(phi - self.phi_position)

        is_eta_above_max = eta_step > self.eta_max_step
        is_kappa_above_max = kappa_step > self.kappa_max_step
        is_phi_above_max = phi_step > self.phi_max_step

        if is_eta_above_max or is_kappa_above_max or is_phi_above_max:
            d_str = '\nDo you really intend to do the following motions?\n'
            t = PrettyTable(['Motor', 'Current position', 'to',
                             'Target position'])
            if is_eta_above_max:
                t.add_row(['eta', 5, '-->', eta])
            if is_kappa_above_max:
                t.add_row(['kappa', 6, '-->', kappa])
            if is_phi_above_max:
                t.add_row(['phi', 7, '-->', phi])
            logger.info(d_str, t)

            if input('  (y/n) ') == 'y':
                move_on = True
            else:
                move_on = False
        else:
            move_on = True
        return move_on
