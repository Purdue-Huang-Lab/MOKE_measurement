# code to analyze numpy output from helicam_test.py.

import numpy as np
import matplotlib
matplotlib.use('TkAgg')
from matplotlib import pyplot as plt
import sys

# frame = np.load(r"C:\Users\Huang Lab\Documents\GitHub\MOKE_measurement\moke\devices\helicam_test_data\helicam_test_000\mode2_rawiq_amplitude.npy")
# print(frame.shape)

# for test mode 1
# dark = np.mean(frame[:7, :, :, 1], axis=0)
# signal = np.mean(frame[7:, :, :, 1], axis=0)
# valid = signal - dark

# fig, ax = plt.subplots(1, 3, figsize=(12, 4))
# ax[0].imshow(dark, cmap='gray')
# ax[1].imshow(signal, cmap='gray')
# ax[2].imshow(valid, cmap='gray')

# fig.colorbar(ax[2].images[0], ax=ax[2])
# plt.show()

# for test mode 2
fs = [
    r'C:\Users\Huang Lab\Documents\GitHub\MOKE_measurement\moke\devices\helicam_test_data\260811-lockin mode\mode2_steady_frame.npy',
    r'C:\Users\Huang Lab\Documents\GitHub\MOKE_measurement\moke\devices\helicam_test_data\260811-lockin mode\mode2_rawiq_I.npy',
    r'C:\Users\Huang Lab\Documents\GitHub\MOKE_measurement\moke\devices\helicam_test_data\260811-lockin mode\mode2_rawiq_Q.npy',
    r'C:\Users\Huang Lab\Documents\GitHub\MOKE_measurement\moke\devices\helicam_test_data\260811-lockin mode\mode2_rawiq_amplitude.npy',
    r'C:\Users\Huang Lab\Documents\GitHub\MOKE_measurement\moke\devices\helicam_test_data\260811-lockin mode\mode2_rawiq_phase.npy',
    r'C:\Users\Huang Lab\Documents\GitHub\MOKE_measurement\moke\devices\helicam_test_data\260811-lockin mode\mode2_amplitude_frame.npy',
    r'C:\Users\Huang Lab\Documents\GitHub\MOKE_measurement\moke\devices\helicam_test_data\260811-lockin mode\mode2_smooth_amplitude_frame.npy'
]
names = [
    "steady frame",
    "rawIQ I",
    "rawIQ Q",
    "rawIQ amplitude",
    "rawIQ phase",
    "amplitude frame",
    "smooth amplitude frame"
]
frames = []
for i, f in enumerate(fs):
    print(f"Loading {names[i]}, shape: {np.load(f).shape}")
    frames.append(np.load(f))

# amp = frames[0]
# fig, ax = plt.subplots(1, 2, figsize=(12, 6))
# ax[0].imshow(amp, cmap='gray')
# plt.show()