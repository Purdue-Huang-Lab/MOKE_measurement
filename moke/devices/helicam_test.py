"""
HeliCam C3 hardware test script -- run manually against real hardware.

Seven modes, one bench checkout item each. Each run creates a fresh
``helicam_test_data/helicam_test_NNN/`` folder (auto-incrementing) so
repeated runs never clobber each other's data. Regardless of mode, every
run finishes by dumping the full live register set to ``registers.json``
(see ``HeliCamC3.dump_registers()``) -- a cheap, always-useful record of
exactly what state the camera was left in. Mode 4 additionally dumps
registers immediately before and after its ``auto_expose()`` call, to
catch what that search itself changes.

Usage::

    python -m moke.devices.helicam_test --mode 1
    python -m moke.devices.helicam_test --mode 2
    python -m moke.devices.helicam_test --mode 3
    python -m moke.devices.helicam_test --mode 4
    python -m moke.devices.helicam_test --mode 5
    python -m moke.devices.helicam_test --mode 6
    python -m moke.devices.helicam_test --mode 7
    python -m moke.devices.helicam_test --mode 8
    python -m moke.devices.helicam_test --mode 9 --f-pem-hz 50023 --note pem_on

Mode 1 -- lifecycle / exposure characterization:
    open -> steady mode -> gain=1x (best SNR, DdsGain=2) -> acquire across a
    fixed, log-spaced list of exposures, recording a (t_acquire_us, max_val)
    table. Does NOT use auto_expose() -- see open_issue_helicam.md #9.

Mode 2 -- lock-in detection:
    open -> steady mode at a fixed exposure -> steady frame -> rawIQ mode ->
    convert I/Q to amplitude -> amplitude mode -> smoothed amplitude mode.
    Saves every image and the run parameters. Does NOT use auto_expose()
    -- see mode 4. minE is not exercised here (not useful for this rig's
    purposes) -- still covered by mode 3's second stream. rawIQ's
    offset_I/offset_Q source is controlled by ``--offset-method``
    (self/null, default self) -- see mode2_lockin()'s docstring.

Mode 3 -- streaming:
    open -> steady mode at a fixed exposure -> live matplotlib preview at up
    to 10 fps (throttled to the camera's own estimated acquire time if
    slower) with Pause / Start / Save frame / Move on buttons -> switch to
    amplitude mode -> stream again. Does NOT use auto_expose() -- see mode 4.
    Uses cam.set_streaming_params()/cam.acquire_light() instead of
    set_measurement_mode()/acquire_single() -- the latter flushes before
    every acquisition, which in volume modes (SensNFrames=256) costs a
    full extra acquisition per displayed frame (confirmed on real
    hardware: ~2x the predicted per-frame time). acquire_light() flushes
    once at set_streaming_params() time instead of on every call.

Mode 4 -- auto_expose() checkout:
    open -> steady mode -> gain=1x (DdsGain=2) -> auto_expose() -> record
    the full search trial table + final frame. The only mode that calls
    auto_expose() -- exercises/verifies it on real hardware in isolation
    rather than buried inside another mode's pipeline (modes 1/2/3 all use
    fixed exposures instead). auto_expose() detects saturation via the
    channel0/channel1 ratio (see helicamC3_practical_knowledge_base.md #3),
    not an absolute intensity threshold -- see its docstring in helicam.py.

Mode 5 -- SensNFrames sweep:
    open -> steady mode -> gain=1x (DdsGain=2) -> t_acquire_us=1.0 (the
    exposure auto_expose()'s first trial used in mode 4) -> sweep
    SensNFrames geometrically 32 -> 256, one acquisition each -> record
    peak intensity. data_reformat() averages (not sums) over frames for
    CamMode 3 (see its CamMode-3 branch), so max_val should come out flat
    across this sweep -- this mode is the hardware check for that.

Mode 6 -- SensExpRatio sweep:
    open -> steady mode -> gain=1x (DdsGain=2) -> fixed short exposure ->
    sweep SensExpRatio over all 4 values (1:2, 1:4, 1:8, 1:16 short:long,
    manual §5.4) -> save the raw (pre-data_reformat()) I/Q pair for each via
    cam.save_raw_np(), and compare channel 0 vs channel 1 magnitude. In
    CamMode 3, channels I/Q are NOT lock-in components (manual §5.4: "not
    demodulated signals ... generated on the two channels I and Q") -- they
    are the short- and long-exposure images of the same HDR pair, so this
    checks which channel is which and how strongly SensExpRatio separates
    them (channel 0 was eyeballed ~10x stronger than channel 1 in an
    earlier capture, at whatever SensExpRatio that run happened to use).

Mode 7 -- no-flush raw sequence (is flush() actually needed, and how much):
    open -> steady mode -> gain=1x (DdsGain=2) -> condition the pipeline at
    a fixed exposure with one real flush() -> switch exposure to a very
    different value -> immediately acquire several raw frames back-to-back
    with **no flush() at all** in between, via ``cam._acquire()`` directly
    (``acquire_single()``/``acquire_avg()``/``save_raw_np()`` all call
    flush() internally, which would defeat the point here). Saves every raw
    frame plus a per-frame channel0/channel1 summary, so a stale first frame
    (still reflecting the old exposure) shows up as an outlier before the
    sequence settles -- see auto_expose()'s per-trial flush() cost in
    TODO.md #1b for why this matters.

Mode 8 -- smooth_amplitude FWHMnFrame effectiveness sweep:
    open -> steady mode -> gain=1x (DdsGain=2) -> fixed exposure -> for a
    CamMode-1 "amplitude" baseline (FWHMnFrame off) and every FWHMnFrame
    value (0-4), acquire several *independent* repeat acquisitions
    back-to-back and compute the per-pixel std across those repeats --
    genuine inter-acquisition noise, the one thing a single acquisition's
    own full-stack averaging can't show. data_reformat() already averages
    the entire SensNFrames stack down to one frame regardless of
    FWHMnFrame (see its CamMode 1/2 docstring in helicam.py), so whether
    the on-device matched filter buys anything beyond that Python-side
    averaging is an open, TODO.md #3, empirical question -- this mode is
    how to answer it on real hardware.

Mode 9 -- ExtTqp lock check (PEM 2f reference on the heliDriver encoder input):
    rawIQ burst on the internal clock (reference + offset map), then the
    same burst with ExtTqp=1. Estimates the external demod frequency from
    acquisition timing and checks that the demodulated I/Q vector is
    coherent frame-to-frame (locked) rather than noise. Restores ExtTqp=0
    afterwards. Rerun with the PEM retardation at 0 and --note pem_off as
    the control. See mode9_exttqp_lock()'s docstring.

This script owns all visualization/GUI/file-IO weight -- ``helicam.py``
stays a plain (non-GUI) device driver; see device_interface_instruction.md.
"""

import argparse
import csv
import glob
import json
import logging
import os
import threading
import time

import matplotlib
matplotlib.use("qtagg")
import matplotlib.pyplot as plt
from matplotlib.widgets import Button
import numpy as np

from moke.devices.helicam import HeliCamC3

_LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s:%(name)s:%(message)s"
_LOG_DATEFMT = "%H:%M:%S"

logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, datefmt=_LOG_DATEFMT)
_log = logging.getLogger(__name__)

DEFAULT_T_ACQUIRE_US = 10.0
# Fixed log-spaced exposure sweep for mode 1 (1us, then 2..64us doubling) --
# see mode1_lifecycle() for why this replaced an auto_expose()-driven search.
DEFAULT_MODE1_T_ACQUIRE_US_LIST = (1.0,) + tuple(round(t) for t in np.geomspace(2.0, 64.0, num=6))

# Mode 5: geometric SensNFrames sweep, 32 -> 64 -> 128 -> 256 (doubling each
# step), at the fixed 1us exposure auto_expose()'s first trial used in mode 4.
DEFAULT_MODE5_SENSNFRAMES_LIST = tuple(int(round(n)) for n in np.geomspace(32, 256, num=10))
DEFAULT_MODE5_T_ACQUIRE_US = 1.0

# Mode 6: all 4 SensExpRatio settings (register description §2.13:
# 0=1:2, 1=1:4, 2=1:8, 3=1:16 short:long), at the same fixed 1us short
# exposure mode 5 used.
DEFAULT_MODE6_SENSEXPRATIO_LIST = (0, 1, 2, 3)
DEFAULT_MODE6_T_ACQUIRE_US = 1.0

