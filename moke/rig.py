'''
Experiment rigs for MOKE measurements.
MOKE rig contains all hardward necessary for performing MOKE experiments. MOKE righ does NOT contain any analysis functionality.

'''
# NOTE: split from script/moke_rig.py — this file keeps only the wide-field camera rig
# (moke_camera_rig). The old point-scan (MFLI lock-in) rig moved to archive/moke_rig.py.
#%% import
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import time

# add device control packages
# delay stage
sys.path.insert(0, r'F:\Git\optical_devices_toolbox\scripts_thorlabs')
from t_bbd_ds import TL_ds as ds_class    # class for Thorlabs delay stage control
# K-cube for hwp
from t_kcube import TL_kcube as kcube_class   # class for Thorlabs K-cube control, needed to auto-balance the balanced detector
# helicam
from moke.devices import helicam as hcam

#%% camera-based MOKE

class moke_camera_rig:
    '''
    Moke rig using lock-in camera instead of lock-in amplifier to achieve wide-field imaging
    Hard requirements:
        lockin camera (designed with helicam_c3 class in mind)
        optical delay stage (represented by TL_ds class)
    Optional requirements:
        half wave plates use a k-cube controller.
    No-connection requirements:
        chopper

    '''
    def __init__(self, delay_stage:TL_ds, li_camera:hcam.HeliCamC3, hwp=None):
        self.licam = li_camera
        self._licamtype = li_camera.type
        self.ds = delay_stage
        self._dsType = delay_stage.type
        self.hwp = hwp

    def __post_init__(self):
        if self.ds is None:
            raise ValueError('Delay stage must be specified')
        if self.licam is None:
            raise ValueError('Lock-in camera must be specified')

    # ----- life cycle -----
    def initialize(self):
        '''
        Initialize all hardware devices and software states.
        '''
        # initialize lock-in camera
        self.licam.initialize()
        self.HEIGHT, self.WIDTH = self.licam.get_image_shape()
        # initialize delay stage
        self.ds.initialize()
        # initialize all optional hardware
        if self.hwp is not None:
            self.hwp.initialize()
        # any remaining sanity check
        pass
        # any software initialization
        self.t0 = 0
        print("MOKE camera rig initialized.")

    def close(self):
        #NOTE: can i get it to run whenever this object is deleted?
        ''' Close all hardware devices. '''
        # close lock-in camera
        self.licam.close()
        # close delay stage
        self.ds.close()
        # close optional hardware
        if self.hwp is not None:
            self.hwp.close()

    def __del__(self):
        self.close()

    # ----- parameterize -----
    def set_camera_steady_state(self):
        ''' Set the lock-in camera to steady state mode. '''
        self.licam.set_measurement_mode("steady")

    def set_camera_lockin_mode(self):
        self.licam.set_measurement_mode("minimum_energy")

    def set_camera_parameter(self, **kwargs):
        # NOTE: double check syntax
        # NOTE: prefer to directly use the lock-in camera's own methods to set parameters, instead of wrapping them here. This is to avoid confusion and redundancy.
        self.licam.set_attributes(**kwargs)

    # ----- measurement -----
    def camera_acquire(self):
        return self.licam.acquire()

    def camera_stream_frame(self, fig, ax, timeout=300, interval=0.05, autoscale=True):
        ''' Preview the lock-in camera image. Usually used in alignment.
        Time out in seconds. Default is 300 seconds. '''

        frame = self.camera_acquire()          # <- your acquisition call
        im = ax.imshow(frame, cmap='gray', interpolation='nearest')
        plt.figure.colorbar(im, ax=ax)
        title = ax.set_title('t = 0.0 s')

        t0 = next_t = time.monotonic()
        n = 0
        try:
            while True:
                elapsed = time.monotonic() - t0
                if elapsed >= timeout:
                    break
                if not plt.fignum_exists(plt.figure.number):   # user closed the window
                    break

                frame = self.camera_acquire()
                im.set_data(frame)
                if autoscale:
                    im.set_clim(frame.min(), frame.max())
                title.set_text(f't = {elapsed:5.1f} s | frame {n} | '
                            f'max {frame.max():g}\nPress any key to exit.')

                fig.canvas.draw_idle()
                fig.canvas.flush_events()
                n += 1

                next_t += interval
                time.sleep(max(0.0, next_t - time.monotonic()))
        except KeyboardInterrupt:
            pass
        finally:
            plt.ioff()

        return n

    def camera_acquire_frame(self, t_acquire = 1.0):
        """
        Measure a single frame with current setting
        """
        self.licam.set_acquire_time(t_acquire)
        raw = self.licam.acquire_single()
        img = self.licam.to_numpy(raw)
        return img

    def measure_frame_at_time(self, t_delay, t_acquire):
        """
        Move delay stage to t_delay, acquire a frame with t_acquire
        """
        self.ds.goto_t(t_delay)
        img = self.camera_acquire_frame(t_acquire)
        return img

    def continuous_measure_frame_at_time(self, t_delay, t_acquire, n_frames):
        """
        Move delay stage to t_delay, acquire n_frames with t_acquire
        """
        self.ds.goto_t(t_delay)
        imgs = np.zeros((n_frames, self.HEIGHT, self.WIDTH))
        for i in range(n_frames):
            imgs[i] = self.stream(t_acquire)
        return imgs

    def measure_delta(self, n_measure, t_acquire, method, method_dict):
        """
        Measure delta signal with n_measure of frames, each frame with t_acquire.
        The "method" argument defines how to determine pump / un-pump frames. The "method" argument is supported by a "method_dict" dictionary.
            "even_odd": even frames are pump, odd frames are un-pump, or vice versa. Requires a "pump_first" boolean in method_dict to indicate whether the first frame is pump or un-pump.
            "reference_roi": use a reference region on camera to determine pump / un-pump frames. Requires 4 keys in method_dict: "x_center", "y_center", "width", "height" to define the reference ROI.
                Frames with stronger signal in the reference ROI are considered pump frames, and weaker signal are considered un-pump frames.
        """
        assert method in ["even_odd", "reference_roi"], "method must be either 'even_odd' or 'reference_roi'"
        mats_even = np.zeros((n_measure, self.HEIGHT, self.WIDTH))
        mat_odd = np.zeros_like(mats_even)
        for i in range(n_measure):
            pass

    def measure_delta_at_time(self, t_delay, n_measure, t_acquire, method, method_dict, save_path = None):
        """
        Move delay stage to t_delay, measure delta signal with n_measure of frames, each frame with t_acquire.
        See measure_delta() for details on method and method_dict.
        """
        self.ds.goto_t(t_delay)
        delta = self.measure_delta(n_measure, t_acquire, method, method_dict)
        return delta

    def measure_delta_at_time_avg(self, reps, t_delay, n_measure, t_acquire, method, method_dict, save_path = None):
        """
        Measure delta signal with n_measure of frames, each frame with t_acquire, at t_delay, and repeat for reps times. Average the results.
        """
        assert reps >= 1, "reps must be positive"
        reps = int(reps)
        size = self.licam.get_image_shape()
        deltas = np.zeros((reps, size[0], size[1]))   # [rep, y, x] indexing
        for i in range(reps):
            delta = self.measure_delta_at_time(t_delay, n_measure, t_acquire, method, method_dict)
            deltas[i] = delta
        delta_avg = np.mean(deltas, axis=0)
        stds = np.std(deltas, axis=0)
        return delta_avg, stds

    def scan_delta(self, t_delay_array, n_measure_array, t_acquire, method, method_dict):
        """
        Scan delay stage to t_delay_array, measure delta signal with n_measure of frames at each delay, each frame with t_acquire.
        See measure_delta() for details on method and method_dict.
        """
        t_delay_array = np.asarray(t_delay_array)
        n_measure_array = np.asarray(n_measure_array)
        assert t_delay_array.size == n_measure_array.size, "t_delay_array and n_measure_array must have the same size"
        size = self.licam.get_image_shape()
        deltas = np.zeros((t_delay_array.size, size[0], size[1]))   # [t, y, x] indexing
        for i, (t_delay, n_measure) in enumerate(zip(t_delay_array, n_measure_array)):
            delta = self.measure_delta_at_time(t_delay, n_measure, t_acquire, method, method_dict)
            deltas[i] = delta
        return deltas

    # ----- IO -----
    def save_frame_txt(self, mat2d, filename):
        """
        Save a single frame to file
        """
        assert mat2d.ndim == 2, "mat2d must be 2D array"
        assert os.path.exists(os.path.dirname(filename)), "directory does not exist"

        np.savetxt(filename, mat2d, delimiter=',', fmt='%4g')   # output in 4 sigfig

    def save_frame_np(self, mat2d, filename):
        """
        Save a single frame to file as a compressed npy file using np.save.
        """
        assert mat2d.ndim == 2, "mat2d must be 2D array"
        assert os.path.splitext(filename)[1] == ".npy", "filename must have .npy extension"
        assert os.path.exists(os.path.dirname(filename)), "directory does not exist"

        np.save(filename, mat2d=mat2d)

    def save_all_txt(self, mat3d, filename):
        """
        Save a 3D array to file as a continuous 2D matrix.
        """
        assert mat3d.ndim == 3, "mat3d must be 3D array"
        assert os.path.exists(os.path.dirname(filename)), "directory does not exist"

        np.savetxt(filename, mat3d.reshape(mat3d.shape[0], -1), delimiter=',', fmt='%4g')   # output in 4 sigfig

    def save_all_np(self, mat3d, filename):
        """
        Save a 3D array to file as a compressed npy file using np.save.
        """
        assert mat3d.ndim == 3, "mat3d must be 3D array"
        assert os.path.splitext(filename)[1] == ".npy", "filename must have .npy extension"
        assert os.path.exists(os.path.dirname(filename)), "directory does not exist"

        np.save(filename, mat3d=mat3d)
# %%
