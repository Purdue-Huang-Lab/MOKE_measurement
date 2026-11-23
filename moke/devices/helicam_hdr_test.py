"""
Does the SDK's own HDR merge (intensity mode, DF_Hf) work, and how does it
compare with our short-channel image? Run manually against real hardware.

    python -m moke.devices.helicam_hdr_test --t-exp-us 10 40 --note beam

Programmer manual, CamMode 3: with the output buffer allocated as DF_Hf
(32-bit float) the SDK does the dark subtraction and HDR merge itself and
returns a (SensNFrames - SensNDarkFrames - 3, ~300, ~300) stack of long,
short and HDR frames. Our driver instead allocates DF_I16Q16 and returns the
dark-subtracted short channel (data_reformat). Untested so far.

Per exposure, same steady settings both ways:
  1. DF_Hf: the SDK stack, saved whole (hdr_stack_t<T>.npy); per-frame stats
     logged so we can tell which frame is long / short / HDR.
  2. DF_I16Q16 (our path): short and long channels (ours_t<T>.npy, (H, W, 2)
     = [long, short]), via _dark_subtract_channels().
Use at least one exposure where the long image saturates on the beam -- that
is where an HDR merge should differ from the plain long image.
"""

import argparse
import ctypes as ct
import logging
import os

import matplotlib.pyplot as plt
import numpy as np

from moke.devices.helicam import HeliCamC3, LibHeLIC
from moke.devices.helicam_amp_test import _read_volume
from moke.devices.helicam_test import add_file_logging, make_test_dir, save_json, save_table

_log = logging.getLogger(__name__)


def run_test(cam: HeliCamC3, out_dir: str, t_exp_list, n_frames: int, note: str) -> None:
    rows, summary = [], {"note": note, "SensNFrames": n_frames, "exposures": {}}
    for t in t_exp_list:
        settings = {"SensNFrames": n_frames, "SensExpTime": int(t), "SensExpTimeMult": 0}

        # 1. SDK HDR path (DF_Hf)
        stack = None
        try:
            cam.set_measurement_mode("steady", warmup=False, **settings)
            cam.lib.AllocCamData(1, LibHeLIC.CamDataFmt["DF_Hf"], 0, 0, 0)
            _read_volume(cam, ct.c_float)                                 # warm-up
            for _ in range(3):                                            # skip stale short transfers (run 004, t=10)
                stack, n_bytes = _read_volume(cam, ct.c_float)
                if stack is not None and n_bytes >= stack.nbytes / 4:
                    break
                _log.warning("t=%s us: short transfer (%d bytes), reading again", t, n_bytes)
        except Exception as e:
            _log.error("t=%s us: DF_Hf path failed: %s", t, e)
        cam.dump_registers(out_dir, f"registers_t{t}")
        if stack is not None:
            np.save(os.path.join(out_dir, f"hdr_stack_t{t}.npy"), stack)
            _log.info("t=%s us: DF_Hf stack shape %s, %d bytes", t, stack.shape, n_bytes)
            for k in range(stack.shape[0]):
                f = stack[k]
                rows.append({"t_exp_us": t, "source": "sdk_DF_Hf", "frame": k, "mean": float(f.mean()),
                             "p99": float(np.percentile(f, 99)), "max": float(f.max()), "min": float(f.min())})
        else:
            _log.warning("t=%s us: no DF_Hf data", t)

        # 2. Our path (DF_I16Q16 -> dark-subtracted long/short channels)
        cam.set_measurement_mode("steady", **settings)                    # re-allocates DF_I16Q16, warm-up
        data = cam._acquire()
        ours = None if data is None else cam._dark_subtract_channels(cam.crop_unphysical(data))
        if ours is not None:
            np.save(os.path.join(out_dir, f"ours_t{t}.npy"), ours)
            for ch, name in ((0, "ours_long"), (1, "ours_short")):
                f = ours[..., ch]
                rows.append({"t_exp_us": t, "source": name, "frame": None, "mean": float(f.mean()),
                             "p99": float(np.percentile(f, 99)), "max": float(f.max()), "min": float(f.min())})
        summary["exposures"][t] = {"sdk_stack_shape": None if stack is None else list(stack.shape),
                                   "ours_shape": None if ours is None else list(ours.shape)}

        # Figure: first 3 SDK frames + our long/short
        panels = []
        if stack is not None:
            panels += [(f"SDK frame {k}", stack[k]) for k in range(min(3, stack.shape[0]))]
            if stack.shape[0] > 3:
                panels.append((f"SDK mean of frames 2..{stack.shape[0] - 1}", stack[2:].mean(axis=0)))
        if ours is not None:
            panels += [("ours long (ch 0)", ours[..., 0]), ("ours short (ch 1)", ours[..., 1])]
        if panels:
            fig, axes = plt.subplots(1, len(panels), figsize=(4.2 * len(panels), 4))
            for ax, (title, p) in zip(np.atleast_1d(axes), panels):
                im = ax.imshow(p, cmap="magma")
                fig.colorbar(im, ax=ax)
                ax.set_title(title)
            fig.suptitle(f"HDR test [{note}] -- SensExpTime {t} us, SensNFrames {n_frames}")
            fig.savefig(os.path.join(out_dir, f"hdr_test_t{t}.png"))
            plt.close(fig)

    save_table(out_dir, "hdr_frame_stats", rows)
    save_json(out_dir, "hdr_test_summary", summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--t-exp-us", type=int, nargs="+", default=[10, 40],
                        help="Short exposure times in us (SensExpTime, Mult 0); include one that saturates the long image")
    parser.add_argument("--n-frames", type=int, default=32, help="SensNFrames (>= SensNDarkFrames + 4 = 11)")
    parser.add_argument("--note", type=str, default="")
    parser.add_argument("--sys-id", type=str, default="c3cam_sl70")
    args = parser.parse_args()

    out_dir = make_test_dir()
    add_file_logging(out_dir)
    with HeliCamC3(args.sys_id) as cam:
        run_test(cam, out_dir, args.t_exp_us, args.n_frames, args.note)
        cam.dump_registers(out_dir)
    _log.info("Done. Output in %s", out_dir)


if __name__ == "__main__":
    main()