# Mode 7: condition at a low exposure, switch to a much higher one, then
# acquire several raw frames with no flush() at all -- a small SensNFrames
# keeps each acquisition (and thus the whole no-flush sequence) fast.
DEFAULT_MODE7_T_OLD_US = 16.0
DEFAULT_MODE7_T_NEW_US = 2.0
DEFAULT_MODE7_SENSNFRAMES = 32
DEFAULT_MODE7_N_ACQUISITIONS = 6

# Mode 8: FWHMnFrame register codes (SMOOTH_AMPLITUDE_SETTINGS's comment,
# manual §5.2.2): 0=no filter, 1=2 frames, 2=6 frames, 3=10 frames,
# 4=20 frames. n_repeats independent acquisitions per value -- the whole
# point is measuring repeat-to-repeat (inter-acquisition) noise, which one
# acquisition alone can't show. Exposure comes from --t-acquire-us
# (DEFAULT_T_ACQUIRE_US), same as modes 2/3, not a separate default here.
DEFAULT_MODE8_FWHM_LIST = (0, 1, 2, 3, 4)
DEFAULT_MODE8_N_REPEATS = 4


def _timed(label: str, fn, *args, level: int = logging.INFO, **kwargs):
    """
    Run ``fn(*args, **kwargs)``, log how long it took, and return its result.

    This is how "how fast is each camera instruction" gets answered --
    ``helicam.py`` itself stays free of timing/instrumentation code (it's a
    device driver, not a profiler); all per-call timing lives here instead.
    """
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    _log.log(level, "[%7.1f ms] %s", dt_ms, label)
    return result


# ----------------------------------------------------------------------
# Output folder / file helpers
# ----------------------------------------------------------------------

def make_test_dir(base_dir: str = None) -> str:
    """Create and return the next ``helicam_test_NNN`` folder under ``base_dir``."""
    base_dir = base_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "helicam_test_data")
    os.makedirs(base_dir, exist_ok=True)

    existing = glob.glob(os.path.join(base_dir, "helicam_test_*"))
    nums = []
    for path in existing:
        suffix = os.path.basename(path).replace("helicam_test_", "")
        if suffix.isdigit():
            nums.append(int(suffix))
    next_n = max(nums, default=-1) + 1

    out_dir = os.path.join(base_dir, f"helicam_test_{next_n:03d}")
    os.makedirs(out_dir)
    _log.info("Test output directory: %s", out_dir)
    return out_dir


def add_file_logging(out_dir: str, filename: str = "run_log.txt") -> str:
    """
    Mirror all logging (this script's and ``moke.devices.helicam``'s) into
    a text file inside ``out_dir``, in addition to the console.

    Attaches to the root logger rather than just ``_log`` so
    ``helicam.py``'s own INFO/WARNING lines (register writes, auto_expose
    trials, etc.) end up in the file too -- everything needed to reconstruct
    what a run did lives with that run's data, not just on screen.
    """
    path = os.path.join(out_dir, filename)
    handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
    logging.getLogger().addHandler(handler)
    _log.info("Logging to %s", path)
    return path


def save_frame(out_dir: str, name: str, frame: np.ndarray) -> None:
    if frame is None:
        _log.warning("save_frame(%s): frame is None, skipping", name)
        return
    np.save(os.path.join(out_dir, name + ".npy"), frame)


