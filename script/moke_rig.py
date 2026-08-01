'''
Experiment rigs for MOKE measurements.
MOKE rig contains all hardward necessary for performing MOKE experiments. MOKE righ does NOT contain any analysis functionality.

'''
#%% import
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
# Galvo for scanning
pass
# import galvo_control as galvo
sys.path.insert(0, r'F:\Git\optical_devices_toolbox\scripts_zurich_instrument')
from zi_mfli import MFLI as lockin

#%% moke_rig class
class moke_rig:
    """
    Moke rig using balanced detector and lock-in amplifier.
    Hard requirements:
        lockin amplifier
        optical delay stage
    Optional requirements:
        half wave plates
        galvo mirror
    No-connection requirements:
        chopper
    """
    def __init__(self, lockin: lockin, delay_stage: ds_class, galvo = None, hwp: kcube_class = None):
        '''
        Initialization when making ths class.
        Do NOT put any hardware initialization here, only coding.
        '''
        # hard requirements
        self.lockin = lockin
        self.delay_stage = delay_stage
        # optional requirements
        self.galvo = galvo
        self.hwp = hwp

    def __post_init__(self):
        '''
        Post-initialization to check hardware connections and set initial states.
        '''
        # sanity check
        if self.lockin is None:
            raise ValueError("Lock-in amplifier must be provided")
        if self.delay_stage is None:
            raise ValueError("Delay stage must be provided")


    def initialize(self):
        ''' 
        Initialize all hardware devices and software states.
        '''
        # initialize lock-in amplifier
        pass
        # initialize delay stage
        pass
        # initialize all optional hardware
        if self.galvo is not None:
            pass
        if self.hwp is not None:
            pass
        # any remaining sanity check
        pass
        # any software initialization
        self.t0 = 0

    def close_hardwares(self):
        ''' Close all hardware devices. '''
        # close lock-in amplifier
        if self.lockin is not None:
            self.lockin.close()
        # close delay stage
        if self.delay_stage is not None:
            self.delay_stage.close()
        # close optional hardware
        if self.galvo is not None:
            self.galvo.close()
        if self.hwp is not None:
            self.hwp.close()

    #%% low level functions that need to be exposed here.
    def single_measurement(self, t_measure = 1):
        TIMING_RATIO = 2   # BUG: so far there is a timing mismatch. Measurement time is actually twice of the requested time in the measure method. Reason unknown.
        li = self.lockin
        r, phase, r_std, phase_std = li.measure_avg('polar', t_measure/TIMING_RATIO)
        return r, phase, r_std, phase_std
    #%% high-level functions
    def t_scan_no_t0_correction(self, t_raw:np.ndarray, t_measure:np.ndarray):
        '''
        Scan in time without T0 correction
        '''
        # get devices
        lockin = self.lockin
        ds = self.delay_stage

        # check dimension
        if t_raw.ndim != 1:
            raise ValueError("t must be 1D arrays")
        if t_measure.ndim != 1:
            raise ValueError("t_measure must be 1D arrays")
        # check size
        if t_raw.shape != t_measure.shape:
            raise ValueError("t and t_measure must have the same length")
        # check t_measure are positive
        if np.any(t_measure <= 0):
            raise ValueError("t_measure must be positive")
        # check all t_raw within ds range
        if np.any(t_raw < ds.tmin) or np.any(t_raw > ds.tmax):
            raise ValueError("t_raw must be within delay stage range")
        n = t_raw.shape[0]
        results = np.zeros((n, 4))

        for i in range(n):
            ds.goto_t(t_raw[i])     # go to time in delay stage
            result = self.single_measurement(t_measure[i])
            results[i,:] = result
        return results

    # def hwp_balance_by_scope(hwp: kcube_class, scope: lockin, tol_volt, tol_ang, step_ang, timeout):
    #     '''
    #     Automatic balance a balanced detector through Zurich MFLI lock-in amplifier and Thorlabs K-Cube rotation mount.
    #     Assumption:
    #         Initial angle is close. 
    #     '''
    #     pass

    # functions, lower level functions for measurements


    # def single_measurement_steady(galvo_device, bld_device, gx, gy, t_measure = 1):
    #     galvo_device.set_position(gx, gy)  # set galvo position
    #     result = bld_device.measure(t_measure)  # start balance detector measurement
    #     # NOTE: I may need to sleep here to wait for the measurement to finish. Not sure how detector is implemented.
    #     return result

    # def single_measurement_lockin(galvo_device, lockin_device, gx, gy, t_measure = 1):
    #     galvo_device.set_position(gx, gy)  # set galvo position
    #     result = lockin_device.measure(t_measure)  # start lock-in measurement
    #     # NOTE: I may need to sleep here to wait for the measurement to finish. Not sure how detector is implemented.
    #     return result

    # def sweep_y_measurement_steady(galvo_device, bld_device, gx, gy0, gy1, dgy, t_measure = 1):
    #     n_data = np.round((gy1 - gy0) / dgy) + 1
    #     results = np.zeros(n_data)
    #     for igy, gy in enumerate(range(gy0, gy1 + 1, dgy)):
    #         result = single_measurement_steady(galvo_device, bld_device, gx, gy, t_measure)
    #         results[igy] = result
    #     return results

    # def sweep_xy_measurement_steady(galvo_device, bld_device, gx0, gx1, dgx, gy0, gy1, dgy, t_measure = 1):
    #     n_data_x = np.round((gx1 - gx0) / dgx) + 1
    #     n_data_y = np.round((gy1 - gy0) / dgy) + 1
    #     results = np.zeros((n_data_y, n_data_x))
    #     for igy, gy in enumerate(range(gy0, gy1 + 1, dgy)):
    #         for igx, gx in enumerate(range(gx0, gx1 + 1, dgx)):
    #             result = single_measurement_steady(galvo_device, bld_device, gx, gy, t_measure)
    #             results[igy, igx] = result
    #     return results

    # def sweep_y_measurement_lockin(galvo_device, lockin_device, gx, gy0, gy1, dgy, t_measure = 1):
    #     n_data = np.round((gy1 - gy0) / dgy) + 1
    #     results = np.zeros(n_data)
    #     for igy, gy in enumerate(range(gy0, gy1 + 1, dgy)):
    #         result = single_measurement_lockin(galvo_device, lockin_device, gx, gy, t_measure)
    #         results[igy] = result
    #     return results

    # def sweep_xy_measurement_lockin(galvo_device, lockin_device, gx0, gx1, dgx, gy0, gy1, dgy, t_measure = 1):
    #     n_data_x = np.round((gx1 - gx0) / dgx) + 1
    #     n_data_y = np.round((gy1 - gy0) / dgy) + 1
    #     results = np.zeros((n_data_y, n_data_x))
    #     for igy, gy in enumerate(range(gy0, gy1 + 1, dgy)):
    #         for igx, gx in enumerate(range(gx0, gx1 + 1, dgx)):
    #             result = single_measurement_lockin(galvo_device, lockin_device, gx, gy, t_measure)
    #             results[igy, igx] = result
    #     return results
    #%% functions, higher level for GUI integration
    # def run_experiment(ds_device,    # object of delay stage class
    #                 galvo_device: galvo.GalvoDevice,  # object of galvo control class
    #                 lockin_device: lockin.LockInDevice,  # object of lock-in amplifier class
    #                 delay_array: np.ndarray,
    #                 gx0: float, gx1: float, dgx: float,
    #                 gy0: float, gy1: float, dgy: float,
    #                 t_measure_array: np.ndarray):
    #     # check size of delay_array and t_measure_array
    #     if len(delay_array) != len(t_measure_array):
    #         raise ValueError("delay_array and t_measure_array must have the same length")
    #     # initialize 
    #     n_frame = len(delay_array)
    #     n_x = int(np.round((gx1 - gx0) / dgx)) + 1
    #     n_y = int(np.round((gy1 - gy0) / dgy)) + 1
    #     results = np.zeros((n_frame, n_y, n_x))
    #     print("Start MOKE experiment:")
    #     for i, delay in enumerate(delay_array):
    #         # print notice
    #         print(f"#{i} out of {n_frame} frame: delay {delay:.2f} ps for {t_measure_array[i]:.2f} s at each point. "
    #             f"\nEstimated total time: {n_x * n_y * t_measure_array[i]:.2f} s")
    #         # move delay stage
    #         ds_device.move_t(delay)
    #         results[i, :, :] = sweep_xy_measurement_lockin(galvo_device, lockin_device, gx0, gx1, dgx, gy0, gy1, dgy, t_measure_array[i])
    #     return results

