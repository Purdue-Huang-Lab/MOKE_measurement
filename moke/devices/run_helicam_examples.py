"""
Run the four HeliCamC3 usage examples one after another, asking before each.

    python -m moke.devices.run_helicam_examples

Press Enter to run an example, type s to skip it, q to quit.
"external" needs the PEM 2f on the encoder input and the PEM 1f on the trigger.

Saves like helicam_test.py: a new helicam_test_data/helicam_test_NNN folder
with run_log.txt, and per example <name>.npy, <name>.png and
registers_<name>.json, plus registers.json at the end.
"""

import os

import matplotlib.pyplot as plt
import numpy as np

from moke.devices.helicam import EXAMPLES, HeliCamC3
from moke.devices.helicam_test import _log, add_file_logging, make_test_dir


def save_result(out_dir: str, name: str, img) -> None:
    np.save(os.path.join(out_dir, name + ".npy"), img)
    panels = [("image", img)] if img.ndim == 2 else [("I", img[..., 0]), ("Q", img[..., 1])]
    fig, axes = plt.subplots(1, len(panels), figsize=(5 * len(panels), 4.5))
    for ax, (title, p) in zip(np.atleast_1d(axes), panels):
        im = ax.imshow(p, cmap="magma")
        fig.colorbar(im, ax=ax)
        ax.set_title(f"{title} [counts]")
    fig.suptitle(f"example: {name}")
    fig.savefig(os.path.join(out_dir, name + ".png"))
    plt.close(fig)


out_dir = make_test_dir()
add_file_logging(out_dir)
with HeliCamC3() as cam:
    for name in ("steady", "stream", "internal", "external"):
        answer = input(f"\nNext: {name}. Enter = run, s = skip, q = quit: ").strip().lower()
        if answer == "q":
            break
        if answer == "s":
            continue
        try:
            img = EXAMPLES[name](cam)
            cam.dump_registers(out_dir, f"registers_{name}")
            if img is None:
                _log.warning("%s: no data returned (acquisition failed)", name)
            else:
                save_result(out_dir, name, img)
                _log.info("%s: done, saved %s.png", name, name)
        except Exception as e:
            _log.exception("%s: FAILED -- %s", name, e)
    cam.dump_registers(out_dir)
_log.info("Finished. Output in %s", out_dir)
