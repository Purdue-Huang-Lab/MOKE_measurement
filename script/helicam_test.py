from helicam_c3_claude import HeliCamC3 as hcam
import numpy as np
import logging
logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)

cam = hcam("c3cam")   # adjust sys_id to your unit
logging.info(f"Camera initialized")
cam.open()
logging.info(f"Camera opened")
cam.prepare_measurement_mode("steady")  # sets mode, AllocCamData
logging.info(f"Camera prepared for measurement mode")
cam.flush()                              # drain stale USB frames
logging.info(f"Camera flushed")

raw = cam.acquire()
logging.info(f"Camera acquired raw data")
img = cam.to_numpy(raw)         
logging.info(f"Camera converted raw data to numpy array")

cam.close()

np.savetxt("output.txt", img)