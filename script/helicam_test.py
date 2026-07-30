import helicam_c3_claude as hcam
import numpy as np
cam = hcam("c3cam")   # adjust sys_id to your unit
cam.open()
cam.prepare_measurement_mode("steady")  # sets mode, AllocCamData
cam.flush()                              # drain stale USB frames

raw = cam.acquire()
img = cam.to_numpy(raw)         

cam.close()

np.savetxt("output.txt", img)