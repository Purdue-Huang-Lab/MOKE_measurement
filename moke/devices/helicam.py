"""
HeliCam C3 camera driver wrapper.

Wraps the libHeLIC C library for the C3 camera system (e.g. c3cam_sl70).
"""

import ctypes as ct
import json
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

    # Register set read off a confirmed-good steady-state capture in the
    # Heliotis heliViewer GUI. Final desired state (AcqStop ends at 0 --
    # heliViewer, like set_measurement_mode() below, halts acquisition with
    # AcqStop=1 first, writes everything else, then restarts with AcqStop=0).
    # Notably includes SensNavM2/SensTqp -- STEADY_SETTINGS above sets
    # neither, so steady mode currently inherits whatever those two demod-
    # timing registers were last left at by an earlier mode/session instead
    # of these values. See compare_steady_settings_to_gui_reference().
    STEADY_SETTINGS_GUI_REFERENCE = {
        "CamMode":         3,
        "SensExpTime":     10,
        "SensExpTimeMult": 0,
        "SensExpRatio":    3,
        "SensNDarkFrames": 7,
        "SensNFrames":     256,
        "BSEnable":        0,
        "TrigFreeExtN":    1,
        "SensNavM2":       2,
        "SensTqp":         1392,
        "AcqStop":         0,
    }

    RAWIQ_SETTINGS = {
        "CamMode":       0,
        # Without an explicit default here, switching into rawIQ mode after
        # "steady" (SensNFrames=385) would silently inherit that leftover
        # value -- a 385-frame raw IQ volume instead of a small test
        # acquisition. Override via set_measurement_mode("rawIQ", SensNFrames=...).
        "SensNFrames":   10,
    }

    AMPLITUDE_SETTINGS = {
        "CamMode":       1,
        "OffsetMethod":  0,
    }

    # --- Physical / calibration constants, used by estimate_acquire_time() ---

    SENSOR_HEIGHT = 300     # helioct3 sensor, per SysDesc.xml (size="300 300")
    SENSOR_WIDTH  = 300

    # Manual ch.8 "Sensor Specification": "300 (centre 292 usable; 2x4 rows
    # are test rows)" / "300 (centre 280 usable; 2x10 columns are test
    # columns)" -- the border pixels carry a fixed hardware self-test
    # pattern, not photodiode data (confirmed empirically: they clip hard
    # against 0/1023 regardless of light level -- see
    # archive/helicam_document/helicamC3_practical_knowledge_base.md #1).
    # Raw acquisitions are still the full SENSOR_HEIGHT x SENSOR_WIDTH --
    # see crop_unphysical().
    SENSOR_HEIGHT_USABLE = 292
    SENSOR_WIDTH_USABLE  = 280

    # ADC output resolution -- manual §8.1/8.2 "Sensor Specification" table
    # ("Output Resolution | 10 bit", both heliSens S3.0 and S3.1 variants),
    # corroborated by §5.1: "raw_I and raw_Q values are returned, ranging
    # 0-1023 (10-bit, unsigned u10.0)". Source is the manual
    # (heliCamC3_manual_v1_15.md), NOT the register description PDF --
    # despite an earlier version of this comment saying so.
    SENSOR_ADC_MAX = 1023

    # DdsGain register code <-> analogue voltage gain (register description
    # §2.x: 00->3x, 01->1.5x, 10->1x [best SNR], 11->0.75x). Shared by
    # set_gain() and auto_expose() so the two can't drift apart.
    ANALOGUE_GAIN_LIST = [3.0, 1.5, 1.0, 0.75]
    DDS_GAIN_CODES     = [0, 1, 2, 3]

    # SensExpRatio register code -> short:long exposure ratio (register
    # description §2.13, corroborated by manual §5.4's table): 0->1:2,
    # 1->1:4, 2->1:8, 3->1:16. In CamMode 3, channel 0 is the long-exposure
    # image and channel 1 is the short-exposure image -- confirmed
    # empirically (mode6_sensexpratio_sweep), see
    # archive/helicam_document/helicamC3_practical_knowledge_base.md #3.
    # auto_expose() uses this ratio as a self-calibrating saturation
    # detector: channel0/channel1 should equal this value whenever both
    # channels are unsaturated, regardless of incident light level.
    SENSEXPRATIO_SHORT_LONG = {0: 2, 1: 4, 2: 8, 3: 16}

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
    # data_reformat(). That diverges from the documented path, but STEADY_SETTINGS
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

    def get_registers(self, include_comments: bool = False) -> dict:
        """
        Read every map register the camera exposes, not just the handful
        ``STEADY_SETTINGS``/``DEFAULT_SETTINGS`` care about -- the same
        full list heliViewer's register dialog shows.

        Read-only (one ``HE_GetMap`` per entry -- tens of calls, no
        acquisition), so it's cheap to call regardless of how slow an
        acquisition in the current mode would be. Useful for capturing
        "what heliViewer actually left the camera in" to diff against
        what this driver assumes (e.g. via ``diff_attributes()``), or for
        spotting registers this driver doesn't know about at all.

        Parameters
        ----------
        include_comments:
            If True, each value becomes ``{"value": <int>, "comment": <str>}``,
            with the comment pulled from the SDK's own register descriptor.
            Default False for a plain ``{name: value}`` dict.

        Returns
        -------
        dict
            Map attribute name -> value (or value+comment dict).
        """
        self._require_open("dump_registers")
        if not include_comments:
            # self._lib.map.as_dict() does the same GetMap-per-entry walk,
            # but leaves keys as raw bytes (b'CamMode') instead of str --
            # a vendor-wrapper quirk (it decodes keys everywhere else, e.g.
            # MapByName.__getattr__, but not here) -- decode for usability.
            raw = self._lib.map.as_dict()
            return {(k.decode("utf-8") if isinstance(k, bytes) else k): v
                    for k, v in raw.items()}

        rd = self._lib.GetRegDesc().contents
        out = {}
        for idx in range(rd.numMap):
            m = rd.maps[idx]
            out[m.id.decode("utf-8")] = {
                "value": self._lib.GetMap(ct.pointer(m)),
                # SDK comments are C strings in Windows-1252 (e.g. curly
                # quotes as 0x91/0x92), not UTF-8 -- utf-8 raises on those.
                "comment": m.cmt.decode("cp1252", errors="replace") if m.cmt else "",
            }
        return out

    def dump_registers(self, out_dir: str, name: str = "registers", include_comments: bool = True) -> str:
        """
        Read every live register (``get_registers()``) and write it to
        ``<out_dir>/<name>.json``.

        Read-only, no acquisition -- safe to call any time the camera is
        open, regardless of mode or how slow an acquisition in the current
        mode would be. Registers own their file-IO here (unlike frames/
        tables, which stay the test script's job -- see
        device_interface_instruction.md) because a register dump is a
        driver-level diagnostic: the main use is bracketing a call like
        ``auto_expose()`` to see exactly what it left changed.

        Parameters
        ----------
        out_dir:
            Directory to write into. Must already exist.
        name:
            Output filename, without extension.
        include_comments:
            Passed through to ``get_registers()``.

        Returns
        -------
        str
            Path written.
        """
        registers = self.get_registers(include_comments=include_comments)
        path = os.path.join(out_dir, name + ".json")
        with open(path, "w") as f:
            json.dump(registers, f, indent=2, default=str)
        _log.info("Wrote %s (%d registers)", path, len(registers))
        return path

    def diff_attributes(self, reference: dict) -> dict:
        """
        Read back each attribute in ``reference`` from the live camera and
        report where it differs.

        Read-only -- just register reads (HE_GetMap), no acquisition -- so
        it's cheap and safe to call regardless of how slow a full
        acquisition in the current mode would be.

        Parameters
        ----------
        reference:
            Attribute name -> expected value, e.g. ``STEADY_SETTINGS_GUI_REFERENCE``.

        Returns
        -------
        dict
            ``{name: {"current": <live value>, "reference": <expected value>}}``
            for every attribute that differs. Empty if everything matches.
        """
        self._require_open("diff_attributes")
        mismatches = {}
        for name, expected in reference.items():
            current = self.get_attribute(name)
            if current != expected:
                mismatches[name] = {"current": current, "reference": expected}
        if mismatches:
            _log.warning("diff_attributes: %d mismatch(es) vs reference: %s", len(mismatches), mismatches)
        else:
            _log.info("diff_attributes: all %d attribute(s) match reference", len(reference))
        return mismatches

    def get_image_shape(self) -> tuple[int, int]:
        """
        Get the expected shape of the image returned by acquire_single()
        (i.e. after crop_unphysical() has removed the border test pixels --
        data_reformat() alone, called on uncropped data, would still be the
        full SENSOR_HEIGHT x SENSOR_WIDTH).

        Returns
        -------
        tuple[int, int]
            (height, width) of the image array.
        """
        return self.SENSOR_HEIGHT_USABLE, self.SENSOR_WIDTH_USABLE


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

    def compare_steady_settings_to_gui_reference(self) -> dict:
        """
        Compare the live register state to ``STEADY_SETTINGS_GUI_REFERENCE``
        (a confirmed-good steady-state capture from heliViewer).

        Call after ``set_measurement_mode("steady")``. Read-only, no
        acquisition -- intended to catch exactly the gap ``STEADY_SETTINGS``
        currently has: it never writes ``SensNavM2``/``SensTqp``, so steady
        mode inherits whatever those two demod-timing registers were last
        left at by an earlier mode/session instead of heliViewer's values.

        Returns
        -------
        dict
            Mismatches vs the reference, see ``diff_attributes()``.
        """
        return self.diff_attributes(self.STEADY_SETTINGS_GUI_REFERENCE)

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
        if analogue_gain not in self.ANALOGUE_GAIN_LIST:
            raise ValueError(f"Invalid analogue_gain: {analogue_gain}. Allowed values are {self.ANALOGUE_GAIN_LIST}.")
        DdsGain = self.DDS_GAIN_CODES[self.ANALOGUE_GAIN_LIST.index(analogue_gain)]
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
        as int16 before arithmetic — ``data_reformat()`` handles this automatically.
        """
        self._require_open("acquire")
        n_bytes = self._lib.Acquire()
        if n_bytes <= 0:
            _log.warning("Acquire returned %d (timeout or no trigger)", n_bytes)
            return None
        _log.debug("Acquired %d bytes", n_bytes)
        self._lib.ProcessCamData(1, 0, 0)
        return self._lib.GetCamArr(1)

    def crop_unphysical(self, data: np.ndarray) -> np.ndarray:
        """
        Crop the sensor's non-photodiode border rows/columns out of a raw
        acquisition, leaving the centered SENSOR_HEIGHT_USABLE x
        SENSOR_WIDTH_USABLE pixels.

        Locates the sensor's H=300, W=300 axes by shape -- works for both
        the ``(n_frames, 300, 300, [channels])`` volume-mode layout and the
        ``(300, 300, channels)`` surface-mode layout -- and slices them down
        to the centered usable region.

        Parameters
        ----------
        data:
            Raw array as returned by ``_acquire()``: any shape containing
            two consecutive axes of length SENSOR_HEIGHT, SENSOR_WIDTH.

        Returns
        -------
        np.ndarray
            Same shape, except the sensor H/W axes are cropped to
            SENSOR_HEIGHT_USABLE x SENSOR_WIDTH_USABLE.

        Raises
        ------
        ValueError
            If no axis pair matching (SENSOR_HEIGHT, SENSOR_WIDTH) is found.
        """
        shape = data.shape
        for axis in range(len(shape) - 1):
            if shape[axis] == self.SENSOR_HEIGHT and shape[axis + 1] == self.SENSOR_WIDTH:
                row0 = (self.SENSOR_HEIGHT - self.SENSOR_HEIGHT_USABLE) // 2
                col0 = (self.SENSOR_WIDTH - self.SENSOR_WIDTH_USABLE) // 2
                idx = [slice(None)] * data.ndim
                idx[axis] = slice(row0, row0 + self.SENSOR_HEIGHT_USABLE)
                idx[axis + 1] = slice(col0, col0 + self.SENSOR_WIDTH_USABLE)
                return data[tuple(idx)]
        raise ValueError(
            f"crop_unphysical: no axis pair of shape "
            f"({self.SENSOR_HEIGHT}, {self.SENSOR_WIDTH}) found in array shape {shape}"
        )

    def acquire_single(self):
        """
        Helper function to acquire a single frame and return it as a numpy array.

        Crops the sensor's non-photodiode border rows/columns
        (``crop_unphysical()``) before ``data_reformat()`` -- both so no
        downstream statistic (max/percentile/etc.) is ever computed over
        border pixels, and so the dark-frame baseline in CamMode 3 isn't
        itself skewed by border pixels that clip against 0/1023.
        """
        self._require_open("acquire_single")
        self.flush()
        data = self._acquire()
        if data is None:
            return None
        data = self.crop_unphysical(data)
        return self.data_reformat(data)

    def acquire_avg(self, n_frames: int = 10):
        """
        Acquire multiple frames in a loop and return their average.

        Crops the sensor's non-photodiode border rows/columns
        (``crop_unphysical()``) before ``data_reformat()``, same as
        ``acquire_single()``.
        """
        self._require_open("continuous_acquire")
        self.flush()

        acc = None
        count = 0
        for _ in range(n_frames):
            data = self._acquire()
            if data is None:
                continue
            data = self.crop_unphysical(data)
            np_data = self.data_reformat(data)
            if acc is None:
                acc = np_data.astype(np.float64)
            else:
                acc += np_data
            count += 1
        if count == 0:
            return None
        return acc / count

    def save_raw_np(self, out_dir: str, name: str = "raw", mode: int = None) -> str:
        """
        Acquire one frame and save the *raw*, pre-``data_reformat()`` array
        straight to ``<out_dir>/<name>.npz`` -- bypasses ``data_reformat()``'s
        CamMode-specific reduction entirely, so the untouched sensor output
        can be reprocessed later. This is the reusable form of the manual
        ``breakpoint()`` capture used to debug ``data_reformat()`` itself
        (see helicam_test_016's in_run_frame/dark_ref/useful.npy). Unlike
        ``acquire_single()``, also bypasses ``crop_unphysical()`` -- the
        saved array still includes the sensor's border test pixels, since
        this is meant to preserve everything for later debugging.

        Parameters
        ----------
        out_dir:
            Directory to write into. Must already exist.
        name:
            Output filename, without extension.
        mode:
            CamMode this capture should be tagged as, for later
            reprocessing. Defaults to the live CamMode most recently set
            via ``set_measurement_mode()``/``arm()`` -- doesn't affect
            acquisition, just records what mode the camera was in, since a
            raw dump alone has no memory of that once reloaded outside a
            live driver session.

        Returns
        -------
        str or None
            Path written, or None if the acquisition failed (timeout).
        """
        self._require_open("save_raw_np")
        if mode is None:
            mode = getattr(self, "_current_cammode", None)
        self.flush()
        data = self._acquire()
        if data is None:
            _log.warning("save_raw_np(%s): acquire failed, nothing saved", name)
            return None
        path = os.path.join(out_dir, name + ".npz")
        np.savez(path, data=data, cam_mode=mode)
        _log.info("Wrote %s (CamMode=%s, shape=%s, dtype=%s)", path, mode, data.shape, data.dtype)
        return path

    def stream_on_trigger(self, t_acquire_s: float, n_frames: int):
        """Not implemented -- stream frames gated on an external trigger."""
        raise NotImplementedError

    def auto_expose(
        self,
        target_fraction: float = 0.5,
        t_min_us: float = 1.0,
        t_max_us: float = 16380.0,
        ratio_tol: float = 0.1,
        max_iter: int = 20,
    ) -> dict:
        """
        Find the short-exposure time that puts channel 0 (the long-exposure
        channel) ``target_fraction`` of the way to saturation, using the
        camera's own dual-channel HDR pair as a self-calibrating saturation
        detector -- no assumption about the sensor's absolute ADC ceiling
        required.

        In CamMode 3, channel 0 is exposed ``SensExpRatio``-times longer
        than channel 1 (manual §5.4; ratio confirmed empirically -- see
        ``SENSEXPRATIO_SHORT_LONG`` and
        archive/helicam_document/helicamC3_practical_knowledge_base.md #3).
        In the unsaturated (linear) regime, ``channel0 / channel1`` equals
        that same nominal ratio at *any* incident light level -- it's a
        property of the two exposure times, not of the light level itself.
        Once channel 0 starts clipping, its growth falls behind channel 1's
        and the observed ratio drops below nominal: a purely relative
        signal that sidesteps ever having to know channel 0's true ADC
        ceiling (which, per the knowledge base #2, isn't simply
        ``SENSOR_ADC_MAX`` anyway -- the raw ~512 baseline halves the real
        headroom).

        Two-phase geometric-then-bisection search, bounded per
        device_interface_instruction.md §6 ("every blocking call has a
        bounded timeout"):

        1. Double ``t`` from ``t_min_us`` while the observed ratio stays
           within ``ratio_tol`` of nominal (channel 0 still unsaturated).
        2. Once a trial's ratio deviates, bisect between the last
           unsaturated and first saturated ``t`` (to within 5% or 0.5µs) to
           refine the saturation onset, ``t_saturation_onset_us``.
        3. Set and return ``target_fraction * t_saturation_onset_us`` as
           the operating exposure -- e.g. the default 0.5 backs off to half
           the exposure time at which channel 0 starts clipping.

        Parameters
        ----------
        target_fraction:
            Fraction of the way to the detected saturation onset to land
            the final exposure at, e.g. 0.5 for "halfway to saturation".
        t_min_us, t_max_us:
            Search bounds, in microseconds (same range as ``set_acquire_time``).
        ratio_tol:
            Relative deviation from the nominal ``SensExpRatio``-derived
            ratio that counts as "channel 0 has started saturating".
        max_iter:
            Upper bound on the number of trial acquisitions.

        Returns
        -------
        dict
            ``{"t_acquire_us": <final exposure>,
            "t_saturation_onset_us": <t where channel 0 starts clipping, or None>,
            "nominal_ratio": <expected channel0/channel1 ratio from SensExpRatio>,
            "floor_limited": <bool>, "ceiling_not_found": <bool>,
            "table": [{"t_acquire_us", "ch0", "ch1", "ratio", "deviates"}, ...]}``.
            ``table`` has one row per trial acquisition, in call order.
            ``floor_limited`` is True when channel 0 is already saturating
            at ``t_min_us`` -- exposure can't be reduced any further in
            software. ``ceiling_not_found`` is True when the search reached
            ``t_max_us``/``max_iter`` (or hit an acquisition failure)
            without ever seeing the ratio deviate -- ``t_acquire_us`` falls
            back to the largest ``t`` actually tried, and
            ``target_fraction`` isn't meaningful in this case since no
            saturation onset was located.

        Raises
        ------
        RuntimeError
            If the camera is not open, or not already in intensity/steady
            mode -- call ``set_measurement_mode("steady")`` first. No
            implicit mode switching (matches the rest of this file).
        """
        self._require_open("auto_expose")
        if getattr(self, "_current_cammode", None) != 3:
            raise RuntimeError(
                "auto_expose: camera must be in intensity/steady mode -- "
                "call set_measurement_mode('steady') first"
            )

        sens_exp_ratio = self.get_attribute("SensExpRatio")
        nominal_ratio = self.SENSEXPRATIO_SHORT_LONG[sens_exp_ratio]
        table = []

        def trial(t_us):
            t_us = min(max(t_us, t_min_us), t_max_us)
            self.set_acquire_time(t_us)
            self.flush()
            data = self._acquire()
            if data is None:
                table.append({"t_acquire_us": t_us, "ch0": None, "ch1": None,
                              "ratio": None, "deviates": None})
                _log.warning("auto_expose trial %d: t_acquire_us=%.1f -> acquire failed",
                             len(table), t_us)
                return t_us, None
            data = self.crop_unphysical(data)
            channels = self._dark_subtract_channels(data)
            ch0 = float(np.percentile(channels[..., 0], 99.9))
            ch1 = float(np.percentile(channels[..., 1], 99.9))
            ratio = (ch0 / ch1) if ch1 else float("inf")
            deviates = ratio < nominal_ratio * (1 - ratio_tol)
            table.append({"t_acquire_us": t_us, "ch0": ch0, "ch1": ch1,
                          "ratio": ratio, "deviates": deviates})
            _log.info(
                "auto_expose trial %d: t_acquire_us=%.1f -> ch0=%.1f, ch1=%.1f, "
                "ratio=%.2f (nominal=%d)%s",
                len(table), t_us, ch0, ch1, ratio, nominal_ratio,
                " [SATURATING]" if deviates else "",
            )
            return t_us, deviates

        def not_found(t_acquire_us):
            self.set_acquire_time(t_acquire_us)
            return {"t_acquire_us": t_acquire_us, "t_saturation_onset_us": None,
                    "nominal_ratio": nominal_ratio, "floor_limited": False,
                    "ceiling_not_found": True, "table": table}

        t_lo, dev_lo = trial(t_min_us)
        if dev_lo is None:
            _log.warning("auto_expose: initial acquisition failed, aborting")
            return not_found(t_min_us)
        if dev_lo:
            _log.warning(
                "auto_expose: channel 0 already saturating at the minimum "
                "exposure t_min_us=%.1f -- cannot reduce exposure further; "
                "lower the gain or incident light", t_lo,
            )
            return {"t_acquire_us": t_lo, "t_saturation_onset_us": t_lo,
                    "nominal_ratio": nominal_ratio, "floor_limited": True,
                    "ceiling_not_found": False, "table": table}

        t_hi, dev_hi = t_lo, dev_lo
        while not dev_hi and t_hi < t_max_us and len(table) < max_iter:
            t_lo = t_hi
            t_hi, dev_hi = trial(t_hi * 2)
            if dev_hi is None:
                _log.warning("auto_expose: acquisition failed mid-search, stopping at t=%.1f", t_lo)
                return not_found(t_lo)

        if not dev_hi:
            _log.warning(
                "auto_expose: channel 0 never saturated even at t_max_us=%.1f "
                "-- can't locate a saturation onset in range", t_max_us,
            )
            return not_found(t_hi)

        # Bisect [t_lo (unsaturated), t_hi (saturated)] to refine the onset.
        while len(table) < max_iter and (t_hi - t_lo) > max(0.05 * t_hi, 0.5):
            t_mid = (t_lo + t_hi) / 2
            _, dev_mid = trial(t_mid)
            if dev_mid is None:
                break
            if dev_mid:
                t_hi = t_mid
            else:
                t_lo = t_mid

        t_saturation_onset_us = t_hi
        final_t = min(max(target_fraction * t_saturation_onset_us, t_min_us), t_max_us)
        self.set_acquire_time(final_t)
        _log.info(
            "auto_expose: saturation onset at t=%.1f -> final t_acquire_us=%.1f "
            "(target_fraction=%.2f, %d trials)",
            t_saturation_onset_us, final_t, target_fraction, len(table),
        )
        return {"t_acquire_us": final_t, "t_saturation_onset_us": t_saturation_onset_us,
                "nominal_ratio": nominal_ratio, "floor_limited": False,
                "ceiling_not_found": False, "table": table}

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

    def _dark_subtract_channels(self, data: np.ndarray, n_dark: int = None) -> np.ndarray:
        """
        Dark-subtract and frame-average a raw CamMode-3 acquisition,
        keeping channel 0 (long exposure) and channel 1 (short exposure)
        separate. Shared by ``data_reformat()`` (which then sums the two
        channels together) and ``auto_expose()`` (which needs them kept
        apart to compare their magnitudes).

        BSEnable=0 is mandatory in intensity mode (manual §5.4), so the
        hardware doesn't suppress the per-pixel baseline itself -- the
        first ``n_dark`` frames measure it, averaged and subtracted from
        the rest. Confirmed necessary on real hardware: without this, a 10x
        drop in incident light changed the combined value by <1%
        (baseline-dominated), which made auto_expose() chase a signal that
        wasn't tracking light level.

        Averaging (not summing) over frames is deliberate -- see the
        CamMode-3 NOTE on ``_MODE_TO_FMT`` -- so ``SensNFrames`` stays a
        noise-averaging knob, not a light-budget one. Subtracting the
        (per-pixel/channel constant) dark reference commutes with
        averaging, so doing it after rather than before the frame-average
        is equivalent and cheaper.

        Parameters
        ----------
        data:
            Raw array from ``_acquire()`` (optionally already
            ``crop_unphysical()``'d), shape ``(n_frames, H, W, 2)``.
        n_dark:
            Number of leading dark frames. Defaults to the live
            ``SensNDarkFrames`` register when open, else
            ``STEADY_SETTINGS``.

        Returns
        -------
        np.ndarray
            ``(H, W, 2)`` float64: dark-subtracted, averaged over the
            remaining frames.
        """
        if n_dark is None:
            n_dark = self.STEADY_SETTINGS.get('SensNDarkFrames', 10)
            if self._is_open:
                try:
                    n_dark = self.get_attribute('SensNDarkFrames')
                except Exception:
                    pass
        # IQ bytes are signed; GetCamArr reads them as uint16 → reinterpret.
        arr = data.view(np.int16).astype(np.float64)   # (n_frames, H, W, 2)
        dark_ref = arr[:n_dark].mean(axis=0)            # (H, W, 2)
        return arr[n_dark:].mean(axis=0) - dark_ref     # (H, W, 2)
    def data_reformat(self, data, mode=None):
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
            * **CamMode 3 – intensity**: 2D float64 (300 × 300). The first
              ``SensNDarkFrames`` frames are averaged into a per-pixel
              baseline and subtracted from the remaining frames (BSEnable=0
              in intensity mode means the hardware doesn't do this itself);
              the remaining frames are then averaged (not summed --
              SensNFrames is purely a noise-averaging knob here, not a
              light-budget one) and their I/Q channels summed to yield a
              baseline-subtracted intensity image, scaled to the sensor's
              native per-frame ADC range independent of SensNFrames.
            * **CamMode 0 – raw IQ**: int16 volume (n_frames × 300 × 300 × 2),
              unscaled raw ADC counts (0-1023 nominal range) — use
              ``iq_to_amplitude()`` to convert to physical amplitude.
            * **CamMode 1 – amplitude**: float32 (300 × 300), physical amplitude
              (register description §5.2.1: u12.4 fixed-point → divide by 16).
            * **CamMode 4, 7 – surface**: float32 (H × W × 2); channel 0 = amplitude
              (u12.4 → /16), channel 1 = Z-height (u11.5 → /32), per register
              description §5.3.1.

        Raises
        ------
        NotImplementedError
            For CamMode 2/5/6 (smoothed amplitude, extended simple max,
            reserved) — none are reachable via ``set_measurement_mode()``
            today, and returning their raw fixed-point ints unscaled would be
            silently wrong rather than merely unimplemented (see
            device_interface_instruction.md §2).
        """
        cam_mode = mode if mode is not None else getattr(self, '_current_cammode', None)
        if cam_mode is None and self._is_open:
            cam_mode = self.get_attribute('CamMode')

        if cam_mode == 3:
            # Channel 0 (long exposure) + channel 1 (short exposure) summed
            # -- see _dark_subtract_channels() for the dark-baseline
            # subtraction and frame-averaging this builds on.
            channels = self._dark_subtract_channels(data)   # (300, 300, 2): [long, short]
            return channels.sum(axis=-1)   # (300, 300) float64, baseline-subtracted

        elif cam_mode == 0:
            # Raw IQ — return signed volume unchanged, still raw ADC counts.
            return data.view(np.int16)

        elif cam_mode == 1:
            # Amplitude volume: u12.4 fixed-point (register description §5.2.1).
            return data.astype(np.float32) / 16.0

        elif cam_mode in (4, 7):
            # Surface modes: amplitude u12.4 (/16), Z u11.5 (/32) -- §5.3.1.
            out = np.empty(data.shape, dtype=np.float32)
            out[..., 0] = data[..., 0].astype(np.float32) / 16.0
            out[..., 1] = data[..., 1].astype(np.float32) / 32.0
            return out

        else:
            raise NotImplementedError(
                f"data_reformat(): CamMode {cam_mode} has no documented conversion "
                f"implemented (only 0, 1, 3, 4, 7 are)"
            )

    @staticmethod
    def iq_to_amplitude(I, Q, offset_I: float = 512.0, offset_Q: float = 512.0) -> np.ndarray:
        """
        Convert raw I/Q samples into a lock-in amplitude image.

        Implements the manual's raw-IQ formula (§5.1)::

            I' = raw_I - offset_I
            Q' = raw_Q - offset_Q
            Amplitude = sqrt(I'^2 + Q'^2)

        Parameters
        ----------
        I, Q:
            Raw in-phase/quadrature arrays (e.g. from ``read_frame()`` or a
            slice of a CamMode-0 ``data_reformat()`` volume).
        offset_I, offset_Q:
            Per-channel DC offset to subtract before combining. Default to
            512 -- the manual's documented nominal ADC center for a
            non-modulated signal ("a non-modulated signal corresponds to a
            value around 512, not 0"). Pass the real per-pixel values once a
            calibration routine (``null_offset()``, not yet built) supplies
            them.

        Returns
        -------
        np.ndarray
            Amplitude, same shape as ``I``/``Q``, float64.

        Notes
        -----
        Pure numpy -- no device state, no hardware call. Does not know or
        care which CamMode produced ``I``/``Q``.
        """
        Ic = I.astype(np.float64) - offset_I
        Qc = Q.astype(np.float64) - offset_Q
        return np.sqrt(Ic**2 + Qc**2)

if __name__ == "__main__":
    print("This module is intended to be imported, not run directly.")