"""
rawIQ vs amplitude vs compressed amplitude -- accuracy and speed, one setup.
Run manually against real hardware. TODO.md "NEXT SESSION (2026-11-23)".

    python -m moke.devices.helicam_amp_test --note pem_on

Setup: same as ``helicam.py --example external`` / helicam_test_004 -- PEM 2f
on the encoder input (fd = f_PEM), PEM 1f on the trigger (``--trig ext``, one
start state for every acquisition), PEM on.

Bursts, same SensNFrames / SensNavM2 / SensTqp throughout:
  1. internal clock, rawIQ, off-harmonic (SensTqp 40 -> 125 kHz): offset map
     for rawIQ (same as mode 9; carries the known ~light-dependent Q bias).
  2. external, rawIQ (CamMode 0)            -> z = (I - I0) + i(Q - Q0)
  3. external, amplitude (CamMode 1, DF_A16) -> A / 16 (u12.4 fixed point)
  4. external, compressed amplitude (CamMode 1 + Comp11to8, DF_A8) -> y,
     decoded with the inverse of register description appendix A1:
     x = y for y <= 100, else 100 - ln(1 - (y - 100)/156) / 0.005.

Accuracy: each mode's 10x10 beam window (its own peak) and a background
window, as sums. rawIQ is given two ways -- |frame-mean z| (lock-in vector)
and frame-mean |z| (what a per-frame amplitude averages to, noise-biased).
Amplitude modes compute their offset on the camera from the same volume
(``--offset-method`` 0 histogram / 1 average of 2^NFrmAvg frames), so a
steady locked signal may largely vanish -- that is part of what this checks.

Speed: per acquisition wall time, bytes transferred (HE_Acquire's return),
and from the header ScanDuration (sensor time) and TimeStamp steps (start to
start); readout = TimeStamp step - ScanDuration.

Amplitude frames are 292 x 282 (FPGA-native), rawIQ 292 x 280, so maps are
compared by window sums, not pixel by pixel. Every map is saved for that.
Always restores the internal clock, free-run, Comp11to8=0 on exit.
"""

import argparse
import ctypes as ct
import logging
import os
import time

import matplotlib.pyplot as plt
import numpy as np

from moke.devices.helicam import HeliCamC3, LibHeLIC
from moke.devices.helicam_test import (
    F_SENSOR_HZ, _peak_window, add_file_logging, make_test_dir, save_json, save_table,
)

_log = logging.getLogger(__name__)


def _read_volume(cam: HeliCamC3, ctype):
    """
    Acquire + process one volume and read SDK buffer 1 with element type
    ``ctype`` (GetCamArr() always reads uint16, which is wrong for DF_A8).
    Returns (array copy, bytes transferred) or (None, bytes).
    """
    n_bytes = cam.lib.Acquire()
    if n_bytes <= 0:
        return None, n_bytes
    cam.lib.ProcessCamData(1, 0, 0)
    meta = LibHeLIC.CamDataMeta()
    cd = cam.lib.GetCamData(1, 0, ct.byref(meta))
    data = cd.contents.data
    if cd.contents.prop & LibHeLIC.CamDataProperty["DP_ENCODER"]:
        data += 1024 * 2                                  # skip header, as GetCamArr() does
    shape = tuple(meta.dimSz[meta.numDim - 1::-1])
    return LibHeLIC.Ptr2Arr(data, shape, ctype).copy(), n_bytes


def _decode_comp11to8(y):
    y = y.astype(np.float64)
    x = y.copy()
    hi = y > 100
    x[hi] = 100 - np.log(np.clip(1 - (y[hi] - 100) / 156, 1e-12, None)) / 0.005
    return np.minimum(x, 1023)            # f(1023) = 254.5, so y = 255 is saturated


