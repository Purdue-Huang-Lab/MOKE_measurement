"""
HeliCam C3 camera driver wrapper.

Wraps the libHeLIC C library for the C3 camera system (e.g. c3cam_sl70).
"""

import ctypes as ct
import sys
import os
import logging
import numpy as np

from moke.devices.base import Device

_log = logging.getLogger(__name__)

# SDK message "param" kind, low 8 bits (see Heliotis Python example
# libHeLIC_setCallback.py). msg == 0x01 (CM_MSG_DISPLAY) is the only kind
# that carries a human-readable string in `data`.
_CM_MSG_DISPLAY = 0x01
_SDK_MSG_KIND_NAMES = {
    0x00: "DEBUG_STRING",
    0x01: "BOX_INFO",
    0x02: "BOX_WARN",
    0x03: "BOX_ERR",
}


def _sdk_message_callback(hdl, msg, param, data):
    """HE_SetCallback target: logs the SDK's human-readable message instead
    of letting it show a blocking popup (see programmer manual, "Warnings
    and error messages")."""
    kind = param & 0xFF
    text = ""
    if msg == _CM_MSG_DISPLAY and data:
        raw = ct.cast(data, ct.c_char_p).value
        text = raw.decode("utf-8", errors="replace") if raw else ""
    kind_name = _SDK_MSG_KIND_NAMES.get(kind, hex(kind))
    level = logging.WARNING if kind in (0x02, 0x03) else logging.DEBUG
    _log.log(level, "SDK message [%s]: %s", kind_name, text)
    return 0

# Prefer the local wrapper/ directory that ships with this repo; fall back to
# the SDK installation so the module works when deployed without the source tree.
_local_wrapper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wrapper")
if os.path.isdir(_local_wrapper):
    _wrapper_path = _local_wrapper
elif sys.platform == "win32":
    _wrapper_path = os.path.join(os.environ.get("PROGRAMFILES", ""), r"Heliotis\heliCam\Python\wrapper")
else:
    _wrapper_path = r"/usr/share/libhelic/python/wrapper"

if _wrapper_path not in sys.path:
    sys.path.insert(0, _wrapper_path)

from libHeLIC import LibHeLIC   


