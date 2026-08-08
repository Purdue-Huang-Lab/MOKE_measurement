'''
This file is a library for controlling Thorlabs DDS300 delay stage from BBD301
brushless motor controller. Copied from optical_devices_toolbox, 260806
Make by Hanjun, Purdue University, 2025.
'''
# so far this script only works on DDS300 delay stage. Should be an easy fix if there is need.

import os
import sys
import time
from ctypes import *

SN = '103507474' # default serie number for debug purpose
C = 299792458   # speed of light
NTRIP = 4     # trip number of delay stage.
CONVERSION = 300 / 6000000  # NOTE: Specific for DDS300 delay stage. 300 mm travel, 6,000,000 steps, so each step is 0.05 mm. This magic number should be changed for different delay stage.
VSTAGE = 100  # default speed in mm/s, used for move command. 

# add dll
# replace with actual Thorlabs Kinesis installation path. Usually it is "C:\Program Files\Thorlabs\Kinesis"
if sys.version_info < (3, 8):
    os.chdir(r"C:\Program Files\Thorlabs\Kinesis")
else:
    os.add_dll_directory(r"C:\Program Files\Thorlabs\Kinesis")

lib: CDLL = cdll.LoadLibrary("Thorlabs.MotionControl.Benchtop.BrushlessMotor.dll")

class TL_ds:
    def __init__(self, SN:str = SN, NTRIP = NTRIP):
        # some constants
        self.SN = c_char_p(SN.encode())
        self.NTRIP = NTRIP
        self.CONVERSION = CONVERSION 
        self.VSTAGE = VSTAGE  # default speed in mm/s
        try:
            lib.TLI_BuildDeviceList()   # must build device list before connect
            # the following is commented because sometimes it mess with BMC_open
            # n_device = lib.TLI_GetDeviceListSize()
            # if n_device < 1:
            #     raise RuntimeError("Device not find.")
            if lib.BMC_Open(self.SN) != 0:  # start communication. Check if the device is opened successfully
                raise RuntimeError("Failed to open device.")
            if lib.BMC_IsChannelValid(self.SN, 1) != 1:  # I will assume DS is installed on channel 1. Return 1 if is valid, start from 1
                raise RuntimeError("Invalid channel.")
            lib.BMC_EnableChannel(self.SN, 1)
            time.sleep(1)
            lib.BMC_StartPolling(self.SN, c_int(100))    # start polling every 100 ms
            # get device limits
            temp_min = c_double()
            temp_max = c_double()
            lib.BMC_GetMotorTravelLimits(self.SN, 1, byref(temp_min), byref(temp_max))  # unti is step; each mm has 2e4 step, total 300 mm, so total 6,000,000 unit
            self.min, self.max = self.convert_dev_to_real(temp_min.value), self.convert_dev_to_real(temp_max.value)
            self.tmin, self.tmax = self.d_to_t(self.min), self.d_to_t(self.max)  # convert to time unit
            self.pos = self.get_position()    # initialize position
            # check if homing is needed
            if lib.BMC_CanMoveWithoutHomingFirst(self.SN, 1) == 0:
                print("Home needed")
            print('Delay stage initialization complete.')
        except Exception as e:
            print(e)
    
    def close(self):
        try:
            lib.BMC_Close(self.SN)
        except Exception as e:
            print(e)

    def convert_dev_to_real(self, dev_value):
        return float(dev_value * self.CONVERSION)  # convert device unit to real unit (mm)

    def convert_real_to_dev(self, real_value):
        return int(real_value / self.CONVERSION)

    def get_position(self):
        try:
            lib.BMC_RequestPosition(self.SN)   # request position
            time.sleep(0.1)
            dev_pos = lib.BMC_GetPosition(self.SN, 1)    # get position in Device Unit. I think there is something wrong with the document. Need to check.
            self.pos = self.convert_dev_to_real(dev_pos)
            return self.pos
        
        except Exception as e:
            print(e)

    def home(self):
        try:
            if(lib.BMC_Home(self.SN, 1))!=0:
                print('Delay stage home error!')    # home
                return None
            # sleep untile get to 0
            # TIMEOUT = 30 # max timeout in seconds. if delay stage does not home in this time, raise error.
            # start_time = time.time()
            # old_pos = self.pos
            # time.sleep(3)   # there is some delay before BMC_Home() actually start
            # while True:  # wait until pos doesn't change anymore. Tolerance is 0.01 mm. Check every 0.2 s.
            #     time.sleep(0.2)
            #     new_time = time.time()   
            #     t = new_time - start_time
            #     new_pos = self.get_position()   # BUG: get_position is blocked when homing
            #     print(f'Time = {t:.2f}, Old position: {old_pos}, new position: {new_pos}') # dubug only    
            #     if abs(new_pos - old_pos) <= 0.01:
            #         break
            #     old_pos = new_pos
            #     if new_time - start_time > TIMEOUT:
            #         print("Thorlab DS homing timeout.")
            #         return 1
            print("Homing started. Must manually get_position after complete!")
        
        except Exception as e:
            print(e)

    def d_to_t(self, d: float):
        '''
        Convert distance to time.
        d: distance in mm
        return: time in ps
        '''
        t = NTRIP * d / C * 1e9  # convert to ps
        return t

    def t_to_d(self, t: float):
        '''
        Convert time to distance.
        t: time in ps
        return: distance in mm
        '''
        d = t * C / NTRIP * 1e-9  # convert to mm
        return d
    
    def goto_d(self, d: float):     # Note: this is the root move function. All other move functions will call this one.
        '''
        Move to absolute position in distance.
        d: distance in mm
        return: None
        '''
        if d < self.min or d > self.max:
            print(f"Distance {d} is out of range ({self.min}, {self.max}). Operation aborted.")
            return
        t_estimated = abs(self.pos - d) / self.VSTAGE + 0.2  # estimated moving time in s
        # print('estimate time = ',t_estimated)  # debug only
        new_pos_dev = c_int(self.convert_real_to_dev(d))  # convert to device unit
        try:
            lib.BMC_SetMoveAbsolutePosition(self.SN, 1, new_pos_dev)    # this step only set target, doesnt actaully move
            time.sleep(0.1)   # wait for communication.
            lib.BMC_MoveAbsolute(self.SN, 1)
            time.sleep(t_estimated)   # wait for move to complete. 
            self.get_position()  # update position
            if abs(self.pos - d) > 0.01:    # check if the move was successful. Let's say acceptable error is 0.1 ps, it convert to ~0.008 mm. Typical accuracy is ~20 dev unit, or 0.001 mm
                print(f'Failed to move to {d} mm. Current position: {self.pos} mm.')
        except Exception as e:
            print(e)
    
    def goto_t(self, t: float):
        '''
        Move to absolute position in time.
        t: time in ps
        return: None
        '''
        d = self.t_to_d(t)
        self.goto_d(d)
    
    def move_rel_d(self, d: float):
        '''
        Move relative to current position in distance.
        d: distance in mm
        return: None
        '''
        new_pos = self.get_position() + d
        self.goto_d(new_pos)
    
    def move_rel_t(self, t: float):
        '''
        Move relative to current position in time.
        t: time in ps
        return: None
        '''
        d = self.t_to_d(t)
        self.move_rel_d(d)
        
# if __name__ == '__main__':
#     ds = TL_ds(SN, NTRIP)
#     ds.home()
#     ds.close()