def _burst(cam: HeliCamC3, out_dir: str, label: str, n_acq: int, mode: str, ctype, fmt, settings: dict):
    """Configure, discard one warm-up volume, then time ``n_acq`` acquisitions."""
    cam.set_measurement_mode(mode, warmup=False, **settings)
    if fmt:
        cam.lib.AllocCamData(1, LibHeLIC.CamDataFmt[fmt], 0, 0, 0)
    cam.dump_registers(out_dir, f"registers_{label}")
    _read_volume(cam, ctype)                              # warm-up (mode-switch settling artifact)
    vols, rows, n_fail = [], [], 0
    for i in range(n_acq):
        t0 = time.perf_counter()
        vol, n_bytes = _read_volume(cam, ctype)
        dt = (time.perf_counter() - t0) * 1000.0
        if vol is None:
            n_fail += 1
            _log.warning("[%s] acquisition %d failed (%d) after %.0f ms", label, i, n_bytes, dt)
            if n_fail >= 2:
                break
            continue
        if n_bytes < vol.nbytes / 2:                      # stale/short transfer (helicam_test_000, internal acq 0)
            _log.warning("[%s] acquisition %d: only %d bytes for a %d-byte volume, skipped", label, i, n_bytes,
                         vol.nbytes)
            continue
        n_fail = 0
        hdr, _ = cam.read_header()
        vols.append(vol)
        rows.append({"config": label, "acq": i, "wall_ms": dt, "bytes": int(n_bytes), "shape": list(vol.shape),
                     "scan_dur_ticks": hdr["scan_dur_ticks"] if hdr else None,
                     "time_stamp_ticks": hdr["time_stamp_ticks"] if hdr else None,
                     "frm_dur_ticks": hdr["frm_dur_ticks"] if hdr else None})
        _log.info("[%s] acq %d: %.1f ms, %.2f MB, shape %s", label, i, dt, n_bytes / 1e6, vol.shape)
    if vols:
        np.save(os.path.join(out_dir, f"{label}_raw0.npy"), vols[0])
    return vols, rows


def _speed(label, rows, sys_clock_hz=200e6):
    """Median wall / bytes / sensor / readout per acquisition (sys clock ~200 MHz, helicam_test_004)."""
    if not rows:
        return {"config": label}
    s = {"config": label, "n_ok": len(rows), "wall_ms": float(np.median([r["wall_ms"] for r in rows])),
         "MB": float(np.median([r["bytes"] for r in rows])) / 1e6}
    scan = [r["scan_dur_ticks"] for r in rows if r["scan_dur_ticks"]]
    ts = [r["time_stamp_ticks"] for r in rows if r["time_stamp_ticks"]]
    if scan:
        s["sensor_ms"] = float(np.median(scan)) / sys_clock_hz * 1e3
    if len(ts) > 1:
        s["start_to_start_ms"] = float(np.median(np.diff(ts))) / sys_clock_hz * 1e3
        if scan:
            s["readout_ms"] = s["start_to_start_ms"] - s["sensor_ms"]
    _log.info("[%s] speed: %s", label, {k: round(v, 2) if isinstance(v, float) else v for k, v in s.items()})
    return s


