"""
Thorlabs K-Cube (KDC101) DC servo driver.

Wraps Thorlabs.MotionControl.KCube.DCServo.dll via ctypes. Written with the
PRM1-Z8 rotation mount in mind; re-derive STEPS_PER_DEG / VELOCITY_STEPS_PER_DEG_S
/ ACCEL_STEPS_PER_DEG_S2 from the Kinesis communication protocol doc for any
other mount.

Origin: adapted from optical_devices_toolbox (t_kcube.py), Hanjun, Purdue
University, 2025.
"""

import os
import sys
import time
import logging
import ctypes as ct

from moke.devices.base import Device

_log = logging.getLogger(__name__)

DEFAULT_SN = "27600911"  # debug-only default serial number

# --- Device-unit <-> real-unit (deg, deg/s, deg/s^2) conversion factors ---
# The upstream comment called STEPS_PER_DEG "steps per revolution", but the
# conversion divides raw device counts by it to get degrees directly -- so
# despite the name, this is steps-per-degree on the PRM1-Z8. Flagged here so
# it doesn't look like a fresh bug to the next reader.
STEPS_PER_DEG = 1919.64186
VELOCITY_STEPS_PER_DEG_S = 42941.66
ACCEL_STEPS_PER_DEG_S2 = 14.66

DEFAULT_VELOCITY_DEG_S = 10.0
DEFAULT_ACCEL_DEG_S2 = 10.0

# Kinesis DLLs must be discoverable either via PATH or an explicit DLL directory.
_KINESIS_DIR = r"C:\Program Files\Thorlabs\Kinesis"
if sys.version_info < (3, 8):
    os.chdir(_KINESIS_DIR)
else:
    os.add_dll_directory(_KINESIS_DIR)
_lib: ct.CDLL = ct.cdll.LoadLibrary("Thorlabs.MotionControl.KCube.DCServo.dll")


