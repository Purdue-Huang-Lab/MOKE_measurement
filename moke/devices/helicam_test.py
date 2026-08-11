"""
HeliCam C3 hardware test script -- run manually against real hardware.

Seven modes, one bench checkout item each. Each run creates a fresh
``helicam_test_data/helicam_test_NNN/`` folder (auto-incrementing) so
repeated runs never clobber each other's data. Regardless of mode, every
run finishes by dumping the full live register set to ``registers.json``
(see ``HeliCamC3.dump_registers()``) -- a cheap, always-useful record of
exactly what state the camera was left in. Modes 2/3/4 additionally dump
registers immediately before and after each ``auto_expose()`` call, to
catch what that search itself changes.

Usage::

    python -m moke.devices.helicam_test --mode 1
    python -m moke.devices.helicam_test --mode 2
    python -m moke.devices.helicam_test --mode 3
    python -m moke.devices.helicam_test --mode 4
    python -m moke.devices.helicam_test --mode 5
    python -m moke.devices.helicam_test --mode 6
    python -m moke.devices.helicam_test --mode 7

Mode 1 -- lifecycle / exposure characterization:
    open -> steady mode -> gain=1x (best SNR, DdsGain=2) -> acquire across a
    fixed, log-spaced list of exposures, recording a (t_acquire_us, max_val)
    table. Does NOT use auto_expose() -- see open_issue_helicam.md #9.

Mode 2 -- lock-in detection:
    open -> steady mode -> auto_expose() -> steady frame -> rawIQ mode ->
    convert I/Q to amplitude -> minE mode -> amplitude+Z. Saves every image
    and the run parameters.

Mode 3 -- streaming:
    open -> steady mode -> auto_expose() -> live matplotlib preview at up to
    10 fps (throttled to the camera's own estimated acquire time if slower)
    with Pause / Start / Save frame / Move on buttons -> switch to minE mode
    -> stream again.

Mode 4 -- auto_expose() checkout:
    open -> steady mode -> gain=1x (DdsGain=2) -> auto_expose() -> record
    the full search trial table + final frame. Exists to exercise/verify
    auto_expose() on real hardware in isolation rather than buried inside
    modes 2/3. auto_expose() detects saturation via the channel0/channel1
    ratio (see helicamC3_practical_knowledge_base.md #3), not an absolute
    intensity threshold -- see its docstring in helicam.py.

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

This script owns all visualization/GUI/file-IO weight -- ``helicam.py``
stays a plain (non-GUI) device driver; see device_interface_instruction.md.
"""

import argparse
import csv
import glob
import json
import logging
import os
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


def _timed(label: str, fn, *args, level: int = logging.INFO, **kwargs):
    """
    Run ``fn(*args, **kwargs)``, log how long it took, and return its result.

    This is how "how fast is each camera instruction" gets answered --
    ``helicam.py`` itself stays free of timing/instrumentation code (it's a
    device driver, not a profiler); all per-call timing lives here instead.
    """
    t0 = time.monotonic()
    result = fn(*args, **kwargs)
    dt_ms = (time.monotonic() - t0) * 1000.0
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
# Mode 2 -- lock-in detection (rawIQ + minE)
# ----------------------------------------------------------------------

def mode2_lockin(cam: HeliCamC3, out_dir: str, t_acquire_us: float) -> None:
    _timed("set_measurement_mode('steady')", cam.set_measurement_mode, "steady")
    _timed(f"set_acquire_time({t_acquire_us})", cam.set_acquire_time, t_acquire_us)
    cam.dump_registers(out_dir, "mode2_registers_before_autoexpose")
    result = _timed("auto_expose()", cam.auto_expose, target_fraction=0.5)
    cam.dump_registers(out_dir, "mode2_registers_after_autoexpose")
    _log.info("Mode 2: auto_expose -> t_acquire_us=%.1f (saturation onset=%s us)",
               result["t_acquire_us"], result["t_saturation_onset_us"])

    steady_frame = _timed("acquire_single() [steady]", cam.acquire_single)
    save_frame(out_dir, "mode2_steady_frame", steady_frame)

    _timed("set_measurement_mode('rawIQ')", cam.set_measurement_mode, "rawIQ")
    raw_iq = _timed("acquire_single() [rawIQ]", cam.acquire_single)   # (n_frames, 300, 300, 2) int16, raw ADC counts
    if raw_iq is None:
        raise RuntimeError("mode2: rawIQ acquire_single() returned no data")
    I, Q = raw_iq[..., 0], raw_iq[..., 1]
    rawiq_amplitude = HeliCamC3.iq_to_amplitude(I, Q).mean(axis=0)   # average over the volume's frames
    save_frame(out_dir, "mode2_rawiq_amplitude", rawiq_amplitude)
    _log.info("Mode 2: rawIQ amplitude -- shape=%s mean=%.1f", rawiq_amplitude.shape, rawiq_amplitude.mean())

    _timed("set_measurement_mode('minimum_energy')", cam.set_measurement_mode, "minimum_energy")
    minE_frame = _timed("acquire_single() [minE]", cam.acquire_single)   # (300, 300, 2) float32: [...,0]=amplitude, [...,1]=Z
    if minE_frame is None:
        raise RuntimeError("mode2: minE acquire_single() returned no data")
    save_frame(out_dir, "mode2_minE_amplitude", minE_frame[..., 0])
    save_frame(out_dir, "mode2_minE_z", minE_frame[..., 1])
    _log.info("Mode 2: minE amplitude -- mean=%.1f", minE_frame[..., 0].mean())

    save_json(out_dir, "mode2_params", {
        "t_acquire_us": result["t_acquire_us"],
        "t_saturation_onset_us": result["t_saturation_onset_us"],
        "nominal_ratio": result["nominal_ratio"],
        "gain_DdsGain": cam.get_attribute("DdsGain"),
    })

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for ax, (title, img) in zip(axes, [
        ("steady", steady_frame),
        ("rawIQ amplitude", rawiq_amplitude),
        ("minE amplitude", minE_frame[..., 0]),
    ]):
        im = ax.imshow(img, cmap="gray")
        ax.set_title(title)
        fig.colorbar(im, ax=ax)
    fig.suptitle("Mode 2: lock-in detection")
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


