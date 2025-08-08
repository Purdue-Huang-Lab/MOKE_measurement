# this is a pseudo code for a MOKE experiment control script
# NOTE: I will use [t,y,x] indexing for the results array
import numpy as np
import time
import sys

# add device control packages
# delay stage
sys.path.insert(0, r'F:\Git\optical_devices_toolbox\scripts_thorlabs')
from t_bbd_ds import TL_ds as ds_class    # class for Thorlabs delay stage control
# K-cube for hwp
from t_kcube import TL_kcube as kcube_class   # class for Thorlabs K-cube control, needed to auto-balance the balanced detector
# Galvo for scanning
# TODO: do this after installing galvo
# import galvo_control as galvo
sys.path.insert(0, r'F:\Git\optical_devices_toolbox\scripts_zurich_instrument')
from zi_mfli import MFLI as lockin

# functions, lower level for device control

# I will move this to the working scirpt instead of in a library.
def hwp_balance_by_scope(hwp: kcube_class, scope: lockin, tol_volt, tol_ang, step_ang, timeout):
    '''
    Automatic balance a balanced detector through Zurich MFLI lock-in amplifier and Thorlabs K-Cube rotation mount.
    Assumption:
        Initial angle is close. 
    '''

# functions, lower level functions for measurements

def single_measurement(lockin_device, t_measure = 1):
    print("Not implemented yet.")
    return 

def single_measurement_steady(galvo_device, bld_device, gx, gy, t_measure = 1):
    galvo_device.set_position(gx, gy)  # set galvo position
    result = bld_device.measure(t_measure)  # start balance detector measurement
    # NOTE: I may need to sleep here to wait for the measurement to finish. Not sure how detector is implemented.
    return result

def single_measurement_lockin(galvo_device, lockin_device, gx, gy, t_measure = 1):
    galvo_device.set_position(gx, gy)  # set galvo position
    result = lockin_device.measure(t_measure)  # start lock-in measurement
    # NOTE: I may need to sleep here to wait for the measurement to finish. Not sure how detector is implemented.
    return result

def sweep_y_measurement_steady(galvo_device, bld_device, gx, gy0, gy1, dgy, t_measure = 1):
    n_data = np.round((gy1 - gy0) / dgy) + 1
    results = np.zeros(n_data)
    for igy, gy in enumerate(range(gy0, gy1 + 1, dgy)):
        result = single_measurement_steady(galvo_device, bld_device, gx, gy, t_measure)
        results[igy] = result
    return results

def sweep_xy_measurement_steady(galvo_device, bld_device, gx0, gx1, dgx, gy0, gy1, dgy, t_measure = 1):
    n_data_x = np.round((gx1 - gx0) / dgx) + 1
    n_data_y = np.round((gy1 - gy0) / dgy) + 1
    results = np.zeros((n_data_y, n_data_x))
    for igy, gy in enumerate(range(gy0, gy1 + 1, dgy)):
        for igx, gx in enumerate(range(gx0, gx1 + 1, dgx)):
            result = single_measurement_steady(galvo_device, bld_device, gx, gy, t_measure)
            results[igy, igx] = result
    return results

def sweep_y_measurement_lockin(galvo_device, lockin_device, gx, gy0, gy1, dgy, t_measure = 1):
    n_data = np.round((gy1 - gy0) / dgy) + 1
    results = np.zeros(n_data)
    for igy, gy in enumerate(range(gy0, gy1 + 1, dgy)):
        result = single_measurement_lockin(galvo_device, lockin_device, gx, gy, t_measure)
        results[igy] = result
    return results

def sweep_xy_measurement_lockin(galvo_device, lockin_device, gx0, gx1, dgx, gy0, gy1, dgy, t_measure = 1):
    n_data_x = np.round((gx1 - gx0) / dgx) + 1
    n_data_y = np.round((gy1 - gy0) / dgy) + 1
    results = np.zeros((n_data_y, n_data_x))
    for igy, gy in enumerate(range(gy0, gy1 + 1, dgy)):
        for igx, gx in enumerate(range(gx0, gx1 + 1, dgx)):
            result = single_measurement_lockin(galvo_device, lockin_device, gx, gy, t_measure)
            results[igy, igx] = result
    return results
#%% functions, higher level for GUI integration
def run_experiment(ds_device,    # object of delay stage class
                   galvo_device: galvo.GalvoDevice,  # object of galvo control class
                   lockin_device: lockin.LockInDevice,  # object of lock-in amplifier class
                   delay_array: np.ndarray,
                gx0: float, gx1: float, dgx: float,
                gy0: float, gy1: float, dgy: float,
                t_measure_array: np.ndarray):
    # check size of delay_array and t_measure_array
    if len(delay_array) != len(t_measure_array):
        raise ValueError("delay_array and t_measure_array must have the same length")
    # initialize 
    n_frame = len(delay_array)
    n_x = int(np.round((gx1 - gx0) / dgx)) + 1
    n_y = int(np.round((gy1 - gy0) / dgy)) + 1
    results = np.zeros((n_frame, n_y, n_x))
    print("Start MOKE experiment:")
    for i, delay in enumerate(delay_array):
        # print notice
        print(f"#{i} out of {n_frame} frame: delay {delay:.2f} ps for {t_measure_array[i]:.2f} s at each point. "
              f"\nEstimated total time: {n_x * n_y * t_measure_array[i]:.2f} s")
        # move delay stage
        ds_device.move_t(delay)
        results[i, :, :] = sweep_xy_measurement_lockin(galvo_device, lockin_device, gx0, gx1, dgx, gy0, gy1, dgy, t_measure_array[i])
    return results

def __main__():
    #%% read parameters
    #%% make devices
    BBD_serial_number = '123456' # NOTE: replace with actual motor serial number
    ds = ds_class(BBD_serial_number, NTRIP=4)     # NOTE: need 2 arguments: serial number and NTRIP


    # define parameters
    delay_array = np.linspace(0, 10, 100)  # example delay array
    gx0, gx1, dgx = 0, 10, 1
    gy0, gy1, dgy = 0, 10, 1
    t_measure_array = np.ones(len(delay_array))  # example measurement time array

    # run the experiment
    results = run_experiment(ds, delay_array, gx0, gx1, dgx, gy0, gy1, dgy, t_measure_array)
    
    # process results
    other_packages.process_results(results)
    #%% close
    ds.close()  # close the delay stage device