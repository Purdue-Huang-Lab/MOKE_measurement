"""
HeliCam C3 hardware test script -- run manually against real hardware.

Three modes, one bench checkout item each. Each run creates a fresh
``helicam_test_data/helicam_test_NNN/`` folder (auto-incrementing) so
repeated runs never clobber each other's data.

Usage::

    python -m moke.devices.helicam_test --mode 1
    python -m moke.devices.helicam_test --mode 2
    python -m moke.devices.helicam_test --mode 3

Mode 1 -- lifecycle / exposure & gain characterization:
    open -> steady mode -> acquire one frame at a default exposure -> save it
    -> auto_expose() to ~half max -> repeat across analogue gains, recording
    a (t_acquire_us, gain, max_val, frac) table.

Mode 2 -- lock-in detection:
    open -> steady mode -> auto_expose() -> steady frame -> rawIQ mode ->
    convert I/Q to amplitude -> minE mode -> amplitude+Z. Saves every image
    and the run parameters.

Mode 3 -- streaming:
    open -> steady mode -> auto_expose() -> live matplotlib preview at up to
    10 fps (throttled to the camera's own estimated acquire time if slower)
    with Pause / Start / Save frame / Move on buttons -> switch to minE mode
    -> stream again.

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
DEFAULT_GAINS = (3.0, 1.5, 1.0, 0.75)


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

def mode1_lifecycle(cam: HeliCamC3, out_dir: str, t_acquire_us: float, gains) -> None:
    _timed("set_measurement_mode('steady')", cam.set_measurement_mode, "steady")

    _timed(f"set_acquire_time({t_acquire_us})", cam.set_acquire_time, t_acquire_us)
    frame = _timed("acquire_single() [initial]", cam.acquire_single)
    if frame is None:
        raise RuntimeError("mode1: initial acquire_single() returned no data")
    save_frame(out_dir, "mode1_initial_frame", frame)
    _log.info("Mode 1: initial frame at t_acquire_us=%.1f -> max=%s", t_acquire_us, frame.max())

    rows = []
    gain_frames = {}
    for gain in gains:
        _timed(f"set_gain({gain})", cam.set_gain, gain)
        result = _timed(f"auto_expose() [gain={gain}]", cam.auto_expose, target_fraction=0.5)
        rows.extend(result["table"])
        if result["floor_limited"]:
            _log.warning("Mode 1: gain=%s -> still oversaturated (frac=%.3f) at the minimum "
                         "exposure -- target not actually reached", gain, result["max_frac"])
        _log.info("Mode 1: gain=%s -> optimal t_acquire_us=%.1f (max_frac=%.3f, %d trials)",
                   gain, result["t_acquire_us"], result["max_frac"], len(result["table"]))
        frame = _timed(f"acquire_single() [gain={gain} optimal]", cam.acquire_single)
        save_frame(out_dir, f"mode1_gain_{gain}_optimal_frame", frame)
        gain_frames[gain] = frame

    save_table(out_dir, "mode1_exposure_gain_table", rows)

    fig, axes = plt.subplots(1, len(gains), figsize=(4 * len(gains), 4))
    if len(gains) == 1:
        axes = [axes]
    for ax, gain in zip(axes, gains):
        im = ax.imshow(gain_frames[gain], cmap="gray")
        ax.set_title(f"gain={gain}")
        fig.colorbar(im, ax=ax)
    fig.suptitle("Mode 1: optimal-exposure frame per gain")
    fig.savefig(os.path.join(out_dir, "mode1_summary.png"))
    plt.show()


# ----------------------------------------------------------------------
# Mode 2 -- lock-in detection (rawIQ + minE)
# ----------------------------------------------------------------------

def mode2_lockin(cam: HeliCamC3, out_dir: str, t_acquire_us: float) -> None:
    _timed("set_measurement_mode('steady')", cam.set_measurement_mode, "steady")
    _timed(f"set_acquire_time({t_acquire_us})", cam.set_acquire_time, t_acquire_us)
    result = _timed("auto_expose()", cam.auto_expose, target_fraction=0.5)
    _log.info("Mode 2: auto_expose -> t_acquire_us=%.1f (max_frac=%.3f)",
               result["t_acquire_us"], result["max_frac"])

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
        "steady_max_frac": result["max_frac"],
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
    result = _timed("auto_expose()", cam.auto_expose, target_fraction=0.5)
    _log.info("Mode 3: auto_expose -> t_acquire_us=%.1f (max_frac=%.3f)",
               result["t_acquire_us"], result["max_frac"])

    stream(cam, out_dir, "steady", fps=10.0)

    _timed("set_measurement_mode('minimum_energy')", cam.set_measurement_mode, "minimum_energy")
    stream(cam, out_dir, "minE", fps=10.0)


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", type=int, choices=[1, 2, 3], required=True,
                         help="1=lifecycle/exposure-gain, 2=lock-in detection, 3=streaming")
    parser.add_argument("--sys-id", type=str, default="c3cam_sl70")
    parser.add_argument("--t-acquire-us", type=float, default=DEFAULT_T_ACQUIRE_US,
                         help="Starting exposure time in microseconds (default: %(default)s)")
    parser.add_argument("--gains", type=float, nargs="+", default=list(DEFAULT_GAINS),
                         help="Analogue gains to sweep in mode 1 (default: %(default)s)")
    args = parser.parse_args()

    out_dir = make_test_dir()
    add_file_logging(out_dir)

    with HeliCamC3(args.sys_id) as cam:
        _log.info("Camera opened: %s", cam.status())
        if args.mode == 1:
            mode1_lifecycle(cam, out_dir, args.t_acquire_us, args.gains)
        elif args.mode == 2:
            mode2_lockin(cam, out_dir, args.t_acquire_us)
        elif args.mode == 3:
            mode3_streaming(cam, out_dir, args.t_acquire_us)

    _log.info("Done. Output in %s", out_dir)


if __name__ == "__main__":
    main()