def stream(cam: HeliCamC3, out_dir: str, label: str, fps: float = 10.0) -> None:
    """
    Live preview loop. Not fancy -- this is a manual bench test tool, not a
    product UI. Pause/Start/Save/Move on buttons; closing the window also
    ends the stream.
    """
    controls = _StreamControls()

    frame = _timed(f"acquire_single() [stream {label}, initial]", cam.acquire_single)
    if frame is None:
        raise RuntimeError(f"stream({label}): initial acquire_single() returned no data")
    img = amplitude_channel(frame)

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

    # Throttle to the slower of the requested fps or the camera's own
    # estimated per-acquisition time -- no point polling faster than the
    # hardware can actually deliver frames.
    est_s = cam.estimate_acquire_time()
    interval_s = max(1.0 / fps, est_s)
    if interval_s > 1.0 / fps:
        _log.info("stream(%s): throttling to %.2f fps (exposure/transfer-bound, est=%.3fs)",
                   label, 1.0 / interval_s, est_s)

    n = 0
    while controls.running and plt.fignum_exists(fig.number):
        loop_start = time.monotonic()
        if not controls.paused:
            # DEBUG, not INFO -- at up to 10 fps this would otherwise flood the
            # console; the per-frame acquire time is shown in the title instead.
            frame = _timed(f"acquire_single() [stream {label}, frame {n}]",
                           cam.acquire_single, level=logging.DEBUG)
            acquire_dt_ms = (time.monotonic() - loop_start) * 1000.0
            if frame is not None:
                img = amplitude_channel(frame)
                im.set_data(img)
                im.set_clim(img.min(), img.max())
                n += 1
            title.set_text(f"{label} | frame {n} | max {img.max():.4g} | acquire {acquire_dt_ms:.1f} ms")

        if controls.save_requested:
            save_frame(out_dir, f"mode3_{label}_frame_{n:04d}", frame)
            controls.save_requested = False

        fig.canvas.draw_idle()
        fig.canvas.flush_events()
        remaining = interval_s - (time.monotonic() - loop_start)
        plt.pause(max(remaining, 0.001))

    plt.close(fig)


def mode3_streaming(cam: HeliCamC3, out_dir: str, t_acquire_us: float) -> None:
    _timed("set_measurement_mode('steady')", cam.set_measurement_mode, "steady")
    _timed(f"set_acquire_time({t_acquire_us})", cam.set_acquire_time, t_acquire_us)
    cam.dump_registers(out_dir, "mode3_registers_before_autoexpose")
    result = _timed("auto_expose()", cam.auto_expose, target_fraction=0.5)
    cam.dump_registers(out_dir, "mode3_registers_after_autoexpose")
    _log.info("Mode 3: auto_expose -> t_acquire_us=%.1f (saturation onset=%s us)",
               result["t_acquire_us"], result["t_saturation_onset_us"])

    stream(cam, out_dir, "steady", fps=10.0)

    _timed("set_measurement_mode('minimum_energy')", cam.set_measurement_mode, "minimum_energy")
    stream(cam, out_dir, "minE", fps=10.0)


# ----------------------------------------------------------------------
# Mode 4 -- auto_expose() checkout in steady mode
# ----------------------------------------------------------------------

def mode4_autoexpose(cam: HeliCamC3, out_dir: str, target_fraction: float) -> None:
    """
    Fixed gain=1x (best SNR, DdsGain=2) -> auto_expose() -> record its full
    search trial table plus the final frame at the exposure it settled on.

    Isolated from modes 2/3 (which also call auto_expose() but bury its
    result inside a larger pipeline) so its search behaviour can be checked
    against real hardware on its own. auto_expose() detects saturation via
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
        t0 = time.monotonic()
        data = cam._acquire()
        dt_ms = (time.monotonic() - t0) * 1000.0
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
# Entry point
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", type=int, choices=[1, 2, 3, 4, 5, 6, 7], required=True,
                         help="1=lifecycle/exposure-gain, 2=lock-in detection, 3=streaming, "
                              "4=auto_expose() checkout, 5=SensNFrames sweep, "
                              "6=SensExpRatio sweep, 7=no-flush raw sequence")
    parser.add_argument("--sys-id", type=str, default="c3cam_sl70")
    parser.add_argument("--t-acquire-us", type=float, default=DEFAULT_T_ACQUIRE_US,
                         help="Starting exposure time in microseconds, modes 2/3 (default: %(default)s)")
    parser.add_argument("--target-fraction", type=float, default=0.5,
                         help="auto_expose() target fraction of the way to the detected "
                              "saturation onset, mode 4 (default: %(default)s)")
    args = parser.parse_args()

    out_dir = make_test_dir()
    add_file_logging(out_dir)

    with HeliCamC3(args.sys_id) as cam:
        _log.info("Camera opened: %s", cam.status())
        if args.mode == 1:
            mode1_lifecycle(cam, out_dir, DEFAULT_MODE1_T_ACQUIRE_US_LIST)
        elif args.mode == 2:
            mode2_lockin(cam, out_dir, args.t_acquire_us)
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

        cam.dump_registers(out_dir)

    _log.info("Done. Output in %s", out_dir)


if __name__ == "__main__":
    main()
