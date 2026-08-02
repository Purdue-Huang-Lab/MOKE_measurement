# Work flow chart for time-resolved magnetic Kerr rotation setup planning
This file is the work flow chart for the optical and code work flow of a TR-MOKE measurement
## Optical setup:
Probe: monochromic, wide field, linearly polarized light, focused into theback focal plane of the objective forming a wide-field imaging.
    Notice: high-NA objective cause mixing of polarization state. It is preferred to have laser polarization orthoigonal to objective axes.  
Pump: focused, chopped light. 
Measurement arm: goes through a PEM at 0 degree, an analyzer polarizer at 45 degree, then lock-in camera. Lock-in camera is demodulated at PEM frequency, and triggered by chopper   
## experiment workflows, focused on code-relavent procedures:
1. Coarse alignment of optics as normal
2. Align signal to camera, under intensity mode, streaming. Make sure signal is at center of image.
3. Test polarization and demod - away from sample, add a 5 deg half wave plate. 
4. Optimize polarization for test: a ~45 degree analyzer with original polarization is good enough. Actual polarization is not very sensitive.
5. Test trigger (?) See even/odd representative frames in code.
6. Measure
## code workflow
1. Initialize all devices (licam, delay stage)
2. Steady state streaming
3. Calibrate with given HWP angle
4. Triggering test
5. Find t0 with manual time scan
6. Scan