def run_experiment_t(rig, t_raw, t_measure):
    results = rig.t_scan_no_t0_correction(t_raw, t_measure)
    return results

#%% camera-based MOKE
# TBD

class moke_camera_rig:
    '''
    Moke rig using lock-in camera instead of lock-in amplifier to achieve wide-field imaging
    Hard requirements:
        lockin camera (represented by LiCam class)
        optical delay stage (represented by TL_ds class)
    Optional requirements:
        half wave plates use a k-cube controller.
    No-connection requirements:
        chopper
        
    '''
    def __init__(self, delay_stage, li_camera=None, hwp=None):
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
        ''' Close all hardware devices. '''
        # close lock-in camera
        self.licam.close()
        # close delay stage
        self.ds.close()
        # close optional hardware
        if self.hwp is not None:
            self.hwp.close()

    # ----- parameterize -----
    def set_camera_steady_state(self):
        ''' Set the lock-in camera to steady state mode. '''
        self.licam.set_measurement_mode("steady")

    def set_camera_lockin_mode(self):
        pass    # TBD

    def set_camera_parameter(self, **kwargs):
        # NOTE: double check syntax
        self.licam.set_attributes(**kwargs)

    # NOTE: prefer to directly use the lock-in camera's own methods to set parameters, instead of wrapping them here. This is to avoid confusion and redundancy.

    # ----- measurement -----
    def camera_acquire(self):
        return self.licam.acquire()

    def camera_stream_frame(self, timeout=300, interval=0.05, autoscale=True):
        ''' Preview the lock-in camera image. Usually used in alignment.
        Time out in seconds. Default is 300 seconds. '''
        fig, ax = plt.subplots()
        ax.clear()

        frame = self.camera_acquire()          # <- your acquisition call
        im = ax.imshow(frame, cmap='gray', interpolation='nearest')
        plt.figure.colorbar(im, ax=ax)
        title = ax.set_title('t = 0.0 s')

        plt.ion()
        plt.figure.show()

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
                            f'max {frame.max():g}')

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
        raw = self.licam.acquire()
        img = self.licam.to_numpy(raw)
        return img

    def measure_frame_at_time(self, t_delay, t_acquire):
        """
        Move delay stage to t_delay, acquire a frame with t_acquire
        """
        self.ds.goto_t(t_delay)
        img = self.camera_acquire_frame(t_acquire)
        return img

    def measure_delta(self, n_pair, t_acquire, method, method_dict):
        """
        Measure delta signal with n_pair of frames, each frame with t_acquire.
        The "method" argument defines how to determine pump / un-pump frames. The "method" argument is supported by a "method_dict" dictionary.
            "even_odd": even frames are pump, odd frames are un-pump, or vice versa. Requires a "pump_first" boolean in method_dict to indicate whether the first frame is pump or un-pump. 
            "reference_roi": use a reference region on camera to determine pump / un-pump frames. Requires 4 keys in method_dict: "x_center", "y_center", "width", "height" to define the reference ROI. 
                Frames with stronger signal in the reference ROI are considered pump frames, and weaker signal are considered un-pump frames.
        """
        assert method in ["even_odd", "reference_roi"], "method must be either 'even_odd' or 'reference_roi'"
        pass

    def measure_delta_at_time(self, t_delay, n_pair, t_acquire, method, method_dict):
        """
        Move delay stage to t_delay, measure delta signal with n_pair of frames, each frame with t_acquire.
        See measure_delta() for details on method and method_dict.
        """
        self.ds.goto_t(t_delay)
        delta = self.measure_delta(n_pair, t_acquire, method, method_dict)
        return delta

    def scan_delta(self, t_delay_array, n_pair_array, t_acquire, method, method_dict):
        """
        Scan delay stage to t_delay_array, measure delta signal with n_pair of frames at each delay, each frame with t_acquire.
        See measure_delta() for details on method and method_dict.
        """
        t_delay_array = np.asarray(t_delay_array)
        n_pair_array = np.asarray(n_pair_array)
        assert t_delay_array.size == n_pair_array.size, "t_delay_array and n_pair_array must have the same size"
        deltas = []
        for t_delay, n_pair in zip(t_delay_array, n_pair_array):
            delta = self.measure_delta_at_time(t_delay, n_pair, t_acquire, method, method_dict)
            deltas.append(delta)
        return np.array(deltas)
# %%
