from moke.devices.helicam import HeliCamC3 as hcam
import numpy as np
import logging
import matplotlib.pyplot as plt
import matplotlib
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s:%(name)s:%(message)s")
_log = logging.getLogger(__name__)

with hcam("c3cam_sl70") as cam:          # opens; closes even if this block raises
    _log.info("Camera opened")

    cam.set_measurement_mode("steady")   # sets mode, AllocCamData
    _log.info("Camera prepared for measurement mode")

    cam.flush()                              # drain stale USB frames (bounded)
    _log.info("Camera flushed")

    raw = cam.acquire()
    if raw is None:
        raise RuntimeError("acquire() returned no data (timeout or missed trigger)")
    _log.info("Acquired raw data: shape=%s dtype=%s", raw.shape, raw.dtype)

    img = cam.to_numpy(raw)
    _log.info("Converted to image: shape=%s dtype=%s min=%d max=%d mean=%.1f",
              img.shape, img.dtype, img.min(), img.max(), img.mean())

np.savetxt("output.txt", img, fmt="%d")
_log.info("Wrote output.txt")

matplotlib.use('qtagg')
fig, axes = plt.subplots(1, 2, figsize=(8, 4))

axes[0].imshow(img[:,:], cmap="gray")
plt.show()