"""Azimuth HWP device wrapper (Thorlabs K-cube, via optical_devices_toolbox).
Direct copy-pasted from optical_devices_toolbox, 260805"""
"""This is a package to handle Thorlabs KDC101 DC servo motor driver. 
Written with PRM1-Z8 rotation mount in mind, but can be used for other devices under minor adjustment.
Made by Hanjun, Purdue University, 2025."""

import os
import sys
import time
from ctypes import *

SN = '27600911' # default serie number for debug purpose.
DCONVERT = 1919.64186     # steps per revolution for the PRM1-Z8 rotation mount, Check the communication protocol for other devices.
VCONVERT = 42941.66       # conversion factor for velocity, unit is steps/s. Check the communication protocol for other devices. 
ACONVERT = 14.66          # conversion factor for acceleration, unit is steps/s^2. Check the communication protocol for other devices.
V0 = 10
A0 = 10     # default velocity and acceration

# add dll
# replace with actual Thorlabs Kinesis installation path. Usually it is "C:\Program Files\Thorlabs\Kinesis"
if sys.version_info < (3, 8):
    os.chdir(r"C:\Program Files\Thorlabs\Kinesis")
else:
    os.add_dll_directory(r"C:\Program Files\Thorlabs\Kinesis")
lib: CDLL = cdll.LoadLibrary("Thorlabs.MotionControl.KCube.DCServo.dll")

class TL_kcube:
    def __init__(self, SN:str = SN):
        self.SN = c_char_p(SN.encode())
        self.comment = ''   # used to store misc information
        self.v = V0
        self.a = A0
        # open device
        try:
            # check device size
            lib.TLI_BuildDeviceList()   # rebuild device list. Without doing this will get 0 size
            time.sleep(0.1) # wait for device list to be built
                
            if lib.CC_Open(self.SN) != 0:
                raise RuntimeError("Opening kcube failed!")
            lib.CC_StartPolling(self.SN, c_int(200))  # poll every 0.2 s. Unit of the 2nd argument is ms.

            steps_per_rev = c_double(DCONVERT)  # for the PRM1-Z8
            gbox_ratio = c_double(1.0)  # gearbox ratio
            pitch = c_double(1.0)

            # Apply these values to the device
            lib.CC_SetMotorParamsExt(self.SN, steps_per_rev, gbox_ratio, pitch)

            # set some device parameters
            # lib.CC_SetRotationModes(self.SN, 2, 0) # set to rotational unbounded, fastest path.
            # read the device's *actual* velocity/acceleration back instead of assuming
            # V0/A0. set_velocity() (CC_SetVelParams) is bugged and never actually writes
            # a velocity to the hardware, so self.v must come from the device or every
            # move_smart() wait-time estimate is timed against a number that was never set.
            accel_dev = c_int()
            vel_dev = c_int()
            if lib.CC_GetVelParams(self.SN, byref(accel_dev), byref(vel_dev)) == 0:
                self.v = vel_dev.value / VCONVERT
                self.a = accel_dev.value / ACONVERT
            else:
                print(f"Warning: could not read velocity from device; assuming default v={V0} deg/s, a={A0} deg/s^2.")
            # check if homing is needed. Do NOT home automatically here: re-homing can move
            # the mount off a previously-set angle, so homing only ever happens via an
            # explicit call to home().
            if lib.CC_CanMoveWithoutHomingFirst(self.SN) == 0:
                print("KCube: Homing needed. Call home() explicitly if required -- not done automatically.")
            self.pos = self.get_position()
            print('Thorlabs K-Cube successfully initialized.')

        except Exception as e:
            print(f"Error initializing Thorlabs K-Cube: {e}")
            raise

    def close(self):
        try:
            lib.CC_StopPolling(self.SN)
            lib.CC_Close(self.SN)
            print('Thorlabs K-Cube closed.')
        except Exception as e:
            print(f"Error closing Thorlabs K-Cube: {e}")

    # TODO: doesn't work for some reason
    # def set_velocity(self, v: float = 10, a: float = 10):   # has bug. Do not use
    #     """
    #     Set velocity and acceleration. v in deg/s, a in deg/s^2.
    #     Default v and a are 10 deg/s and 10 deg/s^2.
    #     """
    #     # should check if v and a are within limits. The limit are read from the instrument manual
    #     if v <= 0 or v >= 24:
    #         print(f"Error: velocity {v} is out of limits [0, 24] deg/s.")
    #         return
    #     if a <= 0 or a >= 20:
    #         print(f"Error: acceleration {a} is out of limits [0, 20] deg/s^2.")
    #         return
    #     v_device = c_int(int(v * VCONVERT))
    #     a_device = c_int(int(a * ACONVERT))
    #     try:
    #         if lib.CC_SetVelParams(self.SN, v_device, a_device) != 0:   # I actually don't know if this does anything
    #             print("Warning: setting velocity failed.")
    #             self.v = None
    #             self.a = None
    #     except Exception as e:
    #         print(f"Error setting velocity: {e}")
    #     self.v = v  # should probably double check...
    #     self.a = a

    def home(self):
        # TIMEOUT = 60    # max timeout in seconds. This is probably a bit too long.
        try:
            if lib.CC_Home(self.SN) != 0: # home the device
                print("Kcube homing failed")
            else:
                print("Kcube homing started. You must manually get_position after homing finish.")
        except Exception as e:
            print(f"Error homing Thorlabs K-Cube: {e}")

    def convert_dev_to_real(self, dev_pos):
        return float(dev_pos / DCONVERT)  # convert device unit to real unit (deg)
    def convert_real_to_dev(self, real_pos):
        return int(real_pos * DCONVERT)

    def get_position(self):
        try:
            dev_pos = lib.CC_GetPosition(self.SN)            
            time.sleep(0.2)
            real_position = self.convert_dev_to_real(dev_pos)
        except Exception as e:
            print(f"Error getting position: {e}")
            raise
        self.pos = real_position
        return self.pos

    def move_rel_straight(self, d: float):
        """
        Move relative to current position by d in real units. Directly use method.
        Assume -180 < d <= 180
        No check afterwards
        Shouldn't be used by user.
        """
        if not (-180 < d <= 180):
            raise ValueError(f"move_rel_straight assumes -180 < d <= 180, got d={d}")
        dev_displacement = c_int(self.convert_real_to_dev(d))
        if lib.CC_MoveRelative(self.SN, dev_displacement) != 0:
            raise RuntimeError("Kcube move_rel_straight failed")
        self.get_position()

    def move_smart(self, d:float):
        '''
        Move a displacement. Smartly decide the shortest path.
        
        '''
        # smartly mov relative to currnet position
        reminder = float(d % 360)
        if reminder > 180:
            reminder = reminder - 360
        # guess estimated time. sleep for that much. self.v is read back from the
        # device at open() (see __init__), not the V0 default -- set_velocity()/
        # CC_SetVelParams is bugged and never actually writes a velocity to the hardware.
        t_est = abs(reminder / self.v) + 2
        # move.
        dev_displacement = c_int(self.convert_real_to_dev(reminder))
        if lib.CC_MoveRelative(self.SN, dev_displacement) != 0:
            raise RuntimeError("Kcube move_smart failed")
        time.sleep(t_est)
        self.get_position()

    move = move_smart   # alias of move
    
    def goto(self, d:float):
        # use a temporailiy pos instead of self.pos because the device pos is sometimes >360 or <0
        pos = self.get_position() % 360
        displacement = d - pos
        self.move_smart(displacement)

    go_to = goto  # alias of goto

    def trig(self, channel):    # check if channel has trigger signal. Not implemented yet.
        pass

    def oscilliate_by_trig(self, channel, d0, dosc):    # oscilliate between d0-dosc and d0+dosc by trigger signal on given channel.Not implemented yet.
        pass

