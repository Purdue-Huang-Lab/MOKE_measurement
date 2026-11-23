"""
HDR linearity: steady state at t_expose_us = 2, 4, 8, 16, 32, 64 (log spaced).
Run manually against real hardware, beam on the sensor, nothing changed
during the sweep.

    python -m moke.devices.helicam_hdr_linearity_test --note beam

One acquisition per exposure; from the same raw data: HDR
(``steady_state_reformat_hdr``), long and short channels (dark-subtracted).
A linear image gives value / t_expose constant for every pixel. Pixels are
grouped by brightness (quantiles of the HDR image at the middle exposure,
per microsecond) and each group's mean value / t is plotted against t, for
HDR, long and short. HDR should stay flat across the point where a group's
long channel saturates (long ~450 -> switch to the short channel).
Saves per exposure ``t<T>_hdr / _long / _short.npy``, ``linearity.csv`` and
``hdr_linearity.png``.
"""

import argparse
import logging
import os

import matplotlib.pyplot as plt
import numpy as np

from moke.devices.helicam import HeliCamC3
from moke.devices.helicam_test import add_file_logging, make_test_dir, save_table

_log = logging.getLogger(__name__)

T_LIST = (2, 4, 8, 16, 32, 64)
QUANTILES = (50, 75, 90, 97, 99.5, 100)       # brightness group edges, percent


def run_test(cam: HeliCamC3, out_dir: str, n_frames: int, note: str) -> None:
    imgs = {}
    for t in T_LIST:
        cam.set_measurement_mode("steady", SensNFrames=n_frames)
        cam.set_acquire_time(t)
        cam.flush()
        data = cam._acquire()
        if data is None:
            _log.warning("t=%s us: acquisition failed", t)
            continue
        ch = cam._dark_subtract_channels(cam.crop_unphysical(data))
        imgs[t] = {"hdr": cam.steady_state_reformat_hdr(data), "long": ch[..., 0], "short": ch[..., 1]}
        for k, v in imgs[t].items():
            np.save(os.path.join(out_dir, f"t{t}_{k}.npy"), v)
        _log.info("t=%s us: long max %.0f, HDR max %.0f, long >= 450 on %d px", t, imgs[t]["long"].max(),
                  imgs[t]["hdr"].max(), int((imgs[t]["long"] >= 450).sum()))
    if len(imgs) < 2:
        _log.error("Not enough exposures succeeded")
        return

    ts = sorted(imgs)
    t_ref = ts[len(ts) // 2]
    ref = imgs[t_ref]["hdr"] / t_ref
    edges = np.percentile(ref, QUANTILES)
    groups = [(ref >= lo) & (ref <= hi) for lo, hi in zip(edges[:-1], edges[1:])]

    rows = []
    for g, (mask, lo, hi) in enumerate(zip(groups, edges[:-1], edges[1:])):
        for t in ts:
            row = {"group": g, "pct": f"{QUANTILES[g]}-{QUANTILES[g + 1]}", "ref_per_us_lo": float(lo),
                   "ref_per_us_hi": float(hi), "n_px": int(mask.sum()), "t_us": t,
                   "long_saturated_frac": float((imgs[t]["long"][mask] >= 450).mean())}
            for k in ("hdr", "long", "short"):
                row[f"{k}_per_us"] = float(imgs[t][k][mask].mean() / t)
            row["hdr_per_us_vs_ref"] = row["hdr_per_us"] / float(ref[mask].mean())
            rows.append(row)
    save_table(out_dir, "linearity", rows)
    for g in range(len(groups)):
        r = [x for x in rows if x["group"] == g]
        _log.info("group %s: HDR/t relative to t=%s: %s", r[0]["pct"], t_ref,
                  [round(x["hdr_per_us_vs_ref"], 3) for x in r])

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5), sharey=False)
    for ax, k in zip(axes, ("hdr", "long", "short")):
        for g in range(len(groups)):
            r = [x for x in rows if x["group"] == g]
            norm = next(x["hdr_per_us"] for x in r if x["t_us"] == t_ref)
            ax.plot([x["t_us"] for x in r], [x[f"{k}_per_us"] / norm for x in r], "o-", label=r[0]["pct"] + " %")
        ax.set_xscale("log", base=2)
        ax.axhline(1.0, color="gray", lw=0.8)
        ax.set_xlabel("t_expose_us (short)")
        ax.set_ylabel(f"{k} / t, normalised to HDR at t={t_ref}")
        ax.set_title(k)
    axes[0].legend(title="brightness group", fontsize=8)
    fig.suptitle(f"HDR linearity [{note}] -- flat = linear; long ~450 is the HDR switch point")
    fig.savefig(os.path.join(out_dir, "hdr_linearity.png"))
    plt.show()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-frames", type=int, default=32, help="SensNFrames (>= 11)")
    parser.add_argument("--note", type=str, default="")
    parser.add_argument("--sys-id", type=str, default="c3cam_sl70")
    args = parser.parse_args()

    out_dir = make_test_dir()
    add_file_logging(out_dir)
    with HeliCamC3(args.sys_id) as cam:
        run_test(cam, out_dir, args.n_frames, args.note)
        cam.dump_registers(out_dir)
    _log.info("Done. Output in %s", out_dir)


if __name__ == "__main__":
    main()