class KCube(Device):
    """
    High-level driver for a Thorlabs K-Cube (KDC101) DC servo.

    In this rig, a K-cube drives the probe azimuth half-wave plate (see
    `HalfWavePlate` below) -- placed in the common path between the
    beamsplitter and the objective, so a double pass makes any static offset
    from the plate's own angle self-cancelling on return (plan doc §2).

    Usage::

        cube = KCube("27600911")
        cube.open()
        cube.move_to_deg(45.0)
        cube.close()

    Or as a context manager::

        with KCube("27600911") as cube:
            cube.move_to_deg(45.0)
    """

    def __init__(self, sn: str = DEFAULT_SN, timeout_s: float = 60.0):
        """
        Parameters
        ----------
        sn:
            Serial number of the K-cube, as a string (e.g. ``"27600911"``).
        timeout_s:
            Upper bound on how long a single relative move is allowed to
            block in `move_rel_deg`, in seconds.
        """
        self._sn = ct.c_char_p(sn.encode())
        self._timeout_s = timeout_s
        self._is_open = False
        self._needs_homing = None
        self.comment = ""  # free-form note field; subclasses may set it
        self._velocity_deg_s = DEFAULT_VELOCITY_DEG_S
        self._accel_deg_s2 = DEFAULT_ACCEL_DEG_S2
        self._pos_deg = None

    # ------------------------------------------------------------------
    # 1. Device lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """
        Connect to the K-cube and read back its live state.

        Does **not** home the device -- see `home()`.

        Raises
        ------
        RuntimeError
            If `CC_Open` fails to produce a usable connection.

        Notes
        -----
        `CC_GetVelParams` is read back here rather than assumed, because
        nothing in this driver ever calls `CC_SetVelParams` (an earlier
        `set_velocity()` wrapper existed but did not reliably write to the
        hardware and was removed). If velocity were assumed instead of read
        back, `move_rel_deg`'s wait-time estimate would be timed against a
        number the device was never told to use.
        """
        _log.debug("Opening K-cube %s", self._sn.value)
        _lib.TLI_BuildDeviceList()   # must precede CC_Open, else device list size is 0
        time.sleep(0.1)              # let the device list populate

        if _lib.CC_Open(self._sn) != 0:
            raise RuntimeError(f"CC_Open failed for K-cube '{self._sn.value}'")
        self._is_open = True
        _lib.CC_StartPolling(self._sn, ct.c_int(200))  # ms

        steps_per_rev = ct.c_double(STEPS_PER_DEG)
        gbox_ratio = ct.c_double(1.0)
        pitch = ct.c_double(1.0)
        _lib.CC_SetMotorParamsExt(self._sn, steps_per_rev, gbox_ratio, pitch)

        accel_dev, vel_dev = ct.c_int(), ct.c_int()
        if _lib.CC_GetVelParams(self._sn, ct.byref(accel_dev), ct.byref(vel_dev)) == 0:
            self._velocity_deg_s = vel_dev.value / VELOCITY_STEPS_PER_DEG_S
            self._accel_deg_s2 = accel_dev.value / ACCEL_STEPS_PER_DEG_S2
        else:
            _log.warning(
                "Could not read velocity from K-cube %s; assuming default "
                "v=%.1f deg/s, a=%.1f deg/s^2",
                self._sn.value, self._velocity_deg_s, self._accel_deg_s2,
            )

        # Homing can move the mount off a previously-set angle, and this rig
        # has found it tracks the desired angle *better* before a re-home
        # than after -- so homing is surfaced as a status flag only, and is
        # never triggered automatically. Call home() explicitly if needed.
        self._needs_homing = _lib.CC_CanMoveWithoutHomingFirst(self._sn) == 0
        if self._needs_homing:
            _log.warning(
                "K-cube %s reports homing needed; not homing automatically -- "
                "call home() explicitly if required.", self._sn.value,
            )

        self._pos_deg = self.get_position_deg()
        _log.info(
            "K-cube %s opened (v=%.2f deg/s, a=%.2f deg/s^2, pos=%.3f deg, "
            "needs_homing=%s)",
            self._sn.value, self._velocity_deg_s, self._accel_deg_s2,
            self._pos_deg, self._needs_homing,
        )

    def close(self) -> None:
        """Stop polling and release the connection. Safe to call twice."""
        if not self._is_open:
            _log.debug("close() called but K-cube %s was not open", self._sn.value)
            return
        _lib.CC_StopPolling(self._sn)
        _lib.CC_Close(self._sn)
        self._is_open = False
        _log.info("K-cube %s closed", self._sn.value)

    def status(self) -> dict:
        """Return open flag, cached position, velocity, and homing flag."""
        return {
            "open": self._is_open,
            "position_deg": self._pos_deg,
            "velocity_deg_s": self._velocity_deg_s,
            "needs_homing": self._needs_homing,
        }

    # ------------------------------------------------------------------
    # 2. Helpers
    # ------------------------------------------------------------------

    def _require_open(self, caller: str = "") -> None:
        if not self._is_open:
            raise RuntimeError(f"{caller}: K-cube is not open — call open() first")

    @staticmethod
    def _dev_to_deg(dev_pos: int) -> float:
        return float(dev_pos / STEPS_PER_DEG)

    @staticmethod
    def _deg_to_dev(pos_deg: float) -> int:
        return int(pos_deg * STEPS_PER_DEG)

    # ------------------------------------------------------------------
    # 3. Motion
    # ------------------------------------------------------------------

    def home(self) -> None:
        """
        Start homing.

        Raises
        ------
        RuntimeError
            If `CC_Home` fails to start.

        Notes
        -----
        Homing runs asynchronously on the device -- this call only starts
        it; read `get_position_deg()` again once it has settled. Deliberately
        never called from `open()`: re-homing can move the mount off a
        previously-set angle, which is worse for this rig than occasionally
        running un-homed, so homing stays an explicit, operator-initiated
        action.
        """
        self._require_open("home")
        if _lib.CC_Home(self._sn) != 0:
            raise RuntimeError("K-cube homing failed to start")
        _log.info(
            "K-cube %s homing started — call get_position_deg() once settled",
            self._sn.value,
        )

    def get_position_deg(self) -> float:
        """
        Read the current position.

        Returns
        -------
        float
            Position in degrees, per the device's internal encoder count
            (not wrapped to [0, 360)).
        """
        self._require_open("get_position_deg")
        dev_pos = _lib.CC_GetPosition(self._sn)
        time.sleep(0.2)  # let a just-issued move register before trusting the read
        self._pos_deg = self._dev_to_deg(dev_pos)
        return self._pos_deg

    def move_rel_deg(self, d_deg: float) -> None:
        """
        Move by the shortest path to a relative displacement.

        Parameters
        ----------
        d_deg:
            Requested relative displacement, in degrees. Any value is
            accepted -- it's reduced mod 360 and folded to the shorter
            direction, i.e. wrapped into (-180, 180], before being sent to
            the device.

        Raises
        ------
        RuntimeError
            If the device rejects the move command.

        Notes
        -----
        There's no move-complete event wired up here, so completion is a
        sleep against an estimate: `abs(wrapped) / velocity_deg_s + 2s`,
        capped at `timeout_s`. `velocity_deg_s` comes from the device itself
        (read back in `open()`), not an assumed constant.
        """
        self._require_open("move_rel_deg")
        wrapped_deg = float(d_deg % 360)
        if wrapped_deg > 180:
            wrapped_deg -= 360

        dev_displacement = ct.c_int(self._deg_to_dev(wrapped_deg))
        if _lib.CC_MoveRelative(self._sn, dev_displacement) != 0:
            raise RuntimeError(f"K-cube move_rel_deg({d_deg}) failed")

        t_est_s = min(abs(wrapped_deg) / self._velocity_deg_s + 2.0, self._timeout_s)
        time.sleep(t_est_s)
        self.get_position_deg()

    def move_to_deg(self, target_deg: float) -> None:
        """
        Move to an absolute azimuth via the shortest relative path.

        Parameters
        ----------
        target_deg:
            Target azimuth in degrees; interpreted mod 360 against the
            device's current (mod-360) position.
        """
        self._require_open("move_to_deg")
        current_deg = self.get_position_deg() % 360
        self.move_rel_deg(target_deg - current_deg)

    # Aliases kept for continuity with existing call sites (e.g. rig.py,
    # hwp_signal_aligner below).
    move = move_rel_deg
    goto = move_to_deg
    go_to = move_to_deg

    def trig(self, channel):
        """Not implemented — check for a trigger signal on `channel`."""
        raise NotImplementedError

    def oscillate_by_trig(self, channel, center_deg: float, half_amplitude_deg: float):
        """Not implemented — oscillate between center ± half_amplitude on a
        trigger signal from `channel`."""
        raise NotImplementedError


class HalfWavePlate(KCube):
    """
    K-cube driving the probe azimuth half-wave plate.

    Purely a labeled specialization of `KCube` -- see `KCube` for the full
    interface.
    """

    def __init__(self, sn: str = DEFAULT_SN, timeout_s: float = 60.0):
        super().__init__(sn, timeout_s)
        self.comment = "Thorlabs K-Cube half-wave plate"


class HwpSignalAligner:
    """
    HWP auto-aligner based on detector feedback.

    `detector` is any object with a way to produce a float-like reading; bind
    it via `setup_acquire()` before calling `minimize()`. Typical detectors:
    a Thorlabs power meter, or a photodiode behind a lock-in.
    """

    def __init__(self, hwp: HalfWavePlate, detector):
        self.hwp = hwp
        self.detector = detector
        self.acquire = None

    def setup_acquire(self, method, **kwargs) -> None:
        """
        Bind `self.acquire` to ``method(**kwargs)``, called fresh on every
        invocation.

        This is what makes `self.acquire` an abstract acquirer: `minimize()`
        just calls `self.acquire()` and doesn't need to know what device or
        method backs it.
        """
        self.acquire = lambda: method(**kwargs)

    def minimize(
        self,
        angle0_deg: float = 0.0,
        half_range_deg: float = 45.0,
        tol_deg: float = 0.1,
        timeout_s: float = 60.0,
        verbose: bool = False,
    ) -> tuple[float, float]:
        """
        Rotate the HWP to minimize the detector signal via golden-section
        search over ``[angle0_deg - half_range_deg, angle0_deg + half_range_deg]``.

        Parameters
        ----------
        angle0_deg:
            Center of the search bracket, in degrees.
        half_range_deg:
            Half-width of the initial search bracket, in degrees.
        tol_deg:
            Bracket width at which the search stops, in degrees.
        timeout_s:
            Upper bound on total search time, in seconds.
        verbose:
            If True, log bracket progress at INFO level.

        Returns
        -------
        tuple[float, float]
            ``(best_angle_deg, best_signal)``.

        Notes
        -----
        Unlike a fixed-step left/right pattern search (whose step only
        shrinks when neither side improves -- a branch that noisy
        measurements can make rare or accidental, so the search can stall at
        a fixed resolution without ever tightening down), golden-section
        search shrinks the bracket by a constant ratio (~0.618) on *every*
        iteration regardless of which side wins. That makes it structurally
        unable to cycle, and it converges to `tol_deg` within a bounded
        number of iterations (or hits `timeout_s`), using only one new
        detector reading (and one new HWP move) per iteration since the
        other probe point is always reused from the previous step.
        """
        if self.acquire is None:
            raise RuntimeError("call setup_acquire() before minimize()")

        start_time = time.time()
        invphi = (5 ** 0.5 - 1) / 2    # 1/phi  ~ 0.618
        invphi2 = (3 - 5 ** 0.5) / 2   # 1/phi^2 ~ 0.382

        def measure_at(angle_deg):
            self.hwp.move_to_deg(angle_deg)
            return self.acquire()

        a, b = angle0_deg - half_range_deg, angle0_deg + half_range_deg
        h = b - a
        c = a + invphi2 * h
        d = a + invphi * h
        yc = measure_at(c)
        yd = measure_at(d)
        if verbose:
            _log.info(
                "Starting golden-section search over [%.3f, %.3f] deg, "
                "tol %.3f deg, timeout %.1f s.", a, b, tol_deg, timeout_s,
            )

        while h > tol_deg:
            if time.time() - start_time > timeout_s:
                _log.warning("HWP alignment timed out before reaching tol_deg")
                break
            if yc < yd:
                b, d, yd = d, c, yc
                h = invphi * h
                c = a + invphi2 * h
                yc = measure_at(c)
            else:
                a, c, yc = c, d, yd
                h = invphi * h
                d = a + invphi * h
                yd = measure_at(d)
            if verbose:
                _log.info("Bracket now [%.3f, %.3f] deg (width %.4f deg), yc=%s, yd=%s.",
                           a, b, h, yc, yd)

        best_angle_deg = (a + b) / 2
        best_signal = measure_at(best_angle_deg)
        if verbose:
            _log.info("Converged to angle %.3f deg, signal %s.", best_angle_deg, best_signal)
        return best_angle_deg, best_signal


if __name__ == "__main__":
    print("This module is intended to be imported, not run directly.")