class HeliCamC3(Device):
    """
    High-level driver for the Heliotis heliCam C3.

    Usage::

        cam = HeliCamC3()
        cam.open()
        cam.set_attributes(SensTqp=540, SensNavM2=2, CamMode=4)
        # ... acquire / process ...
        cam.close()

    Or as a context manager::

        with HeliCamC3() as cam:
            cam.set_attributes(SensTqp=540, CamMode=4)
            ...
    """

    # Default map settings for the C3 in "simple max" surface mode (CamMode=4).
    # Override any of these via set_attributes() after open().
    DEFAULT_SETTINGS = {
        "SensTqp":       540,   # demodulation frequency fd = 70MHz / (8*(SensTqp+30)); e.g. fd=10kHz → SensTqp=845
        "SensNavM2":     2,     # averaging cycles per frame: Nc = SensNavM2*2+2; range 1–255
        "SensNFrames":   150,   # frames per acquisition; range 10–511 (0x1ff)
        "BSEnable":      1,     # in-pixel bias suppression (offset compensation); 1=enabled
        "DdsGain":       2,     # sensor analog DDS stage gain: 0→3x, 1→1.5x, 2→1x (best SNR), 3→0.75x
        "TrigFreeExtN":  1,     # 1=free-running (internal trigger), 0=external trigger
        "TrigExtSrcSel": 0,     # not in official register description; appears in SDK examples, always 0
        "CamMode":       4,     # 0=raw IQ, 1=amplitude, 2=smoothed amp, 3=intensity, 4=simple max, 5=ext-simple max, 7=min-energy
        "AcqStop":       0,     # 0=acquisition running, 1=stopped (power-on default is 1)
    }

    # Values below are the ones heliViewer used for a confirmed-good capture on
    # this camera (serial 1002688069) and were verified end-to-end from Python.
    # AcqStop must stay last: prepare_measurement_mode() halts acquisition
    # (AcqStop=1), writes everything else, then restarts with this AcqStop=0.
    STEADY_SETTINGS = {
        "CamMode":         3,   # intensity mode — camera behaves like a standard 2D camera
        "SensNFrames":   385,   # total frames; useful HDR output = SensNFrames - SensNDarkFrames - 3
        "SensNDarkFrames": 7,   # dark frames taken; must be >= 7 and <= SensNFrames - 4
        "SensExpTime":     1,   # short exposure time [µs]; actual = SensExpTime * (SensExpTimeMult+1)
        "SensExpTimeMult": 0,   # exposure time multiplier; actual exposure = SensExpTime * (SensExpTimeMult+1)
        "SensExpRatio":    3,   # short:long exposure ratio (register description §2.12); NOT frame-rate dead time
        "BSEnable":        0,   # must be 0 for intensity mode (manual §5.4)
        "TrigFreeExtN":    1,   # free-running for continuous steady-state capture
        "TrigExtSrcSel":   0,   # always 0 per SDK examples
        "AcqStop":         0,   # 0 = acquisition running (power-on default is 1 — must be set explicitly)
    }

    RAWIQ_SETTINGS = {
        "CamMode":       0,
    }

    AMPLITUDE_SETTINGS = {
        "CamMode":       1,
        "OffsetMethod":  0,
    }

    # --- Physical / calibration constants, used by estimate_acquire_time() ---

    SENSOR_HEIGHT = 300     # helioct3 sensor, per SysDesc.xml (size="300 300")
    SENSOR_WIDTH  = 300

    SEQUENCER_CLOCK_HZ = 35e6   # clock FrmDur35MHz / TDemodCyc35MHz are counted in

    # Sustained USB 2.0 bulk throughput, measured on camera 1002688069:
    # 36.5 MB/s, constant to within 0.3% over 100/200/385-frame acquisitions.
    # Acquisition in the volume modes is transfer-bound, so this — not the
    # sensor — sets the wall time. Retune if moved to another USB controller.
    USB_THROUGHPUT_BPS = 36.5e6

    # Fallback frame duration when the camera is closed and FrmDur35MHz cannot
    # be read: 23364 ticks / 35 MHz as configured by STEADY_SETTINGS.
    NOMINAL_FRAME_DURATION_S = 23364 / 35e6   # 667.5 us

    # Map from CamMode to the expected CamDataFmt for AllocCamData.
    #
    # NOTE on CamMode 3 (intensity): the programmer's manual documents this
    # mode as using DF_Hf (32-bit float), with the SDK itself doing the
    # dark-frame subtraction and HDR combination on-device and returning
    # SensNFrames-SensNDarkFrames-3 reduced frames. This driver instead
    # requests DF_I16Q16 (raw I/Q) and reimplements that reduction in
    # to_numpy(). That diverges from the documented path, but STEADY_SETTINGS
    # above records these exact values as verified end-to-end on real
    # hardware (serial 1002688069) -- so this is a known doc/code mismatch,
    # not yet confirmed as a bug. Don't "fix" it to DF_Hf without testing
    # against real hardware first.
    _MODE_TO_FMT = {
        0: "DF_I16Q16",   # raw IQ
        1: "DF_A16",      # amplitude volume
        3: "DF_I16Q16",   # intensity (IQ raw used, summed in post) -- see NOTE above
        4: "DF_A16Z16",   # simple max  → surface (Z) + amplitude (A)
        5: "DF_Z16A16P16",# extended simple max → Z, A, phase
        7: "DF_A16Z16",   # minimize energy
    }


    def __init__(self, sys_id: str = "c3cam_sl70", timeout_ms: int = 2000):
        """
        Parameters
        ----------
        sys_id:
            Camera system identifier string passed to HE_Open. Must match an
            entry in ``C:\\ProgramData\\Heliotis\\devDesc\\SysDesc.xml``:
            ``'c3cam_sl70'`` (current hardware), ``'c3cam'`` (older sl50),
            ``'c3cam_sl110'``, ``'c3cam_se80'``. A wrong identifier does *not*
            raise — HE_Open returns 0 and leaves the handle NULL (see open()).
        timeout_ms:
            Acquisition timeout in milliseconds (0 = no timeout).
        """
        self._sys_id = sys_id
        self._timeout_ms = timeout_ms
        self._lib = LibHeLIC()
        self._is_open = False
        # Keep a reference to the ctypes callback alive for the lifetime of
        # this object — otherwise it can be garbage-collected and leave the
        # SDK holding a dangling function pointer.
        self._sdk_cb = self._lib.funcCBType(_sdk_message_callback)
        self._lib.SetCallback(self._sdk_cb)

    # ------------------------------------------------------------------
    # 1. Device lifecycle
    # ------------------------------------------------------------------

    def open(self) -> int:
        """
        Power on / initialise the camera.

        Opens the USB connection and downloads the FPGA firmware.

        Success is determined by the **handle**, not by the return code.
        HE_Open returns a non-zero status (1) on a healthy open of this
        camera, so a ``res != 0`` test rejects working hardware. The real
        failure mode — e.g. a sys_id that does not match the attached
        camera — returns 0 and leaves the handle NULL, after logging
        "FPGA download failed" through the SDK callback.

        Returns
        -------
        int
            Raw return code from HE_Open. Informational only.

        Raises
        ------
        RuntimeError
            If HE_Open did not produce a usable handle.
        """
        _log.debug("Opening %s", self._sys_id)
        res = self._lib.Open(0, sys=self._sys_id)
        handle = getattr(self._lib.handle, "value", self._lib.handle)
        if not handle:
            raise RuntimeError(
                f"HE_Open produced a NULL handle for '{self._sys_id}' (res={res}). "
                f"The sys_id likely does not match the attached camera; valid ids "
                f"are listed in SysDesc.xml."
            )
        self._is_open = True
        self._lib.SetTimeout(self._timeout_ms)
        _log.info("Camera '%s' opened (handle=0x%x, res=%s)", self._sys_id, handle, res)
        return res

    def close(self) -> int:
        """
        Shut down the camera and release all resources.

        Returns
        -------
        int
            Return code from HE_Close (0 = success).
        """
        if not self._is_open:
            _log.warning("close() called but camera is not open")
            return 0
        _log.debug("Closing camera")
        res = self._lib.Close()
        self._is_open = False
        _log.info("Camera closed (res=%d)", res)
        return res

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------
    # 2. Attribute / map setting
    # ------------------------------------------------------------------

    def set_attributes(self, **kwargs) -> None:
        """
        Set one or more camera map attributes by name.

        Any keyword argument whose name matches a map entry in the camera's
        register descriptor is forwarded to ``HE_SetMap``.

        Parameters
        ----------
        **kwargs:
            Attribute name → integer value pairs, e.g.::

                cam.set_attributes(SensTqp=540, CamMode=4, BSEnable=1)

        Raises
        ------
        RuntimeError
            If the camera is not open.
        AttributeError
            If a map name does not exist in the camera's register descriptor.
        """
        self._require_open("set_attributes")
        for name, value in kwargs.items():
            _log.debug("set map %s = %s", name, value)
            try:
                setattr(self._lib.map, name, value)
            except AttributeError:
                raise AttributeError(f"'{name}' is not a valid map attribute for '{self._sys_id}'")

    def get_attribute(self, name: str) -> int:
        """
        Read a single camera map attribute by name.

        Parameters
        ----------
        name:
            Map attribute name, e.g. ``'SensTqp'``.

        Returns
        -------
        int
            Current value of the map attribute.
        """
        self._require_open("get_attribute")
        return getattr(self._lib.map, name)

    def apply_default_settings(self) -> None:
        """Apply DEFAULT_SETTINGS to the camera."""
        self.set_attributes(**self.DEFAULT_SETTINGS)

    def get_image_shape(self) -> tuple[int, int]:
        """
        Get the expected shape of the image returned by to_numpy().

        Returns
        -------
        tuple[int, int]
            (height, width) of the image array.
        """
        return self.SENSOR_HEIGHT, self.SENSOR_WIDTH


    # ------------------------------------------------------------------
    # 3. Helpers
    # ------------------------------------------------------------------

    def _require_open(self, caller: str = "") -> None:
        if not self._is_open:
            raise RuntimeError(
                f"{caller}: camera is not open — call open() first"
            )

    def status(self) -> dict:
        """Return open flag, sys id, and current measurement mode."""
        return {
            "open": self._is_open,
            "sys_id": self._sys_id,
            "cam_mode": getattr(self, "_current_cammode", None),
        }

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def lib(self) -> LibHeLIC:
        """Direct access to the underlying LibHeLIC instance."""
        return self._lib

    # ------------------------------------------------------------------
    # 4. Measurement
    # ------------------------------------------------------------------

    # def set_roi(self, x0: int, y0: int, width: int, height: int) -> None:
    #     # NOTE: check if it is possible.
    #     """
    #     Set the camera's region of interest (ROI).
    #
    #     Parameters
    #     ----------
    #     x0, y0:
    #         Top-left corner of the ROI in pixels. Must be within the sensor bounds.
    #     width, height:
    #         Size of the ROI in pixels. Must be positive and fit within the sensor bounds.
    #     """
    #     pass

    def set_measurement_mode(self, modedesc, **kwargs):
        """
        Helper function to prepare camera measurement mode.
        Argument:
        - modedesc: str,
            Description of the measurement mode to set.
            Allow
            "steady" / "intensity": intensity mode — camera behaves like a standard 2D camera
            "rawIQ" / "raw_iq": raw IQ mode — returns signed I/Q volume per frame
            "minimum_energy" / "minE": minimize-energy surface mode
            To-be-filled
        - **kwargs:
            Override any mode-specific setting, e.g. SensNFrames=100.
        """
        self._require_open("set_measurement_mode")

        intensity_alias = ["intensity", "steady"]
        minimum_energy_alias = ["minimum_energy", "minE"]
        rawIQ_alias = ["rawIQ", "raw_iq"]

        if modedesc in intensity_alias:
            base = dict(self.STEADY_SETTINGS)
            cam_mode = 3
        elif modedesc in minimum_energy_alias:
            base = {"CamMode": 7, "AcqStop": 0}
            cam_mode = 7
        elif modedesc in rawIQ_alias:
            base = dict(self.RAWIQ_SETTINGS)
            cam_mode = 0
        else:
            raise ValueError(f"Unsupported measurement mode: {modedesc}")

        # Halt acquisition before touching the sensor registers, then restart
        # it via the trailing AcqStop=0 in `settings` — the order heliViewer
        # uses for a known-good capture.
        self.set_attributes(AcqStop=1)
        settings = {**base, **kwargs}
        settings.setdefault("AcqStop", 0)
        self.set_attributes(**settings)

        fmt = LibHeLIC.CamDataFmt[self._MODE_TO_FMT[cam_mode]]
        self._lib.AllocCamData(1, fmt, 0, 0, 0)
        self._current_cammode = cam_mode
        _log.info("Prepared mode '%s' (CamMode=%d)", modedesc, cam_mode)

    def set_acquire_time(self, t):
        """
        Set the short-exposure time for intensity mode (CamMode=3).

        The hardware expands the 12-bit SensExpTime register with a 2-bit
        multiplier:  actual [µs] = SensExpTime × (SensExpTimeMult + 1).
        The multiplier is chosen automatically to be as small as possible.

        Parameters
        ----------
        t : float
            Target exposure in microseconds.  Range: 1 – 16380 µs.
        """
        self._require_open("set_acquire_time")
        MAX_BASE = 4095       # 12-bit register, max value
        MAX_MULT = 3          # 2-bit multiplier field, 0–3  → factor 1–4
        MAX_TOTAL = MAX_BASE * (MAX_MULT + 1)   # 16380 µs

        if t < 1:
            raise ValueError(f"Exposure time must be >= 1 µs, got {t}")
        if t > MAX_TOTAL:
            raise ValueError(
                f"Exposure time {t} µs exceeds maximum {MAX_TOTAL} µs"
            )

        for mult in range(MAX_MULT + 1):        # try 0, 1, 2, 3
            base = t / (mult + 1)
            if base <= MAX_BASE:
                self.set_attributes(
                    SensExpTime=round(base),
                    SensExpTimeMult=mult,
                )
                _log.info(
                    "Set exposure: SensExpTime=%d µs × (SensExpTimeMult=%d+1)"
                    " = %.1f µs actual",
                    round(base), mult, round(base) * (mult + 1),
                )
                return

    def set_gain(self, analogue_gain=1):
        """
        Set the gain for the camera. Note a gain = 1 is optimal for signal-noise ratio. Also note the analogue gain is different than actual code-gain.

        Parameters
        ----------
        gain:
            Gain value to set for the camera.
        """
        allowed_gain_list = [3.0, 1.5, 1, 0.75]
        DdsGain_list = [0, 1, 2, 3]
        if analogue_gain not in allowed_gain_list:
            raise ValueError(f"Invalid analogue_gain: {analogue_gain}. Allowed values are {allowed_gain_list}.")
        DdsGain = DdsGain_list[allowed_gain_list.index(analogue_gain)]
        self.set_attributes(DdsGain=DdsGain)
        _log.info("Set analogue gain to %sx (DdsGain=%d)", analogue_gain, DdsGain)

    def set_internal_demod(self, freq):
        """
        Set the internal demodulation frequency of the camera.

        Computes and writes the SensTqp register from the formula:
            SensTqp = f_sensor / (8 × fd) − 30,   f_sensor = 70 MHz

        Parameters
        ----------
        freq : float
            Demodulation frequency in Hz.  Hardware-valid range: ~2121 – 291667 Hz.
        """
        self._require_open("set_internal_demod")
        F_SENSOR = 70e6
        SensTqp = round(F_SENSOR / (8 * freq) - 30)
        if not (0 <= SensTqp <= 0xFFF):
            f_min = F_SENSOR / (8 * (0xFFF + 30))
            f_max = F_SENSOR / (8 * 30)
            raise ValueError(
                f"freq={freq:.1f} Hz → SensTqp={SensTqp} out of range [0, 4095]. "
                f"Valid range: {f_min:.0f} – {f_max:.0f} Hz"
            )
        self.set_attributes(SensTqp=SensTqp)
        _log.info("Set demodulation frequency to %.1f Hz (SensTqp=%d)", freq, SensTqp)

    def flush(self, max_frames: int = 3) -> int:
        """
        Drain stale frames from the USB buffer.

        Must be called after ``prepare_measurement_mode()`` and before the first
        real ``acquire()`` call, otherwise the first frame may contain leftover
        data from a previous session.

        The loop is bounded on purpose. In free-running mode (``TrigFreeExtN=1``)
        the camera always has another frame ready, so an unbounded
        ``while Acquire() > 0`` never terminates.

        Parameters
        ----------
        max_frames:
            Upper bound on frames to discard.

        Returns
        -------
        int
            Number of stale frames discarded.
        """
        self._require_open("flush")
        count = 0
        for _ in range(max_frames):
            if self._lib.Acquire() <= 0:
                break
            count += 1
        _log.info("Flushed %d stale frame(s) from USB buffer", count)
        return count

    def _acquire(self):
        """
        Trigger one acquisition and return the processed data as a numpy array.

        Sequence: HE_Acquire → HE_ProcessCamData(slot=1, mode=0) → HE_GetCamArr(1).

        Call ``prepare_measurement_mode()`` and ``flush()`` first to set up the
        camera mode, allocate the output buffer, and drain stale USB frames.

        Returns
        -------
        np.ndarray or None
            Raw output array from GetCamArr (uint16 dtype, shape depends on mode).
            Returns None if HE_Acquire reports no data (timeout or trigger miss).

        Notes
        -----
        HE_Acquire returns the **number of bytes transferred**, not a status
        code: a large positive value is success, ``<= 0`` is a timeout or
        missed trigger. For 385 frames of 300x300 I/Q uint16 this is
        385*300*300*2*2 + 2496 bytes of header = 138,602,496.

        For IQ-based modes (CamMode 0 and 3) the uint16 view must be reinterpreted
        as int16 before arithmetic — ``to_numpy()`` handles this automatically.
        """
        self._require_open("acquire")
        n_bytes = self._lib.Acquire()
        if n_bytes <= 0:
            _log.warning("Acquire returned %d (timeout or no trigger)", n_bytes)
            return None
        _log.debug("Acquired %d bytes", n_bytes)
        self._lib.ProcessCamData(1, 0, 0)
        return self._lib.GetCamArr(1)

    def acquire_single(self):
        """
        Helper function to acquire a single frame and return it as a numpy array.
        """
        self._require_open("acquire_single")
        self.flush()
        data = self._acquire()
        if data is None:
            return None
        return self.to_numpy(data)

    def acquire_avg(self, n_frames: int = 10):
        """
        Acquire multiple frames in a loop and return their average.
        """
        self._require_open("continuous_acquire")
        self.flush()

        acc = None
        count = 0
        for _ in range(n_frames):
            data = self._acquire()
            if data is None:
                continue
            np_data = self.to_numpy(data)
            if acc is None:
                acc = np_data.astype(np.float64)
            else:
                acc += np_data
            count += 1
        if count == 0:
            return None
        return acc / count

    def stream_on_trigger(self, t_acquire_s: float, n_frames: int):
        """Not implemented -- stream frames gated on an external trigger."""
        raise NotImplementedError

    def _frame_duration_s(self) -> float:
        """
        Duration of one sensor frame in seconds.

        Prefers the hardware's own FrmDur35MHz register (ticks of the 35 MHz
        sequencer clock). Falls back to the demodulation formula
        ``Nc / f_d``, with ``Nc = SensNavM2*2 + 2`` and
        ``f_d = 70 MHz / (8*(SensTqp + 30))``, which agrees with the register
        to ~1% on this camera.
        """
        if self._is_open:
            try:
                ticks = self.get_attribute("FrmDur35MHz")
                if ticks > 0:
                    return ticks / self.SEQUENCER_CLOCK_HZ
            except Exception:
                pass
            try:
                n_cycles = self.get_attribute("SensNavM2") * 2 + 2
                f_demod = 70e6 / (8 * (self.get_attribute("SensTqp") + 30))
                return n_cycles / f_demod
            except Exception:
                pass
        return self.NOMINAL_FRAME_DURATION_S

    def _payload_bytes(self, cam_mode: int, n_frames: int) -> int:
        """
        Bytes transferred over USB for one acquisition in the given CamMode.

        Volume modes stream every frame; the surface modes (4, 7) do the
        peak-finding on the FPGA and return only a collapsed 2D surface, so
        their payload does not scale with SensNFrames.
        """
        px = self.SENSOR_HEIGHT * self.SENSOR_WIDTH
        if cam_mode in (0, 3):        # DF_I16Q16  — full I/Q volume
            return n_frames * px * 2 * 2
        if cam_mode == 1:             # DF_A16     — amplitude volume
            return n_frames * px * 2
        if cam_mode in (4, 7):        # DF_A16Z16  — collapsed surface
            return px * 2 * 2
        if cam_mode == 5:             # DF_Z16A16P16 — Z/A/phase over a window
            hwin = 5
            if self._is_open:
                try:
                    hwin = self.get_attribute("ExSimpMaxHwin")
                except Exception:
                    pass
            return px * (2 * hwin + 1) * 3 * 2
        return n_frames * px * 2 * 2  # unknown mode — assume full volume

    def estimate_acquire_time(self, n_frames: int = None, cam_mode: int = None) -> float:
        """
        Estimate how long a single ``acquire()`` will take, in seconds.

        Sensing and USB transfer are pipelined, so the wall time is set by
        whichever dominates::

            sensor   = SensNFrames * FrmDur35MHz / 35 MHz
            transfer = payload_bytes / USB_THROUGHPUT_BPS
            estimate = max(sensor, transfer)

        For the volume modes (0, 1, 3) transfer dominates heavily — a 385-frame
        intensity acquisition senses for 257 ms but moves 138.6 MB, taking
        ~3.8 s. For the surface modes (4, 7) the FPGA returns only a 2D surface,
        so sensing dominates instead.

        Parameters
        ----------
        n_frames:
            Frame count to estimate for. Defaults to the camera's live
            SensNFrames when open, else the STEADY_SETTINGS value.
        cam_mode:
            CamMode to estimate for. Defaults to the mode set by the most
            recent ``prepare_measurement_mode()``, else the live register.

        Returns
        -------
        float
            Estimated seconds per acquisition.

        Notes
        -----
        Calibrated against measurements on camera 1002688069 at 36.5 MB/s
        (USB 2.0 bulk), accurate to within ~0.3% for CamMode 3 at 100/200/385
        frames. The surface-mode branch follows the documented data formats but
        has not been measured. Throughput is a property of the link, so retune
        ``USB_THROUGHPUT_BPS`` if the camera is moved to a different controller.
        """
        if n_frames is None:
            n_frames = (self.get_attribute("SensNFrames") if self._is_open
                        else self.STEADY_SETTINGS["SensNFrames"])
        if cam_mode is None:
            cam_mode = getattr(self, "_current_cammode", None)
            if cam_mode is None:
                cam_mode = (self.get_attribute("CamMode") if self._is_open
                            else self.STEADY_SETTINGS["CamMode"])

        sensor_s = n_frames * self._frame_duration_s()
        payload = self._payload_bytes(cam_mode, n_frames)
        transfer_s = payload / self.USB_THROUGHPUT_BPS
        estimate = max(sensor_s, transfer_s)

        _log.debug(
            "estimate_acquire_time: CamMode=%s N=%d -> %.3fs "
            "(sensor %.3fs, transfer %.3fs for %.1f MB)",
            cam_mode, n_frames, estimate, sensor_s, transfer_s, payload / 1e6,
        )
        return estimate

    # ------------------------------------------------------------------
    # 5. trigger
    # ------------------------------------------------------------------
    def set_internal_trigger(self, f_hz, phase):
        """Not implemented -- configure the camera's internal trigger frequency/phase."""
        raise NotImplementedError

    def get_trigger_status(self):
        """Not implemented -- read back internal trigger frequency/phase."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 6. Lock-in acquisition (arm / read_frame / set_demod_clock)
    # ------------------------------------------------------------------
    #
    # Implements the plan doc's (§5.3) per-trigger lock-in interface:
    #   arm(n_demod, phi_us) -> configure the next accumulation
    #   read_frame()         -> block for it and return (I, Q)
    #   set_demod_clock()    -> select the demod clock source
    #
    # phi_us and the external demod-clock source both depend on SDK
    # registers that have not been confirmed against the register
    # description yet -- see plan doc §6 open item ("confirm heliCam C3
    # frame-sync/trigger output"). Until that's resolved, phi_us=0 and
    # set_demod_clock() are documented gaps, not silently-wrong stand-ins.

    def arm(self, n_demod: int, phi_us: float = 0.0) -> None:
        """
        Prepare the camera to accumulate one lock-in half-period on the
        next trigger edge.

        Parameters
        ----------
        n_demod:
            Number of demodulation cycles to accumulate before readout
            (plan doc §3's N_demod). Must be even -- odd N_demod leaves a
            residual 1f component instead of cancelling it pairwise (plan
            doc §3, §5.4 invariant). Maps onto the averaging-cycle
            register via ``SensNavM2 = (n_demod-2)/2``, valid for
            n_demod in [4, 512] (even).
        phi_us:
            Trigger-to-accumulation start delay, in microseconds (plan
            doc §3's φ₁/φ₂). Only 0 is currently supported.

        Raises
        ------
        ValueError
            If `n_demod` is odd or maps outside the register's range.
        NotImplementedError
            If `phi_us` is nonzero -- no confirmed SDK register exposes a
            trigger-start delay yet (plan doc §6 open item).

        Notes
        -----
        Uses CamMode 0 (raw IQ) so `read_frame()` can return (I, Q)
        directly, without the surface-mode peak-finding CamMode 4/7 do
        on-FPGA.
        """
        self._require_open("arm")
        if n_demod % 2 != 0:
            raise ValueError(f"n_demod must be even (plan doc §3/§5.4), got {n_demod}")
        sens_nav_m2 = (n_demod - 2) // 2
        if not (1 <= sens_nav_m2 <= 255):
            raise ValueError(
                f"n_demod={n_demod} -> SensNavM2={sens_nav_m2} out of range "
                f"[1, 255] (valid n_demod: 4-512, even)"
            )
        if phi_us != 0.0:
            raise NotImplementedError(
                f"phi_us={phi_us} requested but no confirmed SDK register exposes "
                f"a trigger-start delay yet -- see plan doc §6 open item"
            )

        self.set_attributes(AcqStop=1)
        self.set_attributes(CamMode=0, SensNavM2=sens_nav_m2, SensNFrames=1, AcqStop=0)
        fmt = LibHeLIC.CamDataFmt[self._MODE_TO_FMT[0]]
        self._lib.AllocCamData(1, fmt, 0, 0, 0)
        self._current_cammode = 0
        _log.info("Armed for n_demod=%d (SensNavM2=%d), phi_us=%.1f", n_demod, sens_nav_m2, phi_us)

    def read_frame(self):
        """
        Block until the accumulation set up by `arm()` completes and
        return (I, Q).

        Returns
        -------
        tuple[np.ndarray, np.ndarray] or None
            (I, Q), each int16 (300, 300). None if the acquisition timed
            out or missed its trigger (see `_acquire()`).
        """
        self._require_open("read_frame")
        data = self._acquire()
        if data is None:
            return None
        iq = data.view(np.int16).reshape(self.SENSOR_HEIGHT, self.SENSOR_WIDTH, 2)
        return iq[:, :, 0], iq[:, :, 1]

    def set_demod_clock(self, external: bool = True) -> None:
        """
        Select the demodulation clock source.

        Parameters
        ----------
        external:
            If True, lock the demod clock to the PEM 2f reference (plan
            doc §3's mandatory hard lock -- the PEM is resonant and
            drifts, so free-running against it is not an option for real
            data).

        Raises
        ------
        NotImplementedError
            Always, for now -- no SDK register for demod-clock source has
            been confirmed yet (plan doc §6 open item). Do not substitute
            `TrigFreeExtN` here: that register gates the acquisition
            *trigger*, not the demodulation clock, and treating them as
            interchangeable would silently defeat the PEM lock this
            method exists to guarantee.
        """
        raise NotImplementedError(
            "set_demod_clock: no confirmed SDK register for demod clock source "
            "-- see plan doc §6 open item"
        )

    # ------------------------------------------------------------------
    # 7. Data processing
    # ------------------------------------------------------------------
    def to_numpy(self, data):
        """
        Post-process raw acquire() output into a spatially meaningful array.

        The behaviour depends on the CamMode set by the most recent call to
        ``prepare_measurement_mode()`` (stored in ``self._current_cammode``).

        Parameters
        ----------
        data : np.ndarray
            Array returned by ``acquire()`` (uint16, shape depends on mode).

        Returns
        -------
        np.ndarray
            * **CamMode 3 – intensity**: 2D int32 (300 × 300).  Dark frames are
              excluded and I/Q channels are summed to yield an HDR intensity image.
            * **CamMode 0 – raw IQ**: int16 volume (n_frames × 300 × 300 × 2).
            * **CamMode 1 – amplitude**: uint16 volume as returned by GetCamArr.
            * **CamMode 4, 7 – surface**: uint16 (H × W × 2); channel 0 = amplitude,
              channel 1 = Z-height.
        """
        cam_mode = getattr(self, '_current_cammode', None)
        if cam_mode is None and self._is_open:
            cam_mode = self.get_attribute('CamMode')

        if cam_mode == 3:
            # IQ bytes are signed; GetCamArr reads them as uint16 → reinterpret.
            arr = data.view(np.int16)           # shape: (n_frames, 300, 300, 2)
            n_dark = self.STEADY_SETTINGS.get('SensNDarkFrames', 10)
            if self._is_open:
                try:
                    n_dark = self.get_attribute('SensNDarkFrames')
                except Exception:
                    pass
            useful = arr[n_dark:].astype(np.int32)
            return useful.sum(axis=0).sum(axis=-1)   # (300, 300) HDR intensity

        elif cam_mode == 0:
            # Raw IQ — return signed volume unchanged.
            return data.view(np.int16)

        elif cam_mode in (4, 7):
            # Surface modes: uint16 (H, W, 2) — amplitude in [:,:,0], Z in [:,:,1].
            return data

        else:
            # Amplitude volume or unknown mode — return as-is.
            return data

if __name__ == "__main__":
    print("This module is intended to be imported, not run directly.")