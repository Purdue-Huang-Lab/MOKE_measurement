"""
Thorlabs DDS300 delay stage, driven via a Thorlabs BBD301 benchtop brushless
motor controller.

Wraps Thorlabs.MotionControl.Benchtop.BrushlessMotor.dll via ctypes. Function
signatures and unit conventions below were checked against
Thorlabs.MotionControl.Benchtop.BrushlessMotor.h (Kinesis SDK C header), not
guessed. So far this only targets a single-channel DDS300; extending to a
multi-channel benchtop rack would mean threading `channel` through the public
API instead of hardcoding `_CHANNEL = 1`.

Origin: adapted from optical_devices_toolbox (t_bbd_ds.py), Hanjun, Purdue
University, 2025.
"""

import os
import sys
import time
import logging
import ctypes as ct

from moke.devices.base import Device

_log = logging.getLogger(__name__)

DEFAULT_SN = "103507474"  # debug-only default serial number
_CHANNEL = 1  # this driver assumes the DDS300 is wired to channel 1

C_M_S = 299792458  # speed of light, m/s
DEFAULT_N_TRIP = 4  # number of passes the beam makes across the delay stage

# DDS300: 300 mm travel over 6,000,000 encoder counts.
STEPS_PER_MM = 20000
CONVERSION_MM_PER_STEP = 1 / STEPS_PER_MM

DEFAULT_VELOCITY_MM_S = 100.0

# Kinesis DLLs must be discoverable either via PATH or an explicit DLL directory.
_KINESIS_DIR = r"C:\Program Files\Thorlabs\Kinesis"
if sys.version_info < (3, 8):
    os.chdir(_KINESIS_DIR)
else:
    os.add_dll_directory(_KINESIS_DIR)
_lib: ct.CDLL = ct.cdll.LoadLibrary("Thorlabs.MotionControl.Benchtop.BrushlessMotor.dll")

# BMC_GetStatusBits returns a DWORD; ctypes' default c_int restype would read
# bit 31 (0x80000000, "channel enabled") as a sign bit and turn the whole
# value negative, breaking any bitmask check against it.
_lib.BMC_GetStatusBits.restype = ct.c_uint32

# Status-bit masks (Thorlabs.MotionControl.Benchtop.BrushlessMotor.h, BMC_GetStatusBits).
_STATUS_MOVING_CW = 0x00000010
_STATUS_MOVING_CCW = 0x00000020
_STATUS_MOVING_MASK = _STATUS_MOVING_CW | _STATUS_MOVING_CCW