def run_test(cam: HeliCamC3, out_dir: str, n_acq: int, n_frames: int, sens_nav_m2: int, sens_tqp: int,
             trig: str, offset_method: int, note: str) -> None:
    common = {"SensNFrames": n_frames, "SensNavM2": sens_nav_m2, "BSEnable": 1, "CalDur1Cyc": 1,
              "DdsGain": 2, "EnTrigOnPos": 0}
    ext = {**common, "TrigFreeExtN": 0 if trig == "ext" else 1}
    amp = {**ext, "OffsetMethod": offset_method}
    fd_int = F_SENSOR_HZ / (8 * (sens_tqp + 30))
    configs = [
        ("rawiq", "rawIQ", ct.c_ushort, None, ext),
        ("amp", "amplitude", ct.c_ushort, None, {**amp, "Comp11to8": 0}),
        ("amp_comp", "amplitude", ct.c_uint8, "DF_A8", {**amp, "Comp11to8": 1}),
    ]
    vols, rows_all, speed = {}, [], []
    try:
        cam.set_internal_demod(fd_int)
        vols["internal"], rows = _burst(cam, out_dir, "internal", 3, "rawIQ", ct.c_ushort, None,
                                        {**common, "TrigFreeExtN": 1})
        rows_all += rows
        cam.set_external_demod(sens_tqp, both_channels=False)
        for label, mode, ctype, fmt, settings in configs:
            try:
                vols[label], rows = _burst(cam, out_dir, label, n_acq, mode, ctype, fmt, settings)
            except Exception as e:                        # e.g. SDK refuses DF_A8 -- keep the other modes
                _log.error("[%s] failed: %s", label, e)
                vols[label], rows = [], []
            rows_all += rows
            speed.append(_speed(label, rows))
    finally:
        cam.set_internal_demod(fd_int)
        cam.set_attributes(AcqStop=1, TrigFreeExtN=1, Comp11to8=0)
        cam.set_attributes(AcqStop=0)
        _log.info("Restored internal clock, TrigFreeExtN=1, Comp11to8=0")

    # --- Maps, all in rawIQ-equivalent counts (frame-averaged, then averaged over acquisitions).
    maps = {}
    if vols["internal"] and vols["rawiq"]:
        offset = np.mean([cam.crop_unphysical(v).view(np.int16).astype(np.float64).mean(axis=0)
                          for v in vols["internal"]], axis=0)
        zs = [cam.crop_unphysical(v).view(np.int16).astype(np.float64) - offset for v in vols["rawiq"]]
        zs = [d[..., 0] + 1j * d[..., 1] for d in zs]                         # (n, H, W)
        maps["rawiq_vector"] = np.mean([np.abs(z.mean(axis=0)) for z in zs], axis=0)
        maps["rawiq_magnitude"] = np.mean([np.abs(z).mean(axis=0) for z in zs], axis=0)
    if vols["amp"]:
        maps["amp"] = np.mean([v.astype(np.float64).mean(axis=0) / 16.0 for v in vols["amp"]], axis=0)
    if vols["amp_comp"]:
        maps["amp_comp_raw"] = np.mean([v.astype(np.float64).mean(axis=0) for v in vols["amp_comp"]], axis=0)
        maps["amp_comp_decoded"] = np.mean([_decode_comp11to8(v).mean(axis=0) for v in vols["amp_comp"]], axis=0)

    acc = []
    for name, m in maps.items():
        np.save(os.path.join(out_dir, f"map_{name}.npy"), m)
        win, bg = _peak_window(m), _peak_window(-m)
        row = {"map": name, "shape": list(m.shape), "win_rows": [win[0].start, win[0].stop],
               "win_cols": [win[1].start, win[1].stop], "window_sum": float(m[win].sum()),
               "background_sum": float(m[bg].sum()), "max": float(m.max())}
        acc.append(row)
    ref = next((r["window_sum"] for r in acc if r["map"] == "rawiq_vector"), None)
    for r in acc:
        r["vs_rawiq_vector"] = r["window_sum"] / ref if ref else None
        _log.info("[%s] window %s/%s sum %.0f (bg %.0f) -> %s x rawIQ vector", r["map"], r["win_rows"],
                  r["win_cols"], r["window_sum"], r["background_sum"],
                  f"{r['vs_rawiq_vector']:.3f}" if r["vs_rawiq_vector"] else "n/a")

    save_table(out_dir, "acquisitions", [{k: v for k, v in r.items() if k != "shape"} for r in rows_all])
    save_table(out_dir, "accuracy", acc)
    save_table(out_dir, "speed", speed)
    save_json(out_dir, "amp_test_summary", {
        "note": note, "n_acq": n_acq, "SensNFrames": n_frames, "SensNavM2": sens_nav_m2, "SensTqp": sens_tqp,
        "trig": trig, "OffsetMethod": offset_method, "accuracy": acc, "speed": speed})

    if maps:
        fig, axes = plt.subplots(1, len(maps), figsize=(4.5 * len(maps), 4.5))
        for ax, (name, m) in zip(np.atleast_1d(axes), maps.items()):
            im = ax.imshow(m, cmap="magma")
            fig.colorbar(im, ax=ax)
            win = _peak_window(m)
            ax.add_patch(plt.Rectangle((win[1].start - 0.5, win[0].start - 0.5), 10, 10, fill=False, ec="cyan"))
            ax.set_title(name)
        fig.suptitle(f"rawIQ vs amplitude vs compressed [{note}] -- SensNFrames {n_frames}, "
                     f"SensNavM2 {sens_nav_m2}, OffsetMethod {offset_method}, trig {trig}")
        fig.savefig(os.path.join(out_dir, "amp_test_summary.png"))
        plt.show()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-acq", type=int, default=6)
    parser.add_argument("--n-frames", type=int, default=32, help="SensNFrames (>= 10)")
    parser.add_argument("--sens-nav-m2", type=int, default=255)
    parser.add_argument("--sens-tqp", type=int, default=40,
                        help="External integration length; internal offset burst runs at the same SensTqp")
    parser.add_argument("--trig", choices=["ext", "free"], default="ext",
                        help="ext: PEM 1f on the trigger (TrigFreeExtN=0); free: free-running")
    parser.add_argument("--offset-method", type=int, choices=[0, 1], default=0,
                        help="Amplitude-mode OffsetMethod: 0 histogram, 1 average of 2^NFrmAvg frames")
    parser.add_argument("--note", type=str, default="")
    parser.add_argument("--sys-id", type=str, default="c3cam_sl70")
    args = parser.parse_args()

    out_dir = make_test_dir()
    add_file_logging(out_dir)
    with HeliCamC3(args.sys_id) as cam:
        run_test(cam, out_dir, args.n_acq, args.n_frames, args.sens_nav_m2, args.sens_tqp, args.trig,
                 args.offset_method, args.note)
        cam.dump_registers(out_dir)
    _log.info("Done. Output in %s", out_dir)


if __name__ == "__main__":
    main()
