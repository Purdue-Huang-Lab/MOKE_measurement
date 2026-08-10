import numpy as np
import matplotlib
matplotlib.use('TkAgg')
from matplotlib import pyplot as plt

frame = np.load(r"C:\Users\Huang Lab\Documents\GitHub\MOKE_measurement\moke\devices\helicam_test_data\helicam_test_016\in_run_frame.npy")
dark = np.mean(frame[:7, :, :, 1], axis=0)
signal = np.mean(frame[7:, :, :, 1], axis=0)
valid = signal - dark

fig, ax = plt.subplots(1, 3, figsize=(12, 4))
ax[0].imshow(dark, cmap='gray')
ax[1].imshow(signal, cmap='gray')
ax[2].imshow(valid, cmap='gray')

fig.colorbar(ax[2].images[0], ax=ax[2])
plt.show()