class DelayStage(Device):
    """
    High-level driver for a Thorlabs DDS300 delay stage on a BBD301
    controller.

    Usage::

        stage = DelayStage("103507474")
        stage.open()
        stage.move_to_mm(50.0)
        stage.close()

    Or as a context manager::

        with DelayStage("103507474") as stage:
            stage.move_to_ps(120.0)
    """

    def __init__(self, sn: str = DEFAULT_SN, n_trip: int = DEFAULT_N_TRIP, timeout_s: float = 30.0):
        """
        Parameters
        ----------
        sn:
            Serial number of the BBD301 controller, as a string.
        n_trip:
            Number of times the beam crosses the stage per unit stage travel
            (a double-pass retroreflector arrangement is `n_trip=4`). Sets
            the mm <-> ps conversion via `move_to_ps`/`move_rel_ps`.
        timeout_s:
            Upper bound on how long a single move is allowed to block while
            polling for motion-complete, in seconds.
        """
        self._sn = ct.c_char_p(sn.encode())
        self.n_trip = n_trip
        self._timeout_s = timeout_s
        self._is_open = False
        self._needs_homing = None
        self._velocity_mm_s = DEFAULT_VELOCITY_MM_S
        self._pos_mm = None
        self._min_mm = None
        self._max_mm = None

    # ------------------------------------------------------------------
    # 1. Device lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """
        Connect to the controller and read back its live state.

        Does **not** home the device -- see `home()`.

        Raises
        ------
        RuntimeError
            If the controller fails to open, the channel is invalid, or the
            channel fails to enable.

        Notes
        -----
        Travel limits are read via `BMC_GetStageAxisMinPos`/`MaxPos`
        (device units), not `BMC_GetMotorTravelLimits` -- the latter is
        documented as "maintained for user info only" and does not track
        the stage's actual working range, and it already returns real-world
        units, which would silently double-convert if run back through
        `_dev_to_mm`.
        """
        _log.debug("Opening delay stage %s", self._sn.value)
        _lib.TLI_BuildDeviceList()  # must precede BMC_Open, else device list size is 0

        if _lib.BMC_Open(self._sn) != 0:
            raise RuntimeError(f"BMC_Open failed for delay stage '{self._sn.value}'")
        self._is_open = True

        if not _lib.BMC_IsChannelValid(self._sn, _CHANNEL):
            self.close()
            raise RuntimeError(f"Channel {_CHANNEL} is not valid on delay stage '{self._sn.value}'")

        if _lib.BMC_EnableChannel(self._sn, _CHANNEL) != 0:
            self.close()
            raise RuntimeError(f"BMC_EnableChannel failed for delay stage '{self._sn.value}'")
        time.sleep(1)  # channel enable takes a moment to settle before polling/moves are reliable

        _lib.BMC_StartPolling(self._sn, _CHANNEL, ct.c_int(100))  # ms
        time.sleep(0.2)  # let the first polled position/status arrive

        min_dev = _lib.BMC_GetStageAxisMinPos(self._sn, _CHANNEL)
        max_dev = _lib.BMC_GetStageAxisMaxPos(self._sn, _CHANNEL)
        self._min_mm, self._max_mm = self._dev_to_mm(min_dev), self._dev_to_mm(max_dev)

        accel_dev, vel_dev = ct.c_int(), ct.c_int()
        real_vel = ct.c_double()
        if (_lib.BMC_GetVelParams(self._sn, _CHANNEL, ct.byref(accel_dev), ct.byref(vel_dev)) == 0
                and _lib.BMC_GetRealValueFromDeviceUnit(
                    self._sn, _CHANNEL, vel_dev, ct.byref(real_vel), 1) == 0):  # unitType 1 = velocity
            self._velocity_mm_s = real_vel.value
        else:
            _log.warning(
                "Could not read velocity from delay stage %s; assuming default v=%.1f mm/s",
                self._sn.value, self._velocity_mm_s,
            )

        # Re-homing can leave the stage further from a previously-useful
        # position than just continuing un-homed, so -- as with the K-cube --
        # this is surfaced as a status flag only and never triggered here.
        self._needs_homing = _lib.BMC_CanMoveWithoutHomingFirst(self._sn, _CHANNEL) == 0
        if self._needs_homing:
            _log.warning(
                "Delay stage %s reports homing needed; not homing automatically -- "
                "call home() explicitly if required.", self._sn.value,
            )

        self._pos_mm = self.get_position_mm()
        _log.info(
            "Delay stage %s opened (range=[%.3f, %.3f] mm, v=%.2f mm/s, pos=%.3f mm, "
            "needs_homing=%s)",
            self._sn.value, self._min_mm, self._max_mm, self._velocity_mm_s,
            self._pos_mm, self._needs_homing,
        )

    def close(self) -> None:
        """Stop polling and release the connection. Safe to call twice."""
        if not self._is_open:
            _log.debug("close() called but delay stage %s was not open", self._sn.value)
            return
        _lib.BMC_StopPolling(self._sn, _CHANNEL)
        _lib.BMC_Close(self._sn)
        self._is_open = False
        _log.info("Delay stage %s closed", self._sn.value)

    def status(self) -> dict:
        """Return open flag, cached position, velocity, and homing flag."""
        return {
            "open": self._is_open,
            "position_mm": self._pos_mm,
            "velocity_mm_s": self._velocity_mm_s,
            "needs_homing": self._needs_homing,
        }

    # ------------------------------------------------------------------
    # 2. Helpers
    # ------------------------------------------------------------------

    def _require_open(self, caller: str = "") -> None:
        if not self._is_open:
            raise RuntimeError(f"{caller}: delay stage is not open — call open() first")

    @staticmethod
    def _dev_to_mm(dev_pos: int) -> float:
        return float(dev_pos) * CONVERSION_MM_PER_STEP

    @staticmethod
    def _mm_to_dev(pos_mm: float) -> int:
        return int(round(pos_mm / CONVERSION_MM_PER_STEP))

    def _mm_to_ps(self, d_mm: float) -> float:
        """
        Convert a stage travel distance to the optical delay it produces.

        Notes
        -----
        `n_trip` counts how many times the beam crosses the moving stage
        (e.g. 4 for a double-pass retroreflector arrangement); the delay
        scales with total path length, not stage travel alone.
        """
        return self.n_trip * d_mm / C_M_S * 1e9  # mm / (m/s) * 1e9 = ps

    def _ps_to_mm(self, delay_ps: float) -> float:
        """Inverse of `_mm_to_ps` -- see its Notes for the `n_trip` factor."""
        return delay_ps * C_M_S / self.n_trip * 1e-9

    def _wait_move_complete(self, timeout_s: float) -> None:
        """
        Poll `BMC_GetStatusBits` until the "shaft moving" bits clear.

        Parameters
        ----------
        timeout_s:
            Upper bound on polling time, in seconds.

        Notes
        -----
        Bounded and polls the device's own motion-complete state rather than
        sleeping a fixed estimate, per the BBD301 status-bit map (bits
        0x10/0x20 = CW/CCW shaft moving). If the timeout elapses first this
        logs a warning and returns rather than raising, since the caller
        still re-reads and validates the actual position afterwards.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            status = _lib.BMC_GetStatusBits(self._sn, _CHANNEL)
            if not (status & _STATUS_MOVING_MASK):
                return
            time.sleep(0.05)
        _log.warning("Delay stage %s move did not settle within %.1f s", self._sn.value, timeout_s)

    # ------------------------------------------------------------------
    # 3. Motion
    # ------------------------------------------------------------------

    def home(self) -> None:
        """
        Start homing.

        Raises
        ------
        RuntimeError
            If `BMC_Home` fails to start.

        Notes
        -----
        Homing runs asynchronously on the device -- this call only starts
        it; read `get_position_mm()` again once it has settled. Never
        called automatically from `open()`, matching `KCube.home()`.
        """
        self._require_open("home")
        if _lib.BMC_Home(self._sn, _CHANNEL) != 0:
            raise RuntimeError("Delay stage homing failed to start")
        _log.info(
            "Delay stage %s homing started — call get_position_mm() once settled",
            self._sn.value,
        )

    def get_position_mm(self) -> float:
        """
        Read the current position.

        Returns
        -------
        float
            Position in millimeters.

        Notes
        -----
        `BMC_RequestPosition` is called explicitly (rather than relying on
        the polling loop started in `open()`) so this returns a fresh value
        immediately instead of whatever the last ~100 ms poll cycle cached.
        """
        self._require_open("get_position_mm")
        _lib.BMC_RequestPosition(self._sn, _CHANNEL)
        time.sleep(0.1)  # let the request/response round-trip complete
        dev_pos = _lib.BMC_GetPosition(self._sn, _CHANNEL)
        self._pos_mm = self._dev_to_mm(dev_pos)
        return self._pos_mm

    def move_to_mm(self, pos_mm: float) -> None:
        """
        Move to an absolute position.

        Parameters
        ----------
        pos_mm:
            Target position in millimeters.

        Raises
        ------
        ValueError
            If `pos_mm` is outside the stage's travel range.
        RuntimeError
            If the controller rejects the move command.

        Notes
        -----
        This is the root move function -- `move_to_ps`, `move_rel_mm`, and
        `move_rel_ps` all funnel through it.
        """
        self._require_open("move_to_mm")
        if not (self._min_mm <= pos_mm <= self._max_mm):
            raise ValueError(
                f"Target position {pos_mm} mm is outside travel range "
                f"[{self._min_mm}, {self._max_mm}] mm."
            )

        dev_target = self._mm_to_dev(pos_mm)
        if _lib.BMC_SetMoveAbsolutePosition(self._sn, _CHANNEL, ct.c_int(dev_target)) != 0:
            raise RuntimeError(f"Delay stage move_to_mm({pos_mm}) failed to set target")
        if _lib.BMC_MoveAbsolute(self._sn, _CHANNEL) != 0:
            raise RuntimeError(f"Delay stage move_to_mm({pos_mm}) failed to start")

        t_est_s = abs(self._pos_mm - pos_mm) / self._velocity_mm_s + 2.0
        self._wait_move_complete(min(t_est_s, self._timeout_s))
        self.get_position_mm()
        if abs(self._pos_mm - pos_mm) > 0.01:
            _log.warning(
                "Delay stage %s failed to reach %.4f mm; actual position %.4f mm",
                self._sn.value, pos_mm, self._pos_mm,
            )

    def move_to_ps(self, delay_ps: float) -> None:
        """Move to an absolute optical delay. See `move_to_mm` and `_ps_to_mm`."""
        self.move_to_mm(self._ps_to_mm(delay_ps))

    def move_rel_mm(self, d_mm: float) -> None:
        """Move by a relative distance. See `move_to_mm`."""
        self._require_open("move_rel_mm")
        self.move_to_mm(self.get_position_mm() + d_mm)

    def move_rel_ps(self, delay_ps: float) -> None:
        """Move by a relative optical delay. See `move_rel_mm` and `_ps_to_mm`."""
        self.move_rel_mm(self._ps_to_mm(delay_ps))


if __name__ == "__main__":
    print("This module is intended to be imported, not run directly.")
