'''
Code for conducting scanning tr-MOKE measurement.
Focused probe light controlled by a galvo mirror, scanning the sample surface.
Delay stage controlled by a Thorlabs BBD301 brushless motor, and DDS300 delay stage.
HWP controlled by a Thorlabs K-cube.
Reflected signal analyzed by a Zurich Instruments MFLI lock-in amplifier, referenced by chopper in the Aux input1.

Magnetic field and temperature is not controlled by this code.

Made by Hanjun, Purdue University, 2025.
'''
#%% import
# NOTE: [t,y,x] indexing for the results array

import numpy as np
import time
import sys
import moke_rig 

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

#%% functions, lower level for device control

# I will move this to the working scirpt instead of in a library.
#%% Other misc functions
def press_enter_to_proceed():
    input("Press Enter to proceed...")

def __main__():
    #%% read parameters
    #%% make devices
    BBD_serial_number = '103507474' # NOTE: replace with actual motor serial number
    ds = ds_class(BBD_serial_number, NTRIP=4)     # NOTE: need 2 arguments: serial number and NTRIP

    kcube_hwp_SN = '27600911'
    hwp = kcube_class(kcube_hwp_SN)     # create hwp object

    li_SN = 'DEV5849'
    li_HOST = '10.164.14.211'
    li = lockin(li_SN, li_HOST)  # create lock-in amplifier object

    galvo_device = None     # NOTE: add galvo later
    rig = moke_rig.moke_rig(li, ds, galvo = galvo_device, hwp = hwp)   # create rig object. 
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
    gx0, gx1, dgx = 0, 10, 1
    gy0, gy1, dgy = 0, 10, 1
    t_measure_array = np.ones(len(delay_array))  # example measurement time array

    # run the experiment
    results = run_experiment(ds, delay_array, gx0, gx1, dgx, gy0, gy1, dgy, t_measure_array)
    
    # save results
    #%% close
    ds.close()  # close the delay stage device