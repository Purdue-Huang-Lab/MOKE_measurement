"""
HeliCam C3 external-reference (ExtTqp / ExtTqpPuls) and encoder-header tests
-- run manually against real hardware. TODO.md "Next" item 1 (old task 6:
``ExtTqpPuls`` single-channel wiring, plus the start-edge test).

Same conventions as ``helicam_test.py`` (fresh ``helicam_test_NNN`` folder per
run, run_log.txt, registers dumped at the end); helpers are imported from it.

Usage::

    python -m moke.devices.helicam_exttqp_test --test header
    python -m moke.devices.helicam_exttqp_test --test puls --note ref_2f
    python -m moke.devices.helicam_exttqp_test --test start --trig both --note pem_on
    python -m moke.devices.helicam_exttqp_test --test start --trig ext --note pem_rtd0 --window 140 135

Every acquisition's volume header is read from the SDK raw buffer (register
description ch. 3; ``LibHeLIC.CamDataHdr``): sync word 0xC000, Nframes,
FrameDur (measured frame duration, 70 MHz ticks), ScanDuration / TimeStamp
(system clock ticks), Nvolume, and one 16-bit zTag (quadrature position
counter of IN3/IN4, manual §2.4.2) per frame. FrameDur gives the demod
frequency directly -- fd = (Nc+1) * 70 MHz / FrameDur, Nc = 2*SensNavM2+2 --
instead of mode 9's wall-time / USB-overhead model.

--test header -- encoder read format (no reference needed):
    internal clock only. Checks the header parses (sync word, Nframes ==
    SensNFrames), that FrameDur matches the known internal fd (validates the
    70 MHz unit and the Nc+1 model), infers the ScanDuration clock rate, and
    records the zTags (whatever IN3/IN4 are doing -- with the PEM ref plugged
    in they should move, unplugged they should sit still).

--test puls -- which encoder input is driven, and how many edges count:
    internal burst (offset map), then ExtTqp=1 free-running with
    ExtTqpPuls=0 and ExtTqpPuls=1. Expect, with the 2f ref on ONE input:
      * ExtTqpPuls=1: fd = f_PEM (both flanks of one channel).
      * ExtTqpPuls=0: fd = f_PEM if the driven input is the "one channel"
        (IN3 pre-Q3-2014, IN4 after), else no pulses -> acquisitions time out.
    fd = 2 f_PEM in either config -> both channels toggle (4 edges/period).

--test start -- start edge / start trigger (TODO "External phase / start edge"):
    internal burst (offset map), then ExtTqp=1 with
      * free: TrigFreeExtN=1 (current mode 9 setup: random start edge,
        expect up to 4 phase states on a pi/2 grid), and/or
      * ext:  TrigFreeExtN=0, EnTrigOnPos=0 (manual §4.4) with a PEM-locked
        start pulse on the trigger BNC (e.g. the 1f ref). Expect one state.
    Reports the 10x10 beam-window vector per acquisition, its phase relative
    to acquisition 0 and the pi/2 state it falls in. Run at RTD=0 too: with
    the default internal SensTqp = external SensTqp (40, off-harmonic) this is
    also the matched-SensTqp zero test from TODO task 1. Use --window to put
    the box where a PEM-on run found the beam (RTD=0 runs pick it off-beam).

All acquisitions of every config are kept as frame means
(``<config>_acq_means.npy``, (n_acq, H, W, 2) float32, raw counts), plus the
first raw volume and first raw header of each config. Always restores
ExtTqp=0, ExtTqpPuls=0, TrigFreeExtN=1 on exit.
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
    F_SENSOR_HZ, _peak_window, _timed, add_file_logging, make_test_dir, save_json, save_table,
)

_log = logging.getLogger(__name__)

SYNCWORD = 0xC000
HDR_WORDS = 1024                    # 2 kB header, LibHeLIC.CamDataHdr / GetCamArr's skip
SENS_NAV_M2, N_FRAMES = 255, 32
NC = 2 * SENS_NAV_M2 + 2


# ----------------------------------------------------------------------
# Header (encoder read format)
# ----------------------------------------------------------------------

def read_header(cam: HeliCamC3):
    """
    Parse the volume header of the last acquisition. Tries SDK buffer 0 (raw,
    where the programmer manual reads zTags from) then buffer 1 (processed;
    has the header only if its DP_ENCODER flag is set). Returns (dict, raw
    header words as uint16) or (None, None) if no buffer carries the sync word.
    """
    for idx in (0, 1):
        cd = cam.lib.GetCamData(idx, 0, 0)
        if not cd or not cd.contents.data:
            continue
        words = np.frombuffer(ct.string_at(cd.contents.data, 2 * HDR_WORDS), dtype="<u2").copy()
        # Sync word is at word 0 on our unit (run 001), not word 1 as in the
        # register description / CamDataHdr; every other field is where they say.
        if words[0] != SYNCWORD:
            continue
        h = LibHeLIC.CamDataHdr.from_buffer_copy(words.tobytes())
        n = int(h.nFrames)
        ztags = np.array(h.zTags[:min(n, 0x200)], dtype=np.uint16)
        dz = np.diff(ztags.astype(np.int64))
        dz = (dz + 2 ** 15) % 2 ** 16 - 2 ** 15                 # 16-bit wrap -> signed step
        return {
            "buffer": idx, "prop": int(cd.contents.prop),
            "dp_encoder": bool(cd.contents.prop & LibHeLIC.CamDataProperty["DP_ENCODER"]),
            "n_frames": n, "n_volume": int(h.nVolume),
            "frm_dur_ticks": int(h.frmDur),
            "scan_dur_ticks": int(h.scanDur[0]) + (int(h.scanDur[1]) << 32),
            "time_stamp_ticks": int(h.timeStamp[0]) + (int(h.timeStamp[1]) << 32),
            "ztags": ztags.tolist(),
            "ztag_step_min": int(dz.min()) if dz.size else None,
            "ztag_step_max": int(dz.max()) if dz.size else None,
            "ztag_step_mean": float(dz.mean()) if dz.size else None,
        }, words
    return None, None


def dump_buffer_info(cam: HeliCamC3, out_dir: str, label: str) -> None:
    """
    Diagnostic for when read_header() finds no sync word: log what SDK buffers
    0 and 1 actually are (size / format / prop), where 0xC000 occurs in their
    first and last 8 kB, and the FPGA header feature flags; save those bytes as
    ``<label>_buf<idx>_head.npy`` / ``_tail.npy`` (uint16) for offline digging.
    """
    for idx in (0, 1):
        cd = cam.lib.GetCamData(idx, 0, 0)
        if not cd:
            _log.info("[%s] buffer %d: GetCamData returned NULL", label, idx)
            continue
        c = cd.contents
        _log.info("[%s] buffer %d: size %d, format %d, prop 0x%x, data %s", label, idx, c.size, c.format,
                  c.prop, "set" if c.data else "NULL")
        if not c.data or c.size < 4:
            continue
        n = min(int(c.size), 8192) // 2 * 2
        parts = {"head": (c.data, n), "tail": (c.data + int(c.size) - n, n)}
        for name, (addr, nb) in parts.items():
            w = np.frombuffer(ct.string_at(addr, nb), dtype="<u2").copy()
            np.save(os.path.join(out_dir, f"{label}_buf{idx}_{name}.npy"), w)
            _log.info("[%s] buffer %d %s: first words %s, 0xC000 at word %s", label, idx, name,
                      [hex(x) for x in w[:8]], np.flatnonzero(w == SYNCWORD)[:10].tolist())
    try:
        feat = cam.lib.GetSysDesc().contents.fpga.contents.feature
        flags = {k: bool(feat >> LibHeLIC.FeatureFPGA[k] & 1)
                 for k in ("FF_hasScanHeader", "FF_extended_header", "FF_mhtheader", "FF_mhtheader_suppress")}
        _log.info("[%s] FPGA feature 0x%x: %s", label, feat, flags)
    except Exception as e:
        _log.info("[%s] could not read FPGA feature flags: %s", label, e)


def _fd_from_header(hdr):
    if not hdr or hdr["frm_dur_ticks"] <= 0:
        return None
    return (NC + 1) * F_SENSOR_HZ / hdr["frm_dur_ticks"]


# ----------------------------------------------------------------------
# Acquisition
# ----------------------------------------------------------------------

def _burst(cam: HeliCamC3, out_dir: str, label: str, n_acq: int, settings: dict):
    """
    Configure rawIQ with ``settings`` and take ``n_acq`` acquisitions (no flush
    in between), reading the header after each. Keeps only the per-acquisition
    frame mean (n_acq, H, W, 2) plus the first raw volume / header. Stops after
    2 consecutive failures (no pulses / no trigger costs seconds, not minutes).
    """
    _timed(f"set_measurement_mode('rawIQ') [{label}]", cam.set_measurement_mode, "rawIQ", **settings)
    cam.dump_registers(out_dir, f"registers_{label}")
    means, rows = [], []
    n_fail = 0
    for i in range(n_acq):
        t0 = time.perf_counter()
        data = cam._acquire()
        dt = (time.perf_counter() - t0) * 1000.0
        if data is None:
            n_fail += 1
            _log.warning("[%s] acquisition %d failed after %.0f ms", label, i, dt)
            if n_fail >= 2:
                _log.warning("[%s] 2 consecutive failures, giving up on this config", label)
                break
            continue
        n_fail = 0
        hdr, words = read_header(cam)
        vol = cam.crop_unphysical(data).view(np.int16)
        if not means:
            np.save(os.path.join(out_dir, f"{label}_raw0.npy"), vol.copy())
            if words is not None:
                np.save(os.path.join(out_dir, f"{label}_header0_words.npy"), words)
            else:
                dump_buffer_info(cam, out_dir, label)
        means.append(vol.astype(np.float32).mean(axis=0))
        fd = _fd_from_header(hdr)
        row = {"config": label, "acq": i, "wall_ms": dt, "header_ok": hdr is not None,
               "fd_header_hz": fd}
        if hdr:
            row.update({k: hdr[k] for k in ("buffer", "n_frames", "n_volume", "frm_dur_ticks",
                                            "scan_dur_ticks", "time_stamp_ticks", "ztag_step_min",
                                            "ztag_step_max", "ztag_step_mean")})
            row["ztags"] = hdr["ztags"]
        rows.append(row)
        _log.info("[%s] acq %d: %.1f ms, header %s, fd %s, zTag step %s..%s", label, i, dt,
                  "ok" if hdr else "NOT FOUND", f"{fd:.1f} Hz" if fd else "n/a",
                  hdr["ztag_step_min"] if hdr else "-", hdr["ztag_step_max"] if hdr else "-")
    if means:
        np.save(os.path.join(out_dir, f"{label}_acq_means.npy"), np.stack(means))
    if any("ztags" in r for r in rows):
        np.save(os.path.join(out_dir, f"{label}_ztags.npy"),
                np.array([r["ztags"] for r in rows if "ztags" in r], dtype=np.uint16))
    return means, rows


def _config_summary(label, rows, settings, f_pem_hz=None):
    """Header-derived numbers for one config (logged and returned for the json)."""
    ok = [r for r in rows if r["header_ok"]]
    s = {"config": label, "settings": settings, "n_ok": len(rows), "n_header_ok": len(ok)}
    if not ok:
        _log.info("[%s] %d acquisitions, no header parsed", label, len(rows))
        return s
    fds = [r["fd_header_hz"] for r in ok if r["fd_header_hz"]]
    t_frame = np.median([r["frm_dur_ticks"] for r in ok]) / F_SENSOR_HZ
    # ScanDuration clock: ticks per (Nframes x measured frame time). Expect a
    # round number (200 MHz system clock per the PowerCtrl description?).
    f_sys = float(np.median([r["scan_dur_ticks"] / (r["n_frames"] * r["frm_dur_ticks"] / F_SENSOR_HZ)
                             for r in ok if r["frm_dur_ticks"] > 0]))
    nvol = [r["n_volume"] for r in ok]
    ts = [r["time_stamp_ticks"] for r in ok]
    s.update({
        "n_frames_header": sorted({r["n_frames"] for r in ok}), "fd_header_median_hz": float(np.median(fds)),
        "fd_header_spread_hz": float(np.ptp(fds)), "frame_s": float(t_frame),
        "scan_clock_hz_est": f_sys, "n_volume_steps": np.diff(nvol).tolist(),
        "time_stamp_steps_s": (np.diff(ts) / f_sys).tolist(),
        "ztag_step_range": [min(r["ztag_step_min"] for r in ok), max(r["ztag_step_max"] for r in ok)],
        "ztag_step_mean": float(np.mean([r["ztag_step_mean"] for r in ok])),
    })
    _log.info("[%s] header: Nframes %s, fd %.1f Hz (spread %.1f)%s, frame %.3f ms, ScanDuration clock "
              "~%.2f MHz, Nvolume steps %s, zTag step range %s (mean %.2f/frame)",
              label, s["n_frames_header"], s["fd_header_median_hz"], s["fd_header_spread_hz"],
              f" = {s['fd_header_median_hz'] / f_pem_hz:.4f} x f_PEM" if f_pem_hz else "",
              t_frame * 1e3, f_sys / 1e6, s["n_volume_steps"], s["ztag_step_range"], s["ztag_step_mean"])
    return s


def _restore(cam: HeliCamC3):
    # Never leave the camera on ExtTqp / external trigger -- every later mode
    # would stall (or silently run off the PEM) without knowing why.
    cam.set_attributes(AcqStop=1, ExtTqp=0, ExtTqpPuls=0, TrigFreeExtN=1)
    cam.set_attributes(AcqStop=0)
    _log.info("Restored ExtTqp=0, ExtTqpPuls=0, TrigFreeExtN=1")


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------

def run_test(cam: HeliCamC3, out_dir: str, test: str, f_pem_hz: float, n_acq: int, ext_sens_tqp: int,
             int_sens_tqp: int, ext_tqp_puls: int, trig: str, window, note: str) -> None:
    common = {"SensNFrames": N_FRAMES, "SensNavM2": SENS_NAV_M2, "BSEnable": 1, "CalDur1Cyc": 1,
              "DdsGain": 2, "EnTrigOnPos": 0}
    int_settings = {**common, "SensTqp": int_sens_tqp, "ExtTqp": 0, "ExtTqpPuls": 0, "TrigFreeExtN": 1}
    fd_int = F_SENSOR_HZ / (8 * (int_sens_tqp + 30))

    ext_configs = []
    if test == "puls":
        for p in (0, 1):
            ext_configs.append((f"ext_puls{p}", {**common, "SensTqp": ext_sens_tqp, "ExtTqp": 1,
                                                 "ExtTqpPuls": p, "TrigFreeExtN": 1}))
    elif test == "start":
        for t in (("free", "ext") if trig == "both" else (trig,)):
            ext_configs.append((f"ext_trig{t}", {**common, "SensTqp": ext_sens_tqp, "ExtTqp": 1,
                                                 "ExtTqpPuls": ext_tqp_puls,
                                                 "TrigFreeExtN": 1 if t == "free" else 0}))
        if trig in ("ext", "both"):
            _log.warning("Trigger BNC: needs the opto spec (4.5-6 V, 8-15 mA); a 50 kHz 1f ref has a 10 us "
                         "half period, at the edge of the >10 us falling-edge width noted for older units.")
    if ext_configs and (ext_sens_tqp + 11) / 35e6 >= 0.5 / (2 * f_pem_hz):
        _log.warning("SensTqp=%d integrates %.2f us, >= the 2f reference half-period %.2f us (manual §4.4)",
                     ext_sens_tqp, (ext_sens_tqp + 11) / 35e6 * 1e6, 0.5 / (2 * f_pem_hz) * 1e6)

    summary = {"test": test, "note": note, "f_pem_hz": f_pem_hz, "n_acq": n_acq, "SensNFrames": N_FRAMES,
               "SensNavM2": SENS_NAV_M2, "int_SensTqp": int_sens_tqp, "ext_SensTqp": ext_sens_tqp,
               "fd_int_model_hz": fd_int, "configs": []}
    rows_all = []
    results = {}
    try:
        n_int = n_acq if test == "header" else 3
        means, rows = _burst(cam, out_dir, "internal", n_int, int_settings)
        s = _config_summary("internal", rows, int_settings)
        if "fd_header_median_hz" in s:
            s["fd_header_over_model"] = s["fd_header_median_hz"] / fd_int
            _log.info("[internal] header fd / model fd (70 MHz/(8(SensTqp+30)) = %.1f Hz) = %.4f  "
                      "(1 -> FrameDur unit and Nc+1 model both right)", fd_int, s["fd_header_over_model"])
        summary["configs"].append(s)
        rows_all += rows
        results["internal"] = means
        for label, settings in ext_configs:
            means, rows = _burst(cam, out_dir, label, n_acq, settings)
            summary["configs"].append(_config_summary(label, rows, settings, f_pem_hz))
            rows_all += rows
            results[label] = means
    finally:
        _restore(cam)

    if test == "puls":
        _log.info("puls: expected fd = f_PEM (%.1f Hz) for the active channel(s) seeing one 2f input; "
                  "2 f_PEM -> both channels toggle; timeouts -> that config's channel is not driven", f_pem_hz)

    # --- Beam-window vectors relative to the internal-burst offset map.
    if results["internal"] and any(results[label] for label, _ in ext_configs):
        offset = np.mean(results["internal"], axis=0).astype(np.float64)
        z = {label: [(m - offset)[..., 0] + 1j * (m - offset)[..., 1] for m in results[label]]
             for label, _ in ext_configs if results[label]}
        first = next(iter(z))
        amp_first = np.mean([np.abs(zk) for zk in z[first]], axis=0)
        if window:
            win = (slice(window[0], window[0] + 10), slice(window[1], window[1] + 10))
        else:
            win = _peak_window(amp_first)
        _log.info("Beam window rows %d-%d cols %d-%d (%s)", win[0].start, win[0].stop - 1,
                  win[1].start, win[1].stop - 1, "--window" if window else f"peak of {first} |z|")
        vec_rows = []
        for label, zs in z.items():
            v = np.array([zk[win].sum() for zk in zs])
            dphi = np.angle(v * np.conj(v[0]))
            state = np.round(dphi / (np.pi / 2)).astype(int) % 4
            resid = dphi - np.round(dphi / (np.pi / 2)) * (np.pi / 2)
            for k in range(len(v)):
                vec_rows.append({"config": label, "k": k, "abs_vector_sum": float(np.abs(v[k])),
                                 "phase_rad": float(np.angle(v[k])), "dphase_rad": float(dphi[k]),
                                 "pi2_state": int(state[k]), "pi2_residual_rad": float(resid[k]),
                                 "abs_sum": float(np.abs(zs[k][win]).sum())})
            _log.info("[%s] window |vector sum| %s; phase vs acq 0 %s rad; pi/2 states %s, residual rms "
                      "%.3f rad", label, np.round(np.abs(v)).astype(int).tolist(), np.round(dphi, 2).tolist(),
                      state.tolist(), float(np.sqrt((resid ** 2).mean())))
            summary["configs"] = [dict(c, window_vectors={
                "abs": np.abs(v).tolist(), "dphase_rad": dphi.tolist(), "pi2_states": state.tolist(),
                "n_states": len(set(state.tolist())), "dphase_spread_rad": float(np.ptp(dphi))})
                if c["config"] == label else c for c in summary["configs"]]
        summary["window"] = {"rows": [win[0].start, win[0].stop], "cols": [win[1].start, win[1].stop]}
        save_table(out_dir, "window_vectors", vec_rows)

        fig, axes = plt.subplots(1, len(z) + 1, figsize=(5 * (len(z) + 1), 4.5))
        for ax, (label, zs) in zip(axes, z.items()):
            im = ax.imshow(np.mean([np.abs(zk) for zk in zs], axis=0), cmap="magma")
            fig.colorbar(im, ax=ax)
            ax.add_patch(plt.Rectangle((win[1].start - 0.5, win[0].start - 0.5), 10, 10, fill=False, ec="cyan"))
            ax.set_title(f"{label}: mean over acq of |z| [counts]")
        ax = axes[-1]
        for label, zs in z.items():
            v = np.array([zk[win].sum() for zk in zs])
            ax.plot(v.real, v.imag, "o", label=label)
        ax.plot(0, 0, "k+")
        ax.set_aspect("equal")
        ax.set_xlabel("I (window sum)")
        ax.set_ylabel("Q (window sum)")
        ax.legend()
        ax.set_title("window vector per acquisition")
        fig.suptitle(f"ExtTqp {test} test [{note}] -- f_PEM={f_pem_hz / 1e3:.3f} kHz, "
                     f"SensTqp int {int_sens_tqp} / ext {ext_sens_tqp}")
        fig.savefig(os.path.join(out_dir, f"exttqp_{test}_summary.png"))

    save_table(out_dir, "acquisitions", [{k: v for k, v in r.items() if k != "ztags"} for r in rows_all])
    save_json(out_dir, f"exttqp_{test}_summary", summary)
    plt.show()


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--test", choices=["header", "puls", "start"], required=True)
    parser.add_argument("--f-pem-hz", type=float, default=50021.3,
                        help="PEM 1f frequency (default: %(default)s, scoped 2026-11-20)")
    parser.add_argument("--n-acq", type=int, default=None,
                        help="Acquisitions per config (default: 20 for start, 6 otherwise)")
    parser.add_argument("--ext-sens-tqp", type=int, default=40,
                        help="SensTqp (per-sample integration) in ExtTqp mode (default: %(default)s)")
    parser.add_argument("--int-sens-tqp", type=int, default=None,
                        help="SensTqp of the internal burst (default: same as --ext-sens-tqp, i.e. matched "
                             "integration; 40 -> fd 125 kHz, off-harmonic)")
    parser.add_argument("--ext-tqp-puls", type=int, choices=[0, 1], default=1,
                        help="ExtTqpPuls for --test start (default: %(default)s)")
    parser.add_argument("--trig", choices=["free", "ext", "both"], default="both",
                        help="Start trigger for --test start: free (TrigFreeExtN=1), ext (TrigFreeExtN=0, "
                             "PEM-locked pulse on the trigger BNC) or both (default: %(default)s)")
    parser.add_argument("--window", type=int, nargs=2, metavar=("ROW", "COL"), default=None,
                        help="Top-left of the 10x10 beam window (default: peak of the first external |z|)")
    parser.add_argument("--note", type=str, default="",
                        help="Free-text label saved with the results, e.g. pem_on / pem_rtd0")
    parser.add_argument("--sys-id", type=str, default="c3cam_sl70")
    args = parser.parse_args()

    n_acq = args.n_acq or (20 if args.test == "start" else 6)
    int_sens_tqp = args.ext_sens_tqp if args.int_sens_tqp is None else args.int_sens_tqp

    out_dir = make_test_dir()
    add_file_logging(out_dir)
    with HeliCamC3(args.sys_id) as cam:
        _log.info("Camera opened: %s", cam.status())
        run_test(cam, out_dir, args.test, args.f_pem_hz, n_acq, args.ext_sens_tqp, int_sens_tqp,
                 args.ext_tqp_puls, args.trig, args.window, args.note)
        cam.dump_registers(out_dir)
    _log.info("Done. Output in %s", out_dir)


if __name__ == "__main__":
    main()
