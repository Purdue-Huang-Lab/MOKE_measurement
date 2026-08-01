'''
Code for conducting scanning tr-MOKE measurement.
Dispersed, wide-field, monochromatic probe beam. Focused pump beam.
Delay stage controlled by a Thorlabs BBD301 brushless motor, and DDS300 delay stage.
Reflected probe beam is modulated by a PEM, then pass through a polarizer and measured by a helicam lock-in camera.
Magnetic field and temperature is not controlled by this code.

As a prototype, this code only contains minimal GUI currently.

Made by Hanjun, Purdue University, 2026.
'''
# ----- import -----------------------------------------
# NOTE: [t,y,x] indexing for the results array

import numpy as np
import sys
import moke_rig
import helicam_c3 as hcam
from hytools import hy_basic as hyb     # NOTE: remove hytools dependency in the future.

# add device control packages
# TODO: ideally we don't need to expose any hardware interface except for moke_rig class.
# delay stage
sys.path.insert(0, r'F:\Git\optical_devices_toolbox\scripts_thorlabs')  # TODO: in a stable version, these codes will be integrated.
from t_bbd_ds import TL_ds as ds_class    # class for Thorlabs delay stage control
# K-cube for hwp
pass

# ----- Other misc functions --------------------------
def press_enter_to_proceed():
    input("Press Enter to proceed...")

def __main__():
    # ----- Parameters -------------------------------
    save_dir = r'F:\Git\MOKE_measurement\results'
    hyb.check_make_dir(save_dir)  # make sure the save directory exists
    # ----- Parameter end ---------------------------
    # ----- Make devices --------------------------------
    BBD_serial_number = '103507474' # NOTE: replace with actual motor serial number
    ds = ds_class(BBD_serial_number, NTRIP=4)     # NOTE: need 2 arguments: serial number and NTRIP

    rig = moke_rig.moke_rig_camera(li, ds, galvo = galvo_device, hwp = hwp)   # create rig object. 
    # pre-run checks. These are tasks that need to be manually done.
    print(  '''
            Pre-run checks:
            Before running experiments, please check the following issues:
            1. Is delay stage homed?
            2. Is lock-in amplifier configured? 
            3. Is hwp balanced?
            4. (If running spatial-MOKE) Is galvo device initialized?
            ''')
    press_enter_to_proceed()
    # define parameters
    delay_array = np.linspace(0, 10, 100)  # example delay array
    t_measure_array = np.ones(len(delay_array))  # example measurement time array

    # run the experiment
    results = moke_rig.run_experiment_t(rig, delay_array, t_measure_array)

    #%% save results
    result_fname = f'{save_dir}\\lock_in_test.txt'
    combined = np.zeros((results.shape[0], results.shape[1] + 1))
    combined[:, 1:] = results           # Place the data matrix
    combined[:, 0] = delay_array        # Place delay_array as the first row (excluding first cell)
    np.savetxt(result_fname, combined, fmt="%.6g", delimiter="\t", header=['delay', 'r', 'phase', 'r_std', 'phase_std'])
    #%% close
    ds.close()  # close the delay stage device