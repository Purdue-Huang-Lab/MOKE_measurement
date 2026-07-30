"""
HeliCam C3 camera driver wrapper.

Wraps the libHeLIC C library for the C3 camera system (e.g. c3cam_sl70).
"""

import ctypes as ct
import sys
import os
import logging
import numpy as np

_log = logging.getLogger(__name__)

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


class HeliCamC3:
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

    STEADY_SETTINGS = {
        "CamMode":         3,   # intensity mode — camera behaves like a standard 2D camera
        "SensNFrames":    50,   # total frames; useful HDR output = SensNFrames - SensNDarkFrames - 3
        "SensNDarkFrames":10,   # dark frames taken; must be >= 7 and <= SensNFrames - 4
        "SensExpTime":   100,   # short exposure time [µs]; actual = SensExpTime * (SensExpTimeMult+1)
        "SensExpTimeMult": 1,   # exposure time multiplier; actual exposure = SensExpTime * (SensExpTimeMult+1)
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

    # Map from CamMode to the expected CamDataFmt for AllocCamData.
    _MODE_TO_FMT = {
        0: "DF_I16Q16",   # raw IQ
        1: "DF_A16",      # amplitude volume
        3: "DF_I16Q16",   # intensity (IQ raw used, summed in post)
        4: "DF_A16Z16",   # simple max  → surface (Z) + amplitude (A)
        5: "DF_Z16A16P16",# extended simple max → Z, A, phase
        7: "DF_A16Z16",   # minimize energy
    }


    def __init__(self, sys_id: str = "c3cam", timeout_ms: int = 2000):
        """
        Parameters
        ----------
        sys_id:
            Camera system identifier string passed to HE_Open, e.g.
            ``'c3cam_sl70'``, ``'c3cam'``.
        timeout_ms:
            Acquisition timeout in milliseconds (0 = no timeout).
        """
        self._sys_id = sys_id
        self._timeout_ms = timeout_ms
        self._lib = LibHeLIC()
        self._is_open = False

    # ------------------------------------------------------------------
    # 1. Device lifecycle
    # ------------------------------------------------------------------

    def open(self) -> int:
        """
        Power on / initialise the camera.

        Opens the USB connection, downloads firmware if needed, and applies
        the default settings.

        Returns
        -------
        int
            Return code from HE_Open (0 = success).

        Raises
        ------
        RuntimeError
            If the camera fails to open.
        """
        _log.debug("Opening %s", self._sys_id)
        res = self._lib.Open(0, sys=self._sys_id)
        if res != 0:
            raise RuntimeError(f"HE_Open failed with code {res} for '{self._sys_id}'")
        self._is_open = True
        self._lib.SetTimeout(self._timeout_ms)
        _log.info("Camera '%s' opened (handle=%s)", self._sys_id, self._lib.handle)
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

    # ------------------------------------------------------------------
    # 3. Helpers
    # ------------------------------------------------------------------

    def _require_open(self, caller: str = "") -> None:
        if not self._is_open:
            raise RuntimeError(
                f"{caller}: camera is not open — call open() first"
            )

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

    def prepare_measurement_mode(self, modedesc, **kwargs):
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
        self._require_open("prepare_measurement_mode")

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

        settings = {**base, **kwargs}
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

    def flush(self) -> int:
        """
        Drain stale frames from the USB buffer.

        Must be called after ``prepare_measurement_mode()`` and before the first
        real ``acquire()`` call, otherwise the first frame may contain leftover
        data from a previous session.

        Returns
        -------
        int
            Number of stale frames discarded.
        """
        self._require_open("flush")
        count = 0
        while self._lib.Acquire() > 0:
            count += 1
        _log.info("Flushed %d stale frame(s) from USB buffer", count)
        return count

    def acquire(self):
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
        For IQ-based modes (CamMode 0 and 3) the uint16 view must be reinterpreted
        as int16 before arithmetic — ``to_numpy()`` handles this automatically.
        """
        self._require_open("acquire")
        res = self._lib.Acquire()
        if res != 0:
            _log.warning("Acquire returned %d (timeout or no trigger)", res)
            return None
        self._lib.ProcessCamData(1, 0, 0)
        return self._lib.GetCamArr(1)

    # ------------------------------------------------------------------
    # 5. Data processing
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