class TL_hwp(TL_kcube):
    def __init__(self, SN:str = SN):
        super().__init__(SN)
        self.comment = 'Thorlabs K-Cube HWP device wrapper'

# example of hwp auto aligner
class hwp_signal_aligner:
    """HWP auto aligner based on signal feedback. Assume signal is a detector-like device with an method to return a float-like value. 
        Typical detector include an Thorlab powermeter, or a photodiode."""
    def __init__(self, hwp: TL_hwp, detector):
        self.hwp = hwp
        self.detector = detector

    def setup_acquire(self, method, **kwargs):
        """ Bind self.acquire to method(**kwargs), called fresh on every invocation. This is what
        makes self.acquire an abstract acquirer: minimize() just calls self.acquire() and doesn't
        need to know what device or method backs it."""
        self.acquire = lambda: method(**kwargs)

    def minimize(self, angle0 = 0, half_range = 45, tol = 0.1, timeout = 60, verbose = False):
        """ Rotate HWP to minimize the signal from the detector, via golden-section search
        over the bracket [angle0-half_range, angle0+half_range].

        Unlike a fixed-step left/right pattern search (whose step only shrinks when neither
        side improves -- a branch that noisy measurements can make rare or accidental, so the
        search can stall at a fixed resolution without ever tightening down), golden-section
        search shrinks the bracket by a constant ratio (~0.618) on *every* iteration regardless
        of which side wins. That makes it structurally unable to cycle, and it converges to
        `tol` within a bounded number of iterations (or hits `timeout`), using only one new
        detector reading (and one new HWP move) per iteration since the other probe point is
        always reused from the previous step.
        """
        start_time = time.time()
        invphi = (5 ** 0.5 - 1) / 2    # 1/phi  ~ 0.618
        invphi2 = (3 - 5 ** 0.5) / 2   # 1/phi^2 ~ 0.382

        def measure_at(angle):
            self.hwp.go_to(angle)
            return self.acquire()

        a, b = angle0 - half_range, angle0 + half_range
        h = b - a
        c = a + invphi2 * h
        d = a + invphi * h
        yc = measure_at(c)
        yd = measure_at(d)
        if verbose:
            print(f"Starting golden-section search over [{a:.3f}, {b:.3f}] deg, tol {tol} deg, timeout {timeout} s.")

        while h > tol:
            # check timeout
            if time.time() - start_time > timeout:
                print("Timeout reached. Stopping minimization.")
                break
            if yc < yd:
                b, d, yd = d, c, yc
                h = invphi * h
                c = a + invphi2 * h
                yc = measure_at(c)
            else:
                a, c, yc = c, d, yd
                h = invphi * h
                d = a + invphi * h
                yd = measure_at(d)
            if verbose:
                print(f"Bracket now [{a:.3f}, {b:.3f}] deg (width {h:.4f} deg), yc={yc}, yd={yd}.")

        best_angle = (a + b) / 2
        best_signal = measure_at(best_angle)
        if verbose:
            print(f"Converged to angle {best_angle:.3f} deg, signal {best_signal}.")
        return best_angle, best_signal

# debug code
# if __name__ == '__main__':
#     nd = TL_kcube(SN)
#     print(f"Current position is {nd.get_position()}")
#     nd.go_to(60)
#     print(f"Current position is {nd.get_position()}")
#     nd.move_rel(120)
#     print(f"Current position is {nd.get_position()}")
#     nd.close()
#     print("Job done!")