def save_table(out_dir: str, name: str, rows: list) -> None:
    if not rows:
        _log.warning("save_table(%s): no rows to save", name)
        return
    path = os.path.join(out_dir, name + ".csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    _log.info("Wrote %s (%d rows)", path, len(rows))


def save_json(out_dir: str, name: str, data: dict) -> None:
    with open(os.path.join(out_dir, name + ".json"), "w") as f:
        json.dump(data, f, indent=2, default=str)


def amplitude_channel(frame: np.ndarray) -> np.ndarray:
    """Amplitude image for display -- surface modes are (H, W, 2); pass 2D frames through."""
    return frame[..., 0] if frame.ndim == 3 else frame


# ----------------------------------------------------------------------
# Mode 1 -- lifecycle, parameters, exposure/gain characterization
# ----------------------------------------------------------------------

def mode1_lifecycle(cam: HeliCamC3, out_dir: str, t_acquire_us_list) -> None:
    """
    Fixed gain=1x (best SNR, DdsGain=2), fixed log-spaced exposure sweep --
    no auto_expose(). auto_expose() has two known bugs (see
    open_issue_helicam.md #9: its "never reached target" fallback returns
    the last, failed trial instead of the best real one, and nothing
    resyncs the acquisition pipeline after a timeout, so one bad trial can
    wedge every trial after it) that made a real bench run come back with
    every "optimal frame" as None. Bypass it entirely until those are fixed.
    """
    _timed("set_measurement_mode('steady')", cam.set_measurement_mode, "steady")
    _timed("set_gain(1.0)", cam.set_gain, 1.0)

    rows = []
    frames = {}
    for t_us in t_acquire_us_list:
        _timed(f"set_acquire_time({t_us})", cam.set_acquire_time, t_us)
        frame = _timed(f"acquire_single() [t={t_us:g}us]", cam.acquire_single)
        save_frame(out_dir, f"mode1_t{t_us:g}us_frame", frame)
        frames[t_us] = frame
        max_val = float(frame.max()) if frame is not None else None
        rows.append({"t_acquire_us": t_us, "analogue_gain": 1.0, "max_val": max_val})
        _log.info("Mode 1: t_acquire_us=%.1f -> max=%s", t_us, max_val)

    save_table(out_dir, "mode1_exposure_table", rows)

    fig, axes = plt.subplots(1, len(t_acquire_us_list), figsize=(4 * len(t_acquire_us_list), 4))
    if len(t_acquire_us_list) == 1:
        axes = [axes]
    for ax, t_us in zip(axes, t_acquire_us_list):
        frame = frames[t_us]
        if frame is not None:
            im = ax.imshow(frame, cmap="gray")
            fig.colorbar(im, ax=ax)
        ax.set_title(f"t={t_us:g}us")
    fig.suptitle("Mode 1: exposure sweep (gain=1x)")
    fig.savefig(os.path.join(out_dir, "mode1_summary.png"))
    plt.show()


# ----------------------------------------------------------------------
# Mode 2 -- lock-in detection (rawIQ + amplitude + smooth_amplitude)
# ----------------------------------------------------------------------

def mode2_lockin(cam: HeliCamC3, out_dir: str, t_acquire_us: float, offset_method: str = "self") -> None:
    """
    Fixed exposure -> steady frame -> rawIQ (converted to amplitude) ->
    amplitude mode -> smoothed amplitude mode. Saves every image and the
    run parameters.

    minE is deliberately not exercised here -- not useful for this rig's
    purposes (still covered by mode 3's second stream). This mode instead
    covers the three amplitude-producing paths side by side: rawIQ's raw
    I/Q converted in Python (``iq_to_amp_phase()``) vs. CamMode 1's
    on-device amplitude vs. CamMode 2's on-device FWHMnFrame-filtered
    ("smoothed") amplitude -- useful for comparing whether the on-device
    smoothing actually buys anything over the raw computation.

    Parameters
    ----------
    offset_method:
        How to determine ``offset_I``/``offset_Q`` for rawIQ's
        ``iq_to_amp_phase()`` conversion -- CamMode 0 has no on-device
        offset correction (``OffsetMethod`` doesn't apply to it, register
        description §2.18), so the manual's nominal 512 leaves a large
        per-camera residual (measured ~88/~67 counts off on this camera --
        see helicamC3_practical_knowledge_base.md). Two options, to A/B
        against each other:
        "self": use this same capture's own per-pixel I/Q mean as a
            single scalar offset -- free (no extra acquisition), but
            assumes there's no real slow-varying signal riding on top of
            the DC bias in this exact frame.
        "null": call ``cam.null_offset()`` for a dedicated, per-pixel
            calibration acquisition just before the real capture -- only
            actually different from "self" if there's genuinely no
            modulated signal present while it runs (light blocked / demod
            frequency detuned); otherwise it just measures the same
            signal-plus-offset a second time.
    """
    if offset_method not in ("self", "null"):
        raise ValueError(f"offset_method must be 'self' or 'null', got {offset_method!r}")

    # set_measurement_mode() now discards its own warm-up acquisition by
    # default (settling artifact confirmed on real hardware -- see
    # helicamC3_practical_knowledge_base.md), so the manual
    # discard-first-acquisition workaround that used to live here is gone.
    _timed("set_measurement_mode('steady', SensExpRatio=1)",
           cam.set_measurement_mode, "steady", SensExpRatio=1)  # start with ratio = 4
    _timed("set_gain(1.0)", cam.set_gain, 1.0)
    _timed(f"set_acquire_time({t_acquire_us})", cam.set_acquire_time, t_acquire_us)
    cam.dump_registers(out_dir, "mode2_registers_at_start")
    steady_frame = _timed("acquire_single() [steady]", cam.acquire_single)
    save_frame(out_dir, "mode2_steady_frame", steady_frame)

    _timed("set_measurement_mode('rawIQ')", cam.set_measurement_mode, "rawIQ")

    if offset_method == "null":
        _log.info("Mode 2: measuring null_offset() -- make sure no modulated "
                   "signal is present (light blocked / demod detuned) right now")
        offset_I, offset_Q = _timed("null_offset()", cam.null_offset)

    raw_iq = _timed("acquire_single() [rawIQ]", cam.acquire_single)   # (292, 280, 2) float64, frame-averaged: [...,0]=I, [...,1]=Q
    if raw_iq is None:
        raise RuntimeError("mode2: rawIQ acquire_single() returned no data")
    I, Q = raw_iq[..., 0], raw_iq[..., 1]

    if offset_method == "self":
        offset_I, offset_Q = float(I.mean()), float(Q.mean())

    rawiq_amplitude, rawiq_phase = HeliCamC3.iq_to_amp_phase(I, Q, offset_I=offset_I, offset_Q=offset_Q)
    save_frame(out_dir, "mode2_rawiq_I", I)
    save_frame(out_dir, "mode2_rawiq_Q", Q)
    save_frame(out_dir, "mode2_rawiq_amplitude", rawiq_amplitude)
    save_frame(out_dir, "mode2_rawiq_phase", rawiq_phase)
    _log.info(
        "Mode 2: rawIQ amplitude -- offset_method=%s (offset_I=%.1f, offset_Q=%.1f) "
        "shape=%s mean=%.1f",
        offset_method, np.mean(offset_I), np.mean(offset_Q),
        rawiq_amplitude.shape, rawiq_amplitude.mean(),
    )

    _timed("set_measurement_mode('amplitude')", cam.set_measurement_mode, "amplitude")
    amplitude_frame = _timed("acquire_single() [amplitude]", cam.acquire_single)   # (292, 280) float32, frame-averaged
    if amplitude_frame is None:
        raise RuntimeError("mode2: amplitude acquire_single() returned no data")
    save_frame(out_dir, "mode2_amplitude_frame", amplitude_frame)
    _log.info("Mode 2: amplitude -- mean=%.1f", amplitude_frame.mean())

    _timed("set_measurement_mode('smooth_amplitude')", cam.set_measurement_mode, "smooth_amplitude")
    cam.dump_registers(out_dir, "mode2_registers_before_smooth_amplitude")
    smooth_amplitude_frame = _timed("acquire_single() [smooth_amplitude]", cam.acquire_single)   # (292, 280) float32, frame-averaged
    if smooth_amplitude_frame is None:
        raise RuntimeError("mode2: smooth_amplitude acquire_single() returned no data")
    save_frame(out_dir, "mode2_smooth_amplitude_frame", smooth_amplitude_frame)
    _log.info("Mode 2: smooth amplitude -- mean=%.1f", smooth_amplitude_frame.mean())
    cam.set_attributes(AcqStop = 1) # stop acquisition
    save_json(out_dir, "mode2_params", {
        "t_acquire_us": t_acquire_us,
        "gain_DdsGain": cam.get_attribute("DdsGain"),
        "FWHMnFrame": cam.SMOOTH_AMPLITUDE_SETTINGS["FWHMnFrame"],
        "offset_method": offset_method,
        "offset_I_mean": float(np.mean(offset_I)),
        "offset_Q_mean": float(np.mean(offset_Q)),
    })

    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    axes = axes.flatten()
    for ax, (title, img) in zip(axes, [
        ("steady", steady_frame),
        ("rawIQ I", I),
        ("rawIQ Q", Q),
        ("rawIQ amplitude", rawiq_amplitude),
        ("rawIQ phase", rawiq_phase),
        ("amplitude", amplitude_frame),
        ("smooth amplitude", smooth_amplitude_frame),
    ]):
        im = ax.imshow(img, cmap="gray")
        ax.set_title(title)
        fig.colorbar(im, ax=ax)
    fig.suptitle(f"Mode 2: lock-in detection (offset_method={offset_method}, "
                 f"offset_I={np.mean(offset_I):.1f}, offset_Q={np.mean(offset_Q):.1f})")
    fig.savefig(os.path.join(out_dir, "mode2_summary.png"))
    plt.show()


# ----------------------------------------------------------------------
# Mode 3 -- streaming preview with Pause/Start/Save/Move-on controls
# ----------------------------------------------------------------------

class _StreamControls:
    def __init__(self):
        self.paused = False
        self.running = True
        self.save_requested = False

    def on_pause(self, _event):
        self.paused = True

    def on_start(self, _event):
        self.paused = False

    def on_save(self, _event):
        self.save_requested = True

    def on_move_on(self, _event):
        self.running = False


class _StreamAccumulator:
    """
    Thread-safe handoff point between the background acquisition thread
    and the GUI thread. The acquisition thread calls ``add()`` for every
    real frame it gets; the GUI thread calls ``pop_average()`` once per
    redraw, which returns the mean of everything accumulated since the
    last call (and resets) -- so a slow plot never throttles acquisition,
    and a fast plot just sees fewer frames averaged together per redraw.

    ``total_count``/``start_time`` are never reset -- they're what
    ``measurement_fps`` is based on, giving a stable, GUI-refresh-
    independent measurement rate instead of a noisy per-redraw one.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._pending_sum = None
        self._pending_count = 0
        self.total_count = 0
        self.start_time = time.monotonic()

    def add(self, frame: np.ndarray) -> None:
        with self._lock:
            if self._pending_sum is None:
                self._pending_sum = frame.astype(np.float64)
            else:
                self._pending_sum += frame
            self._pending_count += 1
            self.total_count += 1

    def pop_average(self):
        """Return (average_frame, n_averaged) since the last call, or (None, 0)."""
        with self._lock:
            if self._pending_count == 0:
                return None, 0
            avg = self._pending_sum / self._pending_count
            n = self._pending_count
            self._pending_sum = None
            self._pending_count = 0
            return avg, n

    @property
    def measurement_fps(self) -> float:
        dt = time.monotonic() - self.start_time
        return self.total_count / dt if dt > 0 else 0.0


def _acquire_worker(frames, label: str, controls: _StreamControls,
                     acc: _StreamAccumulator) -> None:
    """
    Background thread: pulls frames from ``cam.stream()`` as fast as
    possible -- no plotting, no pacing, nothing GUI-related. This is what
    decouples measurement rate from plotting rate. Stops when
    ``controls.running`` goes False (set by the "Move on" button, the
    window closing, or a fatal acquisition error here).
    """
    try:
        for frame in frames:
            while controls.paused and controls.running:
                time.sleep(0.01)
            if not controls.running:
                break
            acc.add(frame)
    except Exception:
        _log.exception("stream(%s): cam.stream() raised, stopping stream", label)
    controls.running = False


def stream(frames, first_frame, out_dir: str, label: str, fps: float = 10.0) -> None:
    """
    Live preview loop. Not fancy -- this is a manual bench test tool, not a
    product UI. Pause/Start/Save/Move on buttons; closing the window also
    ends the stream.

    ``frames`` is a ``cam.stream(...)`` generator that has already yielded
    ``first_frame`` (the caller pulls it, so the camera is configured
    before this window opens).

    Acquisition runs on a background thread (see ``_acquire_worker()``) as
    fast as ``cam.stream()`` allows -- the GUI thread never throttles
    it. Each redraw pulls whatever frames accumulated since the last one
    and displays their mean (``_StreamAccumulator``), so plotting cost
    never limits the measurement rate. The title shows both numbers
    separately: "measurement fps" (real acquisition rate, GUI-independent)
    and how many frames were averaged into the frame just plotted.

    Parameters
    ----------
    fps:
        Requested GUI redraw rate. Display-only -- does not throttle
        acquisition. None redraws as fast as the GUI event loop allows.
    """
    controls = _StreamControls()
    acc = _StreamAccumulator()

    img = amplitude_channel(first_frame)
    last_frame = first_frame

    fig, ax = plt.subplots()
    plt.subplots_adjust(bottom=0.25)
    im = ax.imshow(img, cmap="gray")
    title = ax.set_title(f"{label} | frame 0")
    fig.colorbar(im, ax=ax)

    b_pause = Button(plt.axes([0.1, 0.05, 0.15, 0.075]), "Pause")
    b_start = Button(plt.axes([0.3, 0.05, 0.15, 0.075]), "Start")
    b_save = Button(plt.axes([0.5, 0.05, 0.15, 0.075]), "Save frame")
    b_moveon = Button(plt.axes([0.7, 0.05, 0.15, 0.075]), "Move on")
    b_pause.on_clicked(controls.on_pause)
    b_start.on_clicked(controls.on_start)
    b_save.on_clicked(controls.on_save)
    b_moveon.on_clicked(controls.on_move_on)

    worker = threading.Thread(
        target=_acquire_worker, args=(frames, label, controls, acc),
        name=f"stream-{label}-acquire", daemon=True,
    )
    worker.start()

    plot_interval_s = 0.0 if fps is None else 1.0 / fps
    n_plotted = 0
    while controls.running and plt.fignum_exists(fig.number):
        loop_start = time.monotonic()

        avg_frame, n_new = acc.pop_average()
        if avg_frame is not None:
            last_frame = avg_frame
            img = amplitude_channel(avg_frame)
            im.set_data(img)
            im.set_clim(img.min(), img.max())
            n_plotted += 1
        title.set_text(
            f"{label} | plotted {n_plotted} (avg of {n_new}) | "
            f"measurement {acc.measurement_fps:.2f} fps | total {acc.total_count}"
        )

        if controls.save_requested:
            save_frame(out_dir, f"mode3_{label}_frame_{n_plotted:04d}", last_frame)
            controls.save_requested = False

        fig.canvas.draw_idle()
        fig.canvas.flush_events()
        remaining = plot_interval_s - (time.monotonic() - loop_start)
        plt.pause(max(remaining, 0.001))

    controls.running = False   # in case the window was closed rather than "Move on" clicked
    worker.join(timeout=5.0)
    if worker.is_alive():
        _log.warning("stream(%s): acquire worker did not stop within 5s", label)

    if acc.total_count > 0:
        _log.info("stream(%s): %d measurements in %.2fs -- average %.2f fps (measurement rate, GUI-independent)",
                   label, acc.total_count, time.monotonic() - acc.start_time, acc.measurement_fps)
    plt.close(fig)


def mode3_streaming(cam: HeliCamC3, out_dir: str, t_acquire_us: float) -> None:
    # Single, clean configure -- no redundant prior set_measurement_mode()
    # call, no manual set_attributes(), no extra flush(). Isolates whether
    # n_frames=32 itself is the problem, or whether it was the preceding
    # back-to-back reconfigure (with SensNFrames changing 256->32) that
    # broke the second call -- see run 020-024 logs, which all show the
    # *first* configure succeeding and the *second* one timing out.
    # t_acquire_us is unused here: set_acquire_time() only affects CamMode 3
    # (knowledge base §10).
    frames = cam.stream("smooth_amplitude", n_frames=16, SensNavM2=128)
    first_frame = _timed("cam.stream() configure + first frame", next, frames)
    cam.dump_registers(out_dir, "mode3_registers_before_amp_stream")
    stream(frames, first_frame, out_dir, "smooth_amplitude", fps=3.0)  # GUI redraw rate only -- measurement is unthrottled


# ----------------------------------------------------------------------
# Mode 4 -- auto_expose() checkout in steady mode
# ----------------------------------------------------------------------

def mode4_autoexpose(cam: HeliCamC3, out_dir: str, target_fraction: float) -> None:
    """
    Fixed gain=1x (best SNR, DdsGain=2) -> auto_expose() -> record its full
    search trial table plus the final frame at the exposure it settled on.

    The only mode that calls auto_expose() -- modes 1/2/3 all use fixed
    exposures instead -- so its search behaviour can be checked against
    real hardware in isolation. auto_expose() detects saturation via
    the channel0/channel1 ratio (see
    helicamC3_practical_knowledge_base.md #3) instead of an absolute
    intensity threshold -- this mode's plot shows that ratio holding near
    SensExpRatio's nominal value, then dropping once channel 0 (long
    exposure) starts clipping.
    """
    _timed("set_measurement_mode('steady')", cam.set_measurement_mode, "steady")
    _timed("set_gain(1.0)", cam.set_gain, 1.0)

    cam.dump_registers(out_dir, "mode4_registers_before_autoexpose")
    result = _timed("auto_expose()", cam.auto_expose, target_fraction=target_fraction)
    cam.dump_registers(out_dir, "mode4_registers_after_autoexpose")
    _log.info(
        "Mode 4: auto_expose -> t_acquire_us=%.1f, t_saturation_onset_us=%s, "
        "floor_limited=%s, ceiling_not_found=%s, %d trial(s)",
        result["t_acquire_us"], result["t_saturation_onset_us"],
        result["floor_limited"], result["ceiling_not_found"], len(result["table"]),
    )

    save_table(out_dir, "mode4_autoexpose_table", result["table"])
    save_json(out_dir, "mode4_autoexpose_result", {
        "target_fraction": target_fraction,
        "t_acquire_us": result["t_acquire_us"],
        "t_saturation_onset_us": result["t_saturation_onset_us"],
        "nominal_ratio": result["nominal_ratio"],
        "floor_limited": result["floor_limited"],
        "ceiling_not_found": result["ceiling_not_found"],
        "n_trials": len(result["table"]),
        "gain_DdsGain": cam.get_attribute("DdsGain"),
    })

    frame = _timed("acquire_single() [final, post auto_expose]", cam.acquire_single)
    save_frame(out_dir, "mode4_final_frame", frame)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    trials = [row for row in result["table"] if row["ratio"] is not None]
    axes[0].plot([row["t_acquire_us"] for row in trials], [row["ratio"] for row in trials], "o-")
    axes[0].axhline(result["nominal_ratio"], color="gray", linestyle="--", label="nominal ratio")
    if result["t_saturation_onset_us"] is not None:
        axes[0].axvline(result["t_saturation_onset_us"], color="red", linestyle=":", label="saturation onset")
    axes[0].axvline(result["t_acquire_us"], color="green", linestyle=":", label="chosen t_acquire_us")
    axes[0].set_xscale("log")
    axes[0].set_xlabel("t_acquire_us")
    axes[0].set_ylabel("channel0 / channel1 ratio")
    axes[0].set_title("auto_expose() search trials")
    axes[0].legend()
    if frame is not None:
        im = axes[1].imshow(frame, cmap="gray")
        fig.colorbar(im, ax=axes[1])
    axes[1].set_title(f"final frame, t={result['t_acquire_us']:.1f}us")
    fig.suptitle("Mode 4: auto_expose() checkout")
    fig.savefig(os.path.join(out_dir, "mode4_summary.png"))
    plt.show()


# ----------------------------------------------------------------------
# Mode 5 -- SensNFrames sweep (does peak intensity scale with frame count?)
# ----------------------------------------------------------------------

def mode5_frames_sweep(cam: HeliCamC3, out_dir: str, t_acquire_us: float, sensnframes_list) -> None:
    """
    Fixed gain=1x (DdsGain=2) and exposure -> sweep SensNFrames geometrically
    -> record peak intensity for each.

    ``to_numpy()`` averages (not sums) over frames for CamMode 3, so
    ``max_val`` should come out flat across this sweep -- this mode exists
    to check that on real hardware.

    ``set_measurement_mode("steady", SensNFrames=n)`` is used (not a bare
    ``set_attributes``) so AllocCamData's buffer is resized to match each N --
    a stale buffer size for a changed SensNFrames is a real vendor-wrapper
    footgun here, not a hypothetical one.
    """
    _timed("set_measurement_mode('steady')", cam.set_measurement_mode, "steady")
    _timed("set_gain(1.0)", cam.set_gain, 1.0)

    full_scale = 2 * HeliCamC3.SENSOR_ADC_MAX
    rows = []
    frames = {}
    for n_frames in sensnframes_list:
        _timed(f"set_measurement_mode('steady', SensNFrames={n_frames})",
               cam.set_measurement_mode, "steady", SensNFrames=n_frames)
        _timed(f"set_acquire_time({t_acquire_us})", cam.set_acquire_time, t_acquire_us)
        frame = _timed(f"acquire_single() [SensNFrames={n_frames}]", cam.acquire_single)
        save_frame(out_dir, f"mode5_n{n_frames}_frame", frame)
        frames[n_frames] = frame

        max_val = float(np.percentile(frame, 99.99)) if frame is not None else None
        rows.append({
            "sens_n_frames": n_frames,
            "t_acquire_us": t_acquire_us,
            "max_val": max_val,
            "full_scale": full_scale,
            "frac": (max_val / full_scale) if max_val is not None else None,
        })
        _log.info("Mode 5: SensNFrames=%d -> max_val=%s", n_frames, max_val)

    save_table(out_dir, "mode5_frames_sweep_table", rows)

    fig1, axes1 = plt.subplots(1, len(sensnframes_list), figsize=(4 * len(sensnframes_list), 4))
    if len(sensnframes_list) == 1:
        axes1 = [axes1]
    for ax, n_frames in zip(axes1, sensnframes_list):
        frame = frames[n_frames]
        if frame is not None:
            im = ax.imshow(frame, cmap="gray")
            fig1.colorbar(im, ax=ax)
        ax.set_title(f"N={n_frames}")
    fig1.suptitle(f"Mode 5: SensNFrames sweep (gain=1x, t={t_acquire_us:g}us)")
    fig1.savefig(os.path.join(out_dir, "mode5_frames_summary.png"))

    ns = [row["sens_n_frames"] for row in rows]
    peaks = [row["max_val"] for row in rows]

    fig2, ax2 = plt.subplots(figsize=(6, 4))
    ax2.plot(ns, peaks, "o-")
    ax2.set_xscale("log")
    ax2.set_xlabel("SensNFrames")
    ax2.set_ylabel("peak intensity (99.99th pct)")
    ax2.set_title("Mode 5: peak intensity vs SensNFrames (expect flat)")
    fig2.savefig(os.path.join(out_dir, "mode5_peak_intensity.png"))
    plt.show()


# ----------------------------------------------------------------------
# Mode 6 -- SensExpRatio sweep (channel 0 vs channel 1 magnitude)
# ----------------------------------------------------------------------

def mode6_sensexpratio_sweep(cam: HeliCamC3, out_dir: str, t_acquire_us: float, ratio_list) -> None:
    """
    Fixed gain=1x (DdsGain=2) and short exposure -> sweep SensExpRatio over
    all 4 values -> save the raw (pre-data_reformat()) I/Q pair for each and
    compare channel 0 vs channel 1 magnitude.

    Uses cam.save_raw_np() (not acquire_single()) because data_reformat()
    sums the two channels together for CamMode 3 -- exactly the distinction
    this sweep needs to keep separate. Dark-subtracts the same way
    data_reformat() does (first SensNDarkFrames averaged as baseline,
    subtracted from the rest) before comparing channel magnitudes.
    """
    _timed("set_measurement_mode('steady')", cam.set_measurement_mode, "steady")
    _timed("set_gain(1.0)", cam.set_gain, 1.0)
    n_dark = cam.STEADY_SETTINGS["SensNDarkFrames"]
    ratio_labels = {0: "1:2", 1: "1:4", 2: "1:8", 3: "1:16"}

    rows = []
    channel_images = {}   # ratio -> (300, 300, 2) dark-subtracted, frame-averaged
    for ratio in ratio_list:
        _timed(f"set_measurement_mode('steady', SensExpRatio={ratio})",
               cam.set_measurement_mode, "steady", SensExpRatio=ratio)
        _timed(f"set_acquire_time({t_acquire_us})", cam.set_acquire_time, t_acquire_us)
        path = _timed(f"save_raw_np() [SensExpRatio={ratio}]",
                       cam.save_raw_np, out_dir, f"mode6_ratio{ratio}_raw")
        if path is None:
            _log.warning("Mode 6: SensExpRatio=%d acquire failed, skipping", ratio)
            continue

        with np.load(path) as npz:
            arr = npz["data"].view(np.int16).astype(np.float64)   # (n_frames, 300, 300, 2)
        dark_ref = arr[:n_dark].mean(axis=0)
        useful = (arr[n_dark:] - dark_ref[np.newaxis, ...]).mean(axis=0)   # (300, 300, 2)
        channel_images[ratio] = useful

        ch0_mean, ch1_mean = float(useful[..., 0].mean()), float(useful[..., 1].mean())
        rows.append({
            "sens_exp_ratio": ratio,
            "short_long_ratio": ratio_labels[ratio],
            "t_acquire_us": t_acquire_us,
            "channel0_mean": ch0_mean,
            "channel1_mean": ch1_mean,
            "channel0_over_channel1": (ch0_mean / ch1_mean) if ch1_mean else None,
        })
        _log.info("Mode 6: SensExpRatio=%d (%s) -> channel0=%.2f, channel1=%.2f",
                   ratio, ratio_labels[ratio], ch0_mean, ch1_mean)

    save_table(out_dir, "mode6_sensexpratio_table", rows)

    fig, axes = plt.subplots(2, len(ratio_list), figsize=(4 * len(ratio_list), 8))
    if len(ratio_list) == 1:
        axes = axes.reshape(2, 1)
    for col, ratio in enumerate(ratio_list):
        img = channel_images.get(ratio)
        if img is None:
            continue
        im0 = axes[0, col].imshow(img[..., 0], cmap="gray")
        fig.colorbar(im0, ax=axes[0, col])
        axes[0, col].set_title(f"SensExpRatio={ratio} ({ratio_labels[ratio]}) ch0")
        im1 = axes[1, col].imshow(img[..., 1], cmap="gray")
        fig.colorbar(im1, ax=axes[1, col])
        axes[1, col].set_title(f"SensExpRatio={ratio} ({ratio_labels[ratio]}) ch1")
    fig.suptitle(f"Mode 6: SensExpRatio sweep, t={t_acquire_us:g}us (dark-subtracted, frame-averaged)")
    fig.savefig(os.path.join(out_dir, "mode6_summary.png"))
    plt.show()


# ----------------------------------------------------------------------
# Mode 7 -- no-flush raw sequence
# ----------------------------------------------------------------------

def mode7_no_flush_raw(cam: HeliCamC3, out_dir: str, t_old_us: float, t_new_us: float,
                        sensnframes: int, n_acquisitions: int) -> None:
    """
    Find out whether -- and for how many frames -- ``flush()`` is actually
    needed, by removing it entirely from the one place it's meant to
    matter: right after an exposure change.

    Conditions the pipeline at ``t_old_us`` with one real ``flush()`` (a
    known-clean starting point), switches to ``t_new_us``, then acquires
    ``n_acquisitions`` raw frames back-to-back with **no flush() call
    anywhere in between** -- straight ``cam._acquire()``, bypassing
    ``acquire_single()``/``acquire_avg()``/``save_raw_np()``, all three of
    which call ``flush()`` internally and would hide the effect being
    tested. If the first acquisition (or first few) still reflects
    ``t_old_us``'s magnitude before the rest settle onto ``t_new_us``'s,
    that's the stale-frame problem flush() exists for, and how many frames
    it actually takes to clear; if every frame already looks like
    ``t_new_us``, flush() isn't buying anything at this boundary.
    """
    _timed(f"set_measurement_mode('steady', SensNFrames={sensnframes})",
           cam.set_measurement_mode, "steady", SensNFrames=sensnframes)
    _timed("set_gain(1.0)", cam.set_gain, 1.0)

    _timed(f"set_acquire_time({t_old_us}) [condition]", cam.set_acquire_time, t_old_us)
    cam.flush()
    warm = cam._acquire()
    _log.info("Mode 7: conditioning acquisition at t_old_us=%.1f done (data=%s)",
               t_old_us, "None" if warm is None else warm.shape)

    _timed(f"set_acquire_time({t_new_us}) [switch, no flush after this]",
           cam.set_acquire_time, t_new_us)

    n_dark = cam.STEADY_SETTINGS["SensNDarkFrames"]
    rows = []
    for i in range(n_acquisitions):
        t0 = time.perf_counter()
        data = cam._acquire()
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if data is None:
            _log.warning("Mode 7: acquisition %d failed (%.1f ms)", i, dt_ms)
            rows.append({"index": i, "t_ms": dt_ms, "ch0_mean": None, "ch1_mean": None})
            continue
        np.savez(os.path.join(out_dir, f"mode7_noflush_raw{i}.npz"),
                 data=data, cam_mode=cam._current_cammode)
        arr = data.view(np.int16).astype(np.float64)
        dark_ref = arr[:n_dark].mean(axis=0)
        useful = (arr[n_dark:] - dark_ref[np.newaxis, ...]).mean(axis=0)
        ch0_mean, ch1_mean = float(useful[..., 0].mean()), float(useful[..., 1].mean())
        rows.append({"index": i, "t_ms": dt_ms, "ch0_mean": ch0_mean, "ch1_mean": ch1_mean})
        _log.info("Mode 7: acquisition %d (%.1f ms) -> ch0=%.2f, ch1=%.2f", i, dt_ms, ch0_mean, ch1_mean)

    save_table(out_dir, "mode7_noflush_table", rows)
    save_json(out_dir, "mode7_params", {
        "t_old_us": t_old_us, "t_new_us": t_new_us,
        "sensnframes": sensnframes, "n_acquisitions": n_acquisitions,
    })

    fig, ax = plt.subplots(figsize=(6, 4))
    idx = [r["index"] for r in rows]
    ch0 = [r["ch0_mean"] for r in rows]
    ch1 = [r["ch1_mean"] for r in rows]
    ax.plot(idx, ch0, "o-", label="channel 0 (long)")
    ax.plot(idx, ch1, "o-", label="channel 1 (short)")
    ax.set_xlabel("acquisition index (no flush() between any of these)")
    ax.set_ylabel("dark-subtracted mean")
    ax.set_title(f"Mode 7: no-flush sequence, t_old={t_old_us:g}us -> t_new={t_new_us:g}us")
    ax.legend()
    fig.savefig(os.path.join(out_dir, "mode7_summary.png"))
    plt.show()


# ----------------------------------------------------------------------
# Mode 8 -- smooth_amplitude FWHMnFrame effectiveness sweep
# ----------------------------------------------------------------------

def mode8_fwhm_sweep(cam: HeliCamC3, out_dir: str, t_acquire_us: float,
                      fwhm_list, n_repeats: int) -> None:
    """
    Does FWHMnFrame's on-device matched filter (manual §5.2.2) actually
    reduce noise in the final amplitude image, given that data_reformat()
    already averages the *entire* SensNFrames stack down to one frame
    regardless of FWHMnFrame (see its CamMode 1/2 docstring in helicam.py)?

    That full-stack average already removes most within-acquisition
    (frame-to-frame) noise on its own -- averaging commutes with a linear
    filter applied earlier in the same stack, so a smoothing filter applied
    before averaging the same full stack should only change the result via
    edge effects (the filter's own boundary tapering over its first/last
    few frames, a few percent of SensNFrames=256). Whether that residual
    effect is big enough to matter can only be settled by measurement, not
    by reading the register description -- hence this mode.

    Metric: for a CamMode-1 "amplitude" baseline (FWHMnFrame off) and each
    FWHMnFrame value, acquire ``n_repeats`` *independent* acquisitions
    back-to-back (same settings, nothing changed in between) and compute
    the per-pixel std across those repeats -- genuine inter-acquisition
    noise, the one thing a single acquisition's own full-stack averaging
    cannot show. If larger FWHMnFrame actually helps, this repeat-to-repeat
    std should measurably drop as FWHMnFrame increases; if it's flat, the
    filter isn't buying anything once data_reformat()'s own averaging is
    already in the pipeline.
    """
    _timed("set_measurement_mode('steady')", cam.set_measurement_mode, "steady")
    _timed("set_gain(1.0)", cam.set_gain, 1.0)
    _timed(f"set_acquire_time({t_acquire_us})", cam.set_acquire_time, t_acquire_us)

    rows = []
    mean_images = {}   # label -> mean-over-repeats image, for the summary grid

    def _run_group(label: str, fwhm):
        if fwhm is None:
            _timed("set_measurement_mode('amplitude')", cam.set_measurement_mode, "amplitude")
        else:
            _timed(f"set_measurement_mode('smooth_amplitude', FWHMnFrame={fwhm})",
                   cam.set_measurement_mode, "smooth_amplitude", FWHMnFrame=fwhm)

        stack = []
        for i in range(n_repeats):
            frame = _timed(f"acquire_single() [{label}, repeat {i}]", cam.acquire_single)
            if frame is None:
                _log.warning("Mode 8: %s repeat %d failed, skipping", label, i)
                continue
            save_frame(out_dir, f"mode8_{label}_repeat{i}_frame", frame)
            stack.append(frame)

        if not stack:
            _log.warning("Mode 8: %s -- all %d repeats failed", label, n_repeats)
            rows.append({"label": label, "fwhm_n_frame": fwhm, "n_ok": 0,
                         "mean_amplitude": None, "repeat_noise_std": None})
            return

        stack = np.stack(stack, axis=0)
        mean_img = stack.mean(axis=0)
        repeat_noise = float(stack.std(axis=0).mean()) if len(stack) > 1 else None
        mean_images[label] = mean_img
        rows.append({
            "label": label,
            "fwhm_n_frame": fwhm,
            "n_ok": len(stack),
            "mean_amplitude": float(mean_img.mean()),
            "repeat_noise_std": repeat_noise,
        })
        _log.info("Mode 8: %s -- mean=%.2f, repeat-to-repeat std=%s (n=%d)",
                   label, mean_img.mean(),
                   f"{repeat_noise:.3f}" if repeat_noise is not None else "n/a", len(stack))

    _run_group("amplitude_baseline", None)
    for fwhm in fwhm_list:
        _run_group(f"fwhm{fwhm}", fwhm)

    save_table(out_dir, "mode8_fwhm_sweep_table", rows)
    save_json(out_dir, "mode8_params", {
        "t_acquire_us": t_acquire_us,
        "fwhm_list": list(fwhm_list),
        "n_repeats": n_repeats,
        "gain_DdsGain": cam.get_attribute("DdsGain"),
        "SensNFrames": cam.SMOOTH_AMPLITUDE_SETTINGS["SensNFrames"],
    })

    labels = [row["label"] for row in rows]
    fig1, axes1 = plt.subplots(1, len(labels), figsize=(4 * len(labels), 4))
    if len(labels) == 1:
        axes1 = [axes1]
    for ax, label in zip(axes1, labels):
        img = mean_images.get(label)
        if img is not None:
            im = ax.imshow(img, cmap="gray")
            fig1.colorbar(im, ax=ax)
        ax.set_title(label)
    fig1.suptitle(f"Mode 8: FWHMnFrame sweep, mean of {n_repeats} repeats each (t={t_acquire_us:g}us)")
    fig1.savefig(os.path.join(out_dir, "mode8_frames_summary.png"))

    swept = [row for row in rows if row["fwhm_n_frame"] is not None and row["repeat_noise_std"] is not None]
    baseline = next((row for row in rows if row["fwhm_n_frame"] is None), None)

    fig2, ax2 = plt.subplots(figsize=(6, 4))
    ax2.plot([row["fwhm_n_frame"] for row in swept], [row["repeat_noise_std"] for row in swept], "o-",
              label="smooth_amplitude")
    if baseline is not None and baseline["repeat_noise_std"] is not None:
        ax2.axhline(baseline["repeat_noise_std"], color="gray", linestyle="--",
                     label="amplitude baseline (no filter)")
    ax2.set_xlabel("FWHMnFrame (0=off, 1=2fr, 2=6fr, 3=10fr, 4=20fr)")
    ax2.set_ylabel("repeat-to-repeat std (mean over image)")
    ax2.set_title("Mode 8: does FWHMnFrame reduce inter-acquisition noise?")
    ax2.legend()
    fig2.savefig(os.path.join(out_dir, "mode8_noise_vs_fwhm.png"))
    plt.show()


# ----------------------------------------------------------------------
# Mode 9 -- ExtTqp lock check (PEM reference on the heliDriver encoder input)
# ----------------------------------------------------------------------

F_SENSOR_HZ = 70e6


def _rawiq_burst(cam: HeliCamC3, label: str, n_acq: int, settings: dict):
    """
    Configure rawIQ with ``settings``, then time ``n_acq`` back-to-back
    acquisitions (no flush in between). Returns (list of (n, H, W, 2) int16
    volumes, list of per-acquisition wall times in ms). Stops early after 2
    consecutive failures so a dead ExtTqp input costs seconds, not minutes.
    """
    _timed(f"set_measurement_mode('rawIQ') [{label}]", cam.set_measurement_mode, "rawIQ", **settings)
    vols, t_ms = [], []
    n_fail = 0
    for i in range(n_acq):
        t0 = time.perf_counter()
        data = cam._acquire()
        dt = (time.perf_counter() - t0) * 1000.0
        if data is None:
            n_fail += 1
            _log.warning("Mode 9 [%s]: acquisition %d failed after %.0f ms", label, i, dt)
            if n_fail >= 2:
                _log.warning("Mode 9 [%s]: 2 consecutive failures, giving up on this config", label)
                break
            continue
        n_fail = 0
        vols.append(cam.crop_unphysical(data).view(np.int16).copy())
        t_ms.append(dt)
        _log.info("Mode 9 [%s]: acquisition %d -> %.1f ms", label, i, dt)
    return vols, t_ms


def mode9_exttqp_lock(cam: HeliCamC3, out_dir: str, f_pem_hz: float, n_acq: int,
                      ext_sens_tqp: int, note: str) -> None:
    """
    Is the lock-in actually locked to the PEM reference on the encoder input?

    Two rawIQ (CamMode 0) bursts with identical settings except the clock:
      1. internal clock (ExtTqp=0, SensTqp=29 -> fd=148.3 kHz): known-good
         reference. Calibrates the per-frame USB overhead for the timing
         model, and -- because the 50 kHz optical signal isn't at fd or an
         odd harmonic of it -- its frame-averaged I/Q is a free per-pixel
         offset map (no modulated signal demodulated).
      2. external clock (ExtTqp=1, ExtTqpPuls=1 so either encoder channel A
         or B works, TrigFreeExtN=1 free-running).

    Evidence it's locked, from independent angles:
      * Timing: per-frame time Tfr = (Nc+1)/fd with Nc = 2*SensNavM2+2
        (BSEnable=1, CalDur1Cyc=1; confirmed by run 037). With SensNavM2=255
        the sensor time dominates, so wall time per acquisition is an fd
        meter. Prediction: fd = f_in/2 = f_PEM (2f reference in), or f_in =
        2 f_PEM if my reading of manual §4.4 is wrong, or 148.3 kHz if
        ExtTqp were silently ignored.
      * Coherence: with a locked reference the demodulated (I,Q) vector is
        the same every frame, so per pixel |mean(z)| / mean(|z|) -> 1.
        Unlocked or no signal -> ~1/sqrt(n_frames). z = (I - I0) + i(Q - Q0),
        offsets from burst 1.
      * Control (manual, rerun with --note pem_off): set PEM retardation to 0
        -- the coherent amplitude must collapse while the timing stays.

    SensTqp=29 is deliberate for the timing test: in ExtTqp mode it only sets
    the per-sample integration length ((29+11)/35 MHz = 1.1 us, inside the
    5 us half-period of a 100 kHz reference), and it makes "ExtTqp ignored"
    land at 148.3 kHz -- far from both lock hypotheses. It also gives both
    bursts the same integration length, so burst 1's offset map applies.
    """
    sens_nav_m2, n_frames = 255, 16
    nc = 2 * sens_nav_m2 + 2
    common = {
        "SensNFrames": n_frames, "SensNavM2": sens_nav_m2, "BSEnable": 1, "CalDur1Cyc": 1,
        "DdsGain": 2, "TrigFreeExtN": 1,
    }
    int_settings = {**common, "SensTqp": 29, "ExtTqp": 0, "ExtTqpPuls": 0}
    ext_settings = {**common, "SensTqp": ext_sens_tqp, "ExtTqp": 1, "ExtTqpPuls": 1}
    if (ext_sens_tqp + 11) / 35e6 >= 0.5 / (2 * f_pem_hz):
        _log.warning("Mode 9: SensTqp=%d integrates %.2f us, >= the 2f reference half-period %.2f us "
                     "(manual §4.4 constraint)", ext_sens_tqp, (ext_sens_tqp + 11) / 35e6 * 1e6,
                     0.5 / (2 * f_pem_hz) * 1e6)

    int_vols, int_t = _rawiq_burst(cam, "internal", n_acq, int_settings)
    try:
        ext_vols, ext_t = _rawiq_burst(cam, "external", n_acq, ext_settings)
        cam.dump_registers(out_dir, "mode9_registers_external")
    finally:
        # Never leave the camera on ExtTqp -- every later mode would stall
        # (or silently run off the PEM) without knowing why.
        cam.set_attributes(AcqStop=1, ExtTqp=0, ExtTqpPuls=0)
        cam.set_attributes(AcqStop=0)
        _log.info("Mode 9: restored ExtTqp=0")

    if not int_vols:
        _log.error("Mode 9: internal-clock reference failed entirely -- camera problem, not ExtTqp")
        return
    np.save(os.path.join(out_dir, "mode9_internal_raw0.npy"), int_vols[0])
    if ext_vols:
        np.save(os.path.join(out_dir, "mode9_external_raw0.npy"), ext_vols[0])

    # --- Timing -> fd estimate. Skip the first acquisition (may be a volume
    # already sitting in camera memory, so it returns early).
    def _median_steady(ts):
        return float(np.median(ts[1:] if len(ts) > 1 else ts))

    fd_int = F_SENSOR_HZ / (8 * (29 + 30))
    tfr_int = (nc + 1) / fd_int
    t_int = _median_steady(int_t) / 1000.0
    t_usb = t_int / n_frames - tfr_int
    _log.info("Mode 9: internal %.1f ms/acq -> USB+overhead %.2f ms/frame (Tfr %.2f ms at %.1f kHz)",
              t_int * 1e3, t_usb * 1e3, tfr_int * 1e3, fd_int / 1e3)

    predictions = {
        "fd=f_PEM (f_in/2, expected)": f_pem_hz,
        "fd=2f_PEM (f_in)": 2 * f_pem_hz,
        "ExtTqp ignored (internal)": F_SENSOR_HZ / (8 * (ext_sens_tqp + 30)),
    }
    for name, fd in predictions.items():
        _log.info("Mode 9: prediction %-30s fd=%8.1f Hz -> %.1f ms/acq",
                  name, fd, n_frames * ((nc + 1) / fd + t_usb) * 1e3)

    fd_ext_est = None
    if ext_t:
        t_ext = _median_steady(ext_t) / 1000.0
        tfr_ext = t_ext / n_frames - t_usb
        fd_ext_est = (nc + 1) / tfr_ext if tfr_ext > 0 else None
        _log.info("Mode 9: external %.1f ms/acq -> estimated fd = %s", t_ext * 1e3,
                  f"{fd_ext_est:.0f} Hz ({fd_ext_est / f_pem_hz:.3f} x f_PEM)" if fd_ext_est else "n/a")
    else:
        _log.warning("Mode 9: NO external acquisitions succeeded. Either no pulses reach the encoder "
                     "input (wiring / channel / signal level), or ExtTqp needs TrigFreeExtN=0 plus a "
                     "start pulse on the trigger BNC.")

    # --- Coherence / signal, relative to the internal burst's offset map.
    offset = np.concatenate(int_vols, axis=0).astype(np.float64).mean(axis=0)   # (H, W, 2)

    def _lock_stats(vols):
        rows = []
        amp_maps, coh_maps, phase_maps = [], [], []
        for k, v in enumerate(vols):
            d = v.astype(np.float64) - offset
            z = d[..., 0] + 1j * d[..., 1]                     # (n, H, W)
            m = z.mean(axis=0)
            amp = np.abs(m)
            coh = amp / np.maximum(np.abs(z).mean(axis=0), 1e-9)
            amp_maps.append(amp); coh_maps.append(coh); phase_maps.append(np.angle(m))
            rows.append({"acq": k, "mean_amp": float(amp.mean()), "p99_amp": float(np.percentile(amp, 99))})
        return rows, np.mean(amp_maps, 0), np.mean(coh_maps, 0), phase_maps

    int_rows, int_amp, int_coh, _ = _lock_stats(int_vols)
    coh_floor = 1.0 / np.sqrt(n_frames)
    _log.info("Mode 9: internal (no-signal reference): mean |z| %.2f counts, coherence median %.2f "
              "(random-noise floor ~%.2f)", int_amp.mean(), np.median(int_coh), coh_floor)

    summary = {
        "note": note, "f_pem_hz": f_pem_hz, "n_acq": n_acq, "SensNFrames": n_frames,
        "SensNavM2": sens_nav_m2, "ext_SensTqp": ext_sens_tqp,
        "internal_ms_per_acq": int_t, "external_ms_per_acq": ext_t,
        "usb_overhead_ms_per_frame": t_usb * 1e3, "fd_ext_estimate_hz": fd_ext_est,
        "predictions_hz": predictions,
        "internal_mean_amp": float(int_amp.mean()), "internal_coherence_median": float(np.median(int_coh)),
    }

    if ext_vols:
        ext_rows, ext_amp, ext_coh, ext_phases = _lock_stats(ext_vols)
        # Signal ROI: pixels clearly above the internal-reference noise.
        thresh = np.percentile(int_amp, 99) * 3
        roi = ext_amp > thresh
        n_roi = int(roi.sum())
        raw_all = np.concatenate(ext_vols, axis=0)
        clip_frac = float(((raw_all <= 2) | (raw_all >= 1021)).mean())
        acq_phase = [float(np.angle(np.exp(1j * p[roi]).mean())) if n_roi else None for p in ext_phases]
        _log.info("Mode 9: external: mean |z| %.2f counts, %d px above 3x internal p99 (%.1f), "
                  "coherence median %.2f overall / %s in ROI, clipped raw fraction %.4f",
                  ext_amp.mean(), n_roi, thresh, np.median(ext_coh),
                  f"{np.median(ext_coh[roi]):.2f}" if n_roi else "n/a", clip_frac)
        _log.info("Mode 9: ROI phase per acquisition [rad]: %s  (a jump of ~pi between acquisitions "
                  "= start-on-rising vs falling edge)", [None if p is None else round(p, 2) for p in acq_phase])
        if n_roi and np.median(ext_coh[roi]) > 0.8:
            _log.info("Mode 9: VERDICT -- coherent, stationary demodulated signal: consistent with LOCKED. "
                      "Confirm with a --note pem_off rerun (amplitude should collapse).")
        else:
            _log.info("Mode 9: VERDICT -- no coherent signal above the reference. Not locked, no light "
                      "modulation reaching the sensor, or the PEM is off.")
        for r, p in zip(ext_rows, acq_phase):
            r["roi_phase_rad"] = p
        save_table(out_dir, "mode9_external_per_acq", ext_rows)
        np.save(os.path.join(out_dir, "mode9_external_amp.npy"), ext_amp)
        np.save(os.path.join(out_dir, "mode9_external_coherence.npy"), ext_coh)
        np.save(os.path.join(out_dir, "mode9_offset_from_internal.npy"), offset)
        summary.update({
            "external_mean_amp": float(ext_amp.mean()), "external_coherence_median": float(np.median(ext_coh)),
            "roi_pixels": n_roi, "roi_threshold": float(thresh),
            "roi_coherence_median": float(np.median(ext_coh[roi])) if n_roi else None,
            "roi_phase_per_acq_rad": acq_phase, "clipped_raw_fraction": clip_frac,
        })

        fig, axes = plt.subplots(1, 4, figsize=(20, 4.5))
        im = axes[0].imshow(int_amp, cmap="magma"); fig.colorbar(im, ax=axes[0])
        axes[0].set_title("internal |z| (no-signal reference)")
        im = axes[1].imshow(ext_amp, cmap="magma"); fig.colorbar(im, ax=axes[1])
        axes[1].set_title("external |z| [counts]")
        im = axes[2].imshow(ext_coh, cmap="viridis", vmin=0, vmax=1); fig.colorbar(im, ax=axes[2])
        axes[2].set_title(f"external coherence (noise floor ~{coh_floor:.2f})")
        ph = np.where(roi, ext_phases[0], np.nan)
        im = axes[3].imshow(ph, cmap="twilight", vmin=-np.pi, vmax=np.pi); fig.colorbar(im, ax=axes[3])
        axes[3].set_title("external phase, acq 0 (ROI only)")
        fd_txt = f"{fd_ext_est / 1e3:.2f} kHz" if fd_ext_est else "n/a"
        fig.suptitle(f"Mode 9 ExtTqp lock check [{note}] -- f_PEM={f_pem_hz / 1e3:.3f} kHz, "
                     f"estimated fd={fd_txt}")
        fig.savefig(os.path.join(out_dir, "mode9_summary.png"))

    save_json(out_dir, "mode9_summary", summary)
    plt.show()


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", type=int, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9], required=True,
                         help="1=lifecycle/exposure-gain, 2=lock-in detection, 3=streaming, "
                              "4=auto_expose() checkout, 5=SensNFrames sweep, "
                              "6=SensExpRatio sweep, 7=no-flush raw sequence, "
                              "8=smooth_amplitude FWHMnFrame effectiveness sweep, "
                              "9=ExtTqp lock check (PEM reference on encoder input)")
    parser.add_argument("--f-pem-hz", type=float, default=50023.0,
                         help="PEM 1f frequency from the controller display, mode 9 (default: %(default)s)")
    parser.add_argument("--n-acq", type=int, default=6,
                         help="Acquisitions per clock config, mode 9 (default: %(default)s)")
    parser.add_argument("--ext-sens-tqp", type=int, default=29,
                         help="SensTqp (per-sample integration length) in ExtTqp mode, mode 9 "
                              "(default: %(default)s; must keep (SensTqp+11)/35MHz < reference half-period)")
    parser.add_argument("--note", type=str, default="pem_on",
                         help="Free-text label saved with mode 9 results, e.g. pem_on / pem_off")
    parser.add_argument("--sys-id", type=str, default="c3cam_sl70")
    parser.add_argument("--t-acquire-us", type=float, default=DEFAULT_T_ACQUIRE_US,
                         help="Starting exposure time in microseconds, modes 2/3/8 (default: %(default)s)")
    parser.add_argument("--target-fraction", type=float, default=0.5,
                         help="auto_expose() target fraction of the way to the detected "
                              "saturation onset, mode 4 (default: %(default)s)")
    parser.add_argument("--offset-method", type=str, choices=["self", "null"], default="self",
                         help="rawIQ offset_I/offset_Q source, mode 2: 'self' (this capture's "
                              "own mean, free) or 'null' (dedicated null_offset() calibration -- "
                              "requires no modulated signal present when it runs) (default: %(default)s)")
    args = parser.parse_args()

    out_dir = make_test_dir()
    add_file_logging(out_dir)

    with HeliCamC3(args.sys_id) as cam:
        _log.info("Camera opened: %s", cam.status())
        if args.mode == 1:
            mode1_lifecycle(cam, out_dir, DEFAULT_MODE1_T_ACQUIRE_US_LIST)
        elif args.mode == 2:
            mode2_lockin(cam, out_dir, args.t_acquire_us, args.offset_method)
        elif args.mode == 3:
            mode3_streaming(cam, out_dir, args.t_acquire_us)
        elif args.mode == 4:
            mode4_autoexpose(cam, out_dir, args.target_fraction)
        elif args.mode == 5:
            mode5_frames_sweep(cam, out_dir, DEFAULT_MODE5_T_ACQUIRE_US, DEFAULT_MODE5_SENSNFRAMES_LIST)
        elif args.mode == 6:
            mode6_sensexpratio_sweep(cam, out_dir, DEFAULT_MODE6_T_ACQUIRE_US, DEFAULT_MODE6_SENSEXPRATIO_LIST)
        elif args.mode == 7:
            mode7_no_flush_raw(cam, out_dir, DEFAULT_MODE7_T_OLD_US, DEFAULT_MODE7_T_NEW_US,
                                DEFAULT_MODE7_SENSNFRAMES, DEFAULT_MODE7_N_ACQUISITIONS)
        elif args.mode == 8:
            mode8_fwhm_sweep(cam, out_dir, args.t_acquire_us,
                              DEFAULT_MODE8_FWHM_LIST, DEFAULT_MODE8_N_REPEATS)
        elif args.mode == 9:
            mode9_exttqp_lock(cam, out_dir, args.f_pem_hz, args.n_acq, args.ext_sens_tqp, args.note)

        cam.dump_registers(out_dir)

    _log.info("Done. Output in %s", out_dir)


if __name__ == "__main__":
    main()
