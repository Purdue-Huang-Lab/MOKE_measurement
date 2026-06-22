# AI_CODE_GUIDE.md — MOKE Measurement Repository

**Repository:** `Purdue-Huang-Lab/MOKE_measurement`  
**Documentation type:** Level 2 Developer Documentation + Level 3 AI-Agent Knowledge Base  
**Prepared for:** A lab AI assistant that should understand, explain, troubleshoot, and guide users through the MOKE measurement code.  
**Source files reviewed:**  

- `readme.MD`
- `script/moke_control_code.py`
- `script/moke_rig.py`

---

## 0. AI-Agent Usage Summary

This document is written for an AI coding assistant, lab assistant, or retrieval-augmented generation system that needs to answer questions about the `MOKE_measurement` repository.

The agent should treat this file as the main semantic guide for the repository. The raw code should still be inspected when exact implementation details are needed, but this guide explains the code architecture, the implemented workflow, the current limitations, the likely experimental context, and the safest way to answer user questions.

### Most important facts for the AI agent

1. This repository is for **magneto-optical Kerr effect (MOKE)** measurement, specifically **time-resolved MOKE / tr-MOKE**.
2. The README describes a system where a focused beam is controlled by a galvo, the balanced detector voltage is read through a lock-in amplifier modulated by a chopper, the DC signal is used for steady-state measurement, and the modulated lock-in signal is used for tr-MOKE.
3. The currently implemented executable workflow is a **time-delay scan**, not a full spatial scan.
4. The main implemented measurement object is the `moke_rig` dataclass in `script/moke_rig.py`.
5. The time scan is performed through:
   - `run_experiment_t(...)`
   - `moke_rig.t_scan_no_t0_correction(...)`
   - `moke_rig.single_measurement(...)`
6. Delay-stage control is done through a Thorlabs BBD301/DDS300-style delay-stage wrapper imported as `TL_ds`.
7. Half-wave plate control is prepared through a Thorlabs K-Cube wrapper imported as `TL_kcube`.
8. Lock-in readout is done through a Zurich Instruments MFLI wrapper imported as `MFLI`.
9. Galvo control is **not implemented yet** in the active code. The galvo variable is set to `None`, and spatial scan functions are commented out.
10. Magnetic field and temperature are explicitly **not controlled** by this code.
11. The code depends on external local packages under paths such as:
    - `F:\Git\optical_devices_toolbox\scripts_thorlabs`
    - `F:\Git\optical_devices_toolbox\scripts_zurich_instrument`
12. The code is hardware-dependent and should not be run casually on a machine without the correct instrument drivers, hardware connection, and lab safety checks.
13. As written, `script/moke_control_code.py` defines a function called `__main__()`, but it does not include a visible `if __name__ == "__main__": __main__()` guard in the reviewed source. Therefore, running the script directly may only define functions and imports unless the function is called explicitly or run through an IDE cell workflow.

---

## 1. Repository Purpose

The repository contains Python code for conducting MOKE measurements, with emphasis on **time-resolved MOKE**.

MOKE experiments measure magnetization-related optical response by analyzing changes in reflected light polarization. In this codebase, the reflected optical signal is measured using a balanced detector and a Zurich Instruments MFLI lock-in amplifier. The delay stage changes the pump-probe time delay. The implemented result is a time-dependent set of lock-in amplitude and phase values.

The repository is intended to help control a lab measurement setup involving:

- Focused optical probe beam
- Galvo mirror for spatial scanning, planned but not active in the implemented workflow
- Balanced photodetector
- Lock-in amplifier
- Chopper modulation reference
- Thorlabs delay stage
- Thorlabs K-Cube rotation mount for half-wave plate control
- External magnetic field and temperature control, handled manually or by other systems

---

## 2. Repository Structure

```text
MOKE_measurement/
├── readme.MD
├── LICENSE
├── CODEOWNERS
├── .gitignore
├── .gitattributes
└── script/
    ├── moke_control_code.py
    └── moke_rig.py
```

### File roles

| File | Role | Importance |
|---|---|---|
| `readme.MD` | Very short repository description | Gives the experimental intent |
| `script/moke_control_code.py` | Main user-facing experiment runner script | Creates device objects, defines scan arrays, runs the experiment, saves output |
| `script/moke_rig.py` | Experiment rig abstraction | Contains `moke_rig` dataclass and the implemented measurement methods |
| `LICENSE` | MIT license | Legal/reuse context |
| `CODEOWNERS` | GitHub code ownership metadata | Not part of measurement logic |
| `.gitignore`, `.gitattributes` | Git/repository configuration | Not part of measurement logic |

---

## 3. Current Measurement Capability

### Implemented now

The implemented measurement flow is:

```text
Set delay array
Set measurement-time array
Create instrument objects
Create moke_rig object
For each delay:
    Move delay stage to that delay
    Measure lock-in signal
    Store r, phase, r_std, phase_std
Save results to a tab-delimited text file
Close delay stage
```

The implemented scan is a **1D time-delay scan**.

The function name `t_scan_no_t0_correction` is important. It means that the code scans raw delay-stage time coordinates directly and does **not** subtract or correct for the experimental time-zero offset `t0`.

### Scaffolded but not implemented

The code contains commented-out sketches for:

- Steady-state galvo measurement
- Lock-in galvo measurement
- 1D spatial y-sweeps
- 2D spatial xy-sweeps
- GUI-oriented experiment function
- HWP balancing through K-Cube and MFLI

These are not active functions. The AI agent should not claim that the repository currently performs full 2D MOKE maps unless the user adds or restores those functions.

### Explicitly not controlled by this code

The code comments state that **magnetic field and temperature are not controlled by this code**.

Therefore, if a user asks:

> Does this code set the magnetic field?

The correct answer is:

> No. The code does not control magnetic field. Magnetic field must be controlled manually or by a separate instrument-control program.

If a user asks:

> Does this code control cryostat temperature?

The correct answer is:

> No. Temperature is not controlled by this code.

---

## 4. Hardware and Software Architecture

### Hardware implied by the code

| Hardware | Code object / import | Purpose |
|---|---|---|
| Thorlabs BBD301 brushless motor controller + DDS300 delay stage | `TL_ds` imported as `ds_class` | Controls pump-probe delay |
| Thorlabs K-Cube rotation mount | `TL_kcube` imported as `kcube_class` | Controls HWP, intended for detector balancing |
| Zurich Instruments MFLI lock-in amplifier | `MFLI` imported as `lockin` | Reads modulated MOKE signal |
| Galvo mirror | `galvo_device = None`; commented import | Planned spatial beam scanning |
| Chopper | Referenced in comments/README | Provides modulation reference to lock-in Aux input |
| Balanced detector | Read indirectly through lock-in | Measures reflected polarization signal |
| Magnet / field supply | Not controlled | Must be external/manual |
| Temperature/cryostat system | Not controlled | Must be external/manual |

### External software dependencies

The code imports the following standard or common Python packages:

```python
import numpy as np
import time
import sys
from dataclasses import dataclass
```

The code also imports local lab-specific packages:

```python
from hytools import hy_basic as hyb
from t_bbd_ds import TL_ds as ds_class
from t_kcube import TL_kcube as kcube_class
from zi_mfli import MFLI as lockin
```

The code modifies `sys.path` to locate external hardware-control wrappers:

```python
sys.path.insert(0, r'F:\Git\optical_devices_toolbox\scripts_thorlabs')
sys.path.insert(0, r'F:\Git\optical_devices_toolbox\scripts_zurich_instrument')
```

### Important AI-agent warning

The repository itself does **not** include the external instrument-control modules:

- `t_bbd_ds.py`
- `t_kcube.py`
- `zi_mfli.py`
- `hytools`

Therefore, the AI agent should avoid claiming that the repository is self-contained. It is not self-contained. It requires the local Huang Lab / Hanjun instrument toolbox or equivalent wrappers.

---

## 5. Main File: `script/moke_control_code.py`

### Purpose

`moke_control_code.py` is the top-level experiment-control script. It creates hardware objects, asks the user to confirm pre-run checks, defines a delay array and measurement-time array, calls the rig-level experiment function, saves the results, and closes the delay stage.

### High-level responsibilities

1. Import numerical and hardware-control libraries.
2. Add external instrument wrapper paths to `sys.path`.
3. Create objects for:
   - Delay stage
   - HWP K-Cube
   - Lock-in amplifier
   - MOKE rig
4. Print manual pre-run checklist.
5. Define scan parameters.
6. Run the delay scan.
7. Save results to disk.
8. Close the delay stage.

### Important code entities

#### `press_enter_to_proceed()`

```python
def press_enter_to_proceed():
    input("Press Enter to proceed...")
```

**Purpose:**  
Pauses the script until the user manually confirms that pre-run checks are complete.

**AI-agent interpretation:**  
This is a simple safety / workflow checkpoint. It does not verify anything automatically. It only waits for user input.

**User-facing explanation:**  
The script asks the experimentalist to confirm that the instruments are ready before starting the scan.

#### `__main__()`

```python
def __main__():
    ...
```

**Purpose:**  
Contains the main experiment procedure.

**Important note:**  
This function is named `__main__`, but it is not the same as Python’s normal entry-point guard. In the reviewed code, there is no visible:

```python
if __name__ == "__main__":
    __main__()
```

Therefore, the function may not execute automatically when running the script unless the user explicitly calls `__main__()` or executes it cell-by-cell in an IDE.

### Device initialization in `__main__()`

#### Save directory

```python
save_dir = r'F:\Git\MOKE_measurement\results'
hyb.check_make_dir(save_dir)
```

**Meaning:**  
Sets the result folder and creates it if needed.

**Dependency:**  
Requires `hytools.hy_basic.check_make_dir`.

**AI-agent warning:**  
This path is hard-coded for a Windows machine. Other users will need to change this path.

#### Delay stage

```python
BBD_serial_number = '103507474'
ds = ds_class(BBD_serial_number, NTRIP=4)
```

**Meaning:**  
Creates a Thorlabs delay-stage object.

**Important parameters:**

| Parameter | Meaning |
|---|---|
| `BBD_serial_number` | Serial number of the Thorlabs BBD motor controller |
| `NTRIP=4` | Device-specific parameter required by the `TL_ds` wrapper |

**AI-agent warning:**  
The serial number is hardware-specific. A different setup likely needs a different serial number.

#### K-Cube / HWP

```python
kcube_hwp_SN = '27600911'
hwp = kcube_class(kcube_hwp_SN)
```

**Meaning:**  
Creates a Thorlabs K-Cube object for controlling a half-wave plate.

**Current use:**  
The HWP object is passed into the rig object, but the active time-scan workflow does not use it directly.

**AI-agent warning:**  
Do not tell users that the code automatically balances the HWP. The balancing function is only scaffolded/commented in `moke_rig.py`.

#### Lock-in amplifier

```python
li_SN = 'dev5849'
li_HOST = '10.164.14.211'
li = lockin(li_SN, li_HOST)
```

**Meaning:**  
Creates a Zurich Instruments MFLI lock-in object.

**Important parameters:**

| Parameter | Meaning |
|---|---|
| `li_SN` | Zurich Instruments device ID |
| `li_HOST` | IP address or host address for communicating with the lock-in |

**AI-agent warning:**  
These values are setup-specific. Users must update them for a different lock-in or network configuration.

#### Galvo

```python
galvo_device = None
```

**Meaning:**  
No galvo object is initialized in the active code.

**AI-agent interpretation:**  
Spatial scanning is not active. Any galvo-based functionality is future work or unfinished.

#### Rig object

```python
rig = moke_rig.moke_rig(li, ds, galvo=galvo_device, hwp=hwp)
```

**Meaning:**  
Wraps the lock-in, delay stage, optional galvo, and optional HWP into one experiment object.

---

## 6. Pre-Run Checklist

The script prints:

```text
Pre-run checks:
Before running experiments, please check the following issues:

1. Is delay stage homed?
2. Is lock-in amplifier configured?
3. Is hwp balanced?
4. (If running spatial-MOKE) Is galvo device initialized?
```

### Meaning for the AI agent

These checks are manual. The code does not verify them automatically.

When a user asks how to run the experiment, the AI agent should include this checklist and explain that these are required before starting a scan.

### Safety interpretation

Because this code controls moving optical hardware and reads experimental instruments, the AI agent should encourage users to verify:

- Delay stage homing
- Physical travel limits
- Lock-in communication
- Chopper reference
- Beam alignment
- Detector balance
- Laser power
- Sample safety
- Magnet/cryostat status, if used

---

## 7. Scan Parameters in `moke_control_code.py`

### Delay array

```python
delay_array = np.linspace(0, 10, 100)
```

**Meaning:**  
Creates 100 evenly spaced delay points from 0 to 10 in the units expected by the delay-stage wrapper.

The code comments and function names suggest that this is a time coordinate, likely in ps, but the actual unit depends on the implementation of `TL_ds.goto_t(...)`.

**AI-agent caution:**  
Do not assume the unit is definitely ps unless confirmed from `t_bbd_ds.TL_ds`. The commented GUI function prints delay in ps, so ps is likely, but the external delay-stage wrapper defines the exact convention.

### Measurement-time array

```python
t_measure_array = np.ones(len(delay_array))
```

**Meaning:**  
Creates one measurement time per delay point. Here every delay is measured for nominally 1 second.

### Shape requirement

`delay_array` and `t_measure_array` must have the same shape because `moke_rig.t_scan_no_t0_correction(...)` checks that:

```python
t_raw.shape == t_measure.shape
```

### Runtime estimate

If there are 100 delay points and `t_measure_array` is all ones, the nominal measurement time is approximately 100 seconds, plus delay-stage movement overhead. However, `single_measurement()` applies a timing correction factor, described below.

---

## 8. Result Saving

The result is saved as:

```python
result_fname = f'{save_dir}\\lock_in_test.txt'
```

The code creates an output array:

```python
combined = np.zeros((results.shape[0], results.shape[1] + 1))
combined[:, 1:] = results
combined[:, 0] = delay_array
```

The intended output columns are:

```text
delay, r, phase, r_std, phase_std
```

The result is saved with:

```python
np.savetxt(
    result_fname,
    combined,
    fmt="%.6g",
    delimiter="\t",
    header=['delay', 'r', 'phase', 'r_std', 'phase_std']
)
```

### Output meaning

| Column | Meaning |
|---|---|
| `delay` | Raw delay value sent to delay stage |
| `r` | Lock-in amplitude magnitude from polar readout |
| `phase` | Lock-in phase from polar readout |
| `r_std` | Standard deviation / uncertainty of amplitude returned by `measure_avg` |
| `phase_std` | Standard deviation / uncertainty of phase returned by `measure_avg` |

### AI-agent implementation note

`np.savetxt(..., header=...)` usually expects the `header` argument to be a string, not a list. The code passes a list:

```python
header=['delay', 'r', 'phase', 'r_std', 'phase_std']
```

Depending on NumPy behavior, this may produce a string representation of the list in the header rather than a clean tab-separated header. A cleaner version would be:

```python
header="delay\tr\tphase\tr_std\tphase_std"
```

or:

```python
header="\t".join(["delay", "r", "phase", "r_std", "phase_std"])
```

The AI agent may recommend this if a user asks why the output header looks strange.

---

## 9. Main File: `script/moke_rig.py`

### Purpose

`moke_rig.py` defines the experiment rig abstraction. It groups the hardware-control objects into one dataclass and provides methods for lock-in measurement and time-delay scanning.

### Main active object

```python
@dataclass
class moke_rig:
    lockin: lockin
    delay_stage: ds_class
    galvo: object = None
    hwp: kcube_class = None
```

### Dataclass fields

| Field | Expected object type | Required? | Purpose |
|---|---|---:|---|
| `lockin` | `MFLI` wrapper | Yes | Acquire lock-in signal |
| `delay_stage` | `TL_ds` wrapper | Yes | Move delay stage |
| `galvo` | Galvo object | No | Intended for spatial scanning; not active |
| `hwp` | `TL_kcube` wrapper | No | Intended for half-wave plate control; not active in time scan |

### `__post_init__(self)`

```python
def __post_init__(self):
    self.t0 = 0
```

**Purpose:**  
Initializes a time-zero variable.

**Current use:**  
`t0` is initialized but not used in the active `t_scan_no_t0_correction` workflow.

**AI-agent interpretation:**  
The code may later support time-zero correction, but the current implemented scan uses raw delay values directly.

---

## 10. Function Reference

### 10.1 `moke_rig.single_measurement(self, t_measure=1)`

#### Location

`script/moke_rig.py`, inside class `moke_rig`.

#### Purpose

Performs one lock-in measurement at the current delay-stage position.

#### Code behavior

```python
TIMING_RATIO = 2
li = self.lockin
r, phase, r_std, phase_std = li.measure_avg('polar', t_measure/TIMING_RATIO)
return r, phase, r_std, phase_std
```

#### Inputs

| Input | Type | Meaning |
|---|---|---|
| `t_measure` | number, default `1` | Requested measurement duration |

#### Outputs

Returns a 4-tuple:

```python
(r, phase, r_std, phase_std)
```

| Output | Meaning |
|---|---|
| `r` | Lock-in polar amplitude magnitude |
| `phase` | Lock-in polar phase |
| `r_std` | Standard deviation of amplitude from averaged measurement |
| `phase_std` | Standard deviation of phase from averaged measurement |

#### Important timing behavior

The function defines:

```python
TIMING_RATIO = 2
```

and then calls:

```python
li.measure_avg('polar', t_measure/TIMING_RATIO)
```

The code comment says:

> Measurement time is actually twice of the requested time in the measure method.

Therefore, if the user asks for `t_measure = 1`, the function calls the MFLI wrapper with `0.5`, expecting the wrapper’s actual measurement duration to be approximately twice that.

#### AI-agent caution

This is a workaround for a known timing mismatch in the lock-in wrapper. The AI agent should not remove `TIMING_RATIO = 2` casually. It should explain that this compensates for the observed timing mismatch.

---

### 10.2 `moke_rig.t_scan_no_t0_correction(self, t_raw, t_measure)`

#### Location

`script/moke_rig.py`, inside class `moke_rig`.

#### Purpose

Scans the delay stage through a 1D array of raw delay values and records a lock-in measurement at each delay.

#### Inputs

| Input | Expected type | Meaning |
|---|---|---|
| `t_raw` | `np.ndarray`, 1D | Raw delay positions/times sent to the delay stage |
| `t_measure` | `np.ndarray`, 1D | Measurement duration for each delay point |

#### Validation checks

The function checks:

1. `t_raw` must be 1D.
2. `t_measure` must be 1D.
3. `t_raw.shape` must equal `t_measure.shape`.
4. All `t_measure` values must be positive.
5. All `t_raw` values must be within the delay-stage range:
   - `ds.tmin <= t_raw <= ds.tmax`

#### Delay-stage range dependency

The function relies on the delay-stage object exposing:

```python
ds.tmin
ds.tmax
ds.goto_t(...)
```

These are not defined in this repository; they come from the external `TL_ds` class.

#### Scan logic

For each delay point:

```python
ds.goto_t(t_raw[i])
result = self.single_measurement(t_measure[i])
results[i, :] = result
```

The result array has shape:

```python
(n, 4)
```

where:

```python
n = len(t_raw)
```

The four columns are:

```text
r, phase, r_std, phase_std
```

#### Important limitation

This function does **not** use `self.t0`. It does no time-zero correction.

If the user wants time-zero correction, the AI agent should suggest a new method such as:

```python
t_corrected = t_raw + self.t0
```

or:

```python
t_stage = t_requested + self.t0
```

but only after confirming the lab’s sign convention for time delay.

---

### 10.3 `run_experiment_t(rig, t_raw, t_measure)`

#### Location

`script/moke_rig.py`, module-level function.

#### Purpose

Thin wrapper function that runs the active time scan.

#### Code behavior

```python
def run_experiment_t(rig, t_raw, t_measure):
    results = rig.t_scan_no_t0_correction(t_raw, t_measure)
    return results
```

#### Inputs

| Input | Meaning |
|---|---|
| `rig` | An initialized `moke_rig` object |
| `t_raw` | Delay array |
| `t_measure` | Measurement-time array |

#### Output

Returns the same result as:

```python
rig.t_scan_no_t0_correction(t_raw, t_measure)
```

#### AI-agent interpretation

This function is a simple convenience wrapper. Most logic is inside the `moke_rig` class.

---

## 11. Active Data Flow

### Diagram

```text
User-defined parameters
    |
    |-- save_dir
    |-- delay_array
    |-- t_measure_array
    |
    v
Device initialization
    |
    |-- ds = TL_ds(...)
    |-- hwp = TL_kcube(...)
    |-- li = MFLI(...)
    |-- galvo_device = None
    |
    v
rig = moke_rig(li, ds, galvo=None, hwp=hwp)
    |
    v
run_experiment_t(rig, delay_array, t_measure_array)
    |
    v
rig.t_scan_no_t0_correction(delay_array, t_measure_array)
    |
    |-- validate arrays
    |-- validate delay-stage range
    |
    v
For each delay:
    ds.goto_t(delay)
    li.measure_avg('polar', t_measure / 2)
    store r, phase, r_std, phase_std
    |
    v
results array, shape = (n_delay, 4)
    |
    v
combined array, shape = (n_delay, 5)
    |
    v
Save tab-delimited text file:
delay, r, phase, r_std, phase_std
```

---

## 12. Common User Questions and Agent Routing Guide

This section is for the AI agent. When a user asks a question, use this table to route the answer to the relevant file/function.

| User question | Relevant file | Relevant object/function | Correct answer direction |
|---|---|---|---|
| What does this repository do? | `readme.MD`, `moke_control_code.py` | Top comments | It controls tr-MOKE measurements using delay stage + lock-in; spatial scan is planned |
| How do I run a time scan? | `moke_control_code.py` | `__main__()` | Configure serial numbers, host address, save path, delay array, measurement array, then call `__main__()` or add a main guard |
| Which function performs one measurement? | `moke_rig.py` | `single_measurement` | Calls `li.measure_avg('polar', t_measure/2)` and returns `r, phase, r_std, phase_std` |
| Which function moves the delay stage? | `moke_rig.py` | `t_scan_no_t0_correction` | Calls `ds.goto_t(t_raw[i])` at each delay point |
| Where is the delay array defined? | `moke_control_code.py` | `delay_array = np.linspace(0, 10, 100)` | In the main runner script |
| Where is the measurement time defined? | `moke_control_code.py` | `t_measure_array = np.ones(len(delay_array))` | One measurement duration per delay point |
| What are the output columns? | `moke_control_code.py`, `moke_rig.py` | Result saving block | `delay`, `r`, `phase`, `r_std`, `phase_std` |
| Does the code do time-zero correction? | `moke_rig.py` | `t_scan_no_t0_correction` | No, it explicitly scans without t0 correction |
| Where is `t0` used? | `moke_rig.py` | `__post_init__` | `t0` is initialized to 0 but not used in active scan |
| Does the code control magnetic field? | `moke_control_code.py` comments | Top docstring | No |
| Does the code control temperature? | `moke_control_code.py` comments | Top docstring | No |
| Does the code control a galvo? | `moke_control_code.py`, `moke_rig.py` | `galvo_device = None`; commented code | No active galvo control |
| How do I add galvo scanning? | `moke_rig.py` | Commented sweep functions | Implement galvo class, uncomment/repair sweep functions, pass actual galvo object |
| Why is the actual measurement time different? | `moke_rig.py` | `TIMING_RATIO = 2` | The code compensates for a known timing mismatch in `measure_avg` |
| What dependencies are missing? | Both Python files | Import section | `hytools`, `t_bbd_ds`, `t_kcube`, `zi_mfli` |
| Why does import fail? | Both Python files | `sys.path.insert(...)` and imports | External local toolbox path may not exist or dependencies are missing |
| Why does direct execution do nothing? | `moke_control_code.py` | `def __main__()` | There is no explicit main guard calling `__main__()` |
| Why does saving fail? | `moke_control_code.py` | `save_dir`, `np.savetxt` | Path may not exist, permission issue, or `hytools` missing |
| Why does delay range error occur? | `moke_rig.py` | Range check against `ds.tmin`, `ds.tmax` | Requested delay is outside hardware/wrapper-defined range |
| How do I change scan range? | `moke_control_code.py` | `np.linspace(0, 10, 100)` | Modify start, stop, and number of delay points |
| How do I change averaging time? | `moke_control_code.py` | `t_measure_array` | Modify values in `t_measure_array` |
| What is the shape of results? | `moke_rig.py` | `results = np.zeros((n, 4))` | `(number_of_delay_points, 4)` |
| Is HWP balancing implemented? | `moke_rig.py` | commented `hwp_balance_by_scope` | No, only a commented placeholder exists |

---

## 13. Parameter Reference

### User-editable parameters in `moke_control_code.py`

| Parameter | Current value | Meaning | User may change? | Caution |
|---|---:|---|---|---|
| `save_dir` | `F:\Git\MOKE_measurement\results` | Output folder | Yes | Use valid path; avoid overwriting important data |
| `BBD_serial_number` | `'103507474'` | Delay-stage controller serial | Yes | Must match connected hardware |
| `NTRIP` | `4` | Delay-stage wrapper parameter | Usually no | Change only if wrapper documentation requires it |
| `kcube_hwp_SN` | `'27600911'` | K-Cube serial number | Yes | Must match connected HWP controller |
| `li_SN` | `'dev5849'` | Zurich Instruments device ID | Yes | Must match MFLI device |
| `li_HOST` | `'10.164.14.211'` | Lock-in host/IP | Yes | Must match network configuration |
| `galvo_device` | `None` | Galvo controller object | Yes, future work | Requires implemented galvo driver |
| `delay_array` | `np.linspace(0, 10, 100)` | Delay points | Yes | Must stay inside `ds.tmin` and `ds.tmax` |
| `t_measure_array` | `np.ones(len(delay_array))` | Measurement time per delay | Yes | Must be positive; longer time increases scan duration |
| `result_fname` | `lock_in_test.txt` | Output filename | Yes | Avoid overwriting previous scans |

---

## 14. Error and Troubleshooting Guide

### Error: `ModuleNotFoundError: No module named 'hytools'`

**Likely cause:**  
The external `hytools` package is not installed or not on Python path.

**Where it occurs:**  
`moke_control_code.py`

**Fix:**  
Install `hytools` or add its parent directory to the Python path.

**Agent response:**  
Explain that `hytools.hy_basic.check_make_dir` is used only to create/check the output directory. If the user wants a quick local replacement, suggest:

```python
from pathlib import Path
Path(save_dir).mkdir(parents=True, exist_ok=True)
```

---

### Error: `ModuleNotFoundError: No module named 't_bbd_ds'`

**Likely cause:**  
The local Thorlabs delay-stage wrapper is missing or the path:

```text
F:\Git\optical_devices_toolbox\scripts_thorlabs
```

does not exist on the user’s machine.

**Where it occurs:**  
Both `moke_control_code.py` and `moke_rig.py`.

**Fix:**  
Confirm that the external `optical_devices_toolbox` repository exists locally and that `t_bbd_ds.py` is inside `scripts_thorlabs`.

---

### Error: `ModuleNotFoundError: No module named 't_kcube'`

**Likely cause:**  
The local Thorlabs K-Cube wrapper is missing or the path is wrong.

**Fix:**  
Confirm the external toolbox path and the K-Cube wrapper file.

---

### Error: `ModuleNotFoundError: No module named 'zi_mfli'`

**Likely cause:**  
The Zurich Instruments MFLI wrapper is missing or the path:

```text
F:\Git\optical_devices_toolbox\scripts_zurich_instrument
```

does not exist.

**Fix:**  
Install or locate the wrapper. Also verify Zurich Instruments Python dependencies if the wrapper requires them.

---

### Error: `ValueError: t must be 1D arrays`

**Cause:**  
`t_raw` is not a 1D NumPy array.

**Fix:**  
Use something like:

```python
delay_array = np.asarray(delay_array).ravel()
```

or define it as:

```python
delay_array = np.linspace(start, stop, n_points)
```

---

### Error: `ValueError: t_measure must be 1D arrays`

**Cause:**  
`t_measure` is not a 1D NumPy array.

**Fix:**  
Use:

```python
t_measure_array = np.ones(len(delay_array))
```

or:

```python
t_measure_array = np.asarray(t_measure_array).ravel()
```

---

### Error: `ValueError: t and t_measure must have the same length`

**Cause:**  
There is not exactly one measurement time for every delay point.

**Fix:**  

```python
t_measure_array = np.ones(len(delay_array)) * desired_measurement_time
```

---

### Error: `ValueError: t_measure must be positive`

**Cause:**  
At least one measurement time is zero or negative.

**Fix:**  
Make all values strictly positive:

```python
t_measure_array = np.maximum(t_measure_array, 0.1)
```

or define:

```python
t_measure_array = np.ones(len(delay_array))
```

---

### Error: `ValueError: t_raw must be within delay stage range`

**Cause:**  
One or more requested delay values are outside the range reported by the delay-stage object:

```python
ds.tmin
ds.tmax
```

**Fix:**  
Check the valid range:

```python
print(ds.tmin, ds.tmax)
```

Then define a delay array within that range:

```python
delay_array = np.linspace(ds.tmin, ds.tmax, n_points)
```

**Agent caution:**  
Do not blindly recommend scanning the full hardware range. The safe experimental range may be narrower because of beam alignment, stage travel, or optical delay geometry.

---

### Problem: Script appears to run but no experiment starts

**Likely cause:**  
`moke_control_code.py` defines `__main__()` but may not call it automatically.

**Fix option 1:**  
Run interactively and call:

```python
__main__()
```

**Fix option 2:**  
Add this to the bottom of `moke_control_code.py`:

```python
if __name__ == "__main__":
    __main__()
```

---

### Problem: Output header looks strange

**Likely cause:**  
`np.savetxt` was given a Python list as the header.

**Current code:**

```python
header=['delay', 'r', 'phase', 'r_std', 'phase_std']
```

**Suggested fix:**

```python
header="delay\tr\tphase\tr_std\tphase_std"
```

---

### Problem: Measurement duration is half of what user expects inside `measure_avg`

**Explanation:**  
The code intentionally calls:

```python
li.measure_avg('polar', t_measure/TIMING_RATIO)
```

with:

```python
TIMING_RATIO = 2
```

because the author observed that the MFLI wrapper’s actual measurement time is approximately twice the requested value.

**Agent caution:**  
Do not remove this unless the timing behavior of `zi_mfli.MFLI.measure_avg` has been verified.

---

## 15. Known Limitations and Current TODOs

### 15.1 No active galvo implementation

The code comments mention focused probe light controlled by a galvo mirror and include commented-out spatial scanning functions, but the active code sets:

```python
galvo_device = None
```

The import is also commented:

```python
# import galvo_control as galvo
```

Therefore, spatial scanning is not operational in the reviewed code.

### 15.2 No time-zero correction

The class initializes:

```python
self.t0 = 0
```

but the active scan function is explicitly named:

```python
t_scan_no_t0_correction
```

and does not use `self.t0`.

### 15.3 No magnetic-field control

The code comments state that magnetic field is not controlled.

### 15.4 No temperature control

The code comments state that temperature is not controlled.

### 15.5 External dependencies are not included

The hardware wrappers are outside the repository.

### 15.6 No robust logging

The script saves numerical results but does not save a structured metadata file with:

- Date/time
- Sample name
- Operator name
- Magnetic field
- Temperature
- Pump/probe power
- Wavelength
- Objective
- Chopper frequency
- Lock-in time constant
- Lock-in sensitivity
- HWP angle
- Delay-stage calibration
- Git commit hash

For reproducible experiments, the agent should recommend adding metadata logging.

### 15.7 No exception-safe cleanup

If an error occurs during the scan, `ds.close()` may not execute. A safer pattern would use `try/finally`.

Example:

```python
try:
    results = moke_rig.run_experiment_t(rig, delay_array, t_measure_array)
finally:
    ds.close()
```

### 15.8 No real-time plotting

The current implemented code does not plot data live during the scan.

### 15.9 No autosave during scan

Results are saved only after the full scan completes. If the script crashes mid-scan, partial data may be lost.

### 15.10 No configuration file

Parameters are hard-coded in the Python script. A future improvement would be a `config.yaml` or `config.json`.

---

## 16. Recommended Future Documentation Files

For a larger version of this repository, split this document into:

```text
README.md
AI_CODE_GUIDE.md
CODE_MAP.md
FUNCTION_REFERENCE.md
HARDWARE_SETUP.md
MEASUREMENT_WORKFLOW.md
PARAMETERS.md
TROUBLESHOOTING.md
SAFETY_NOTES.md
```

For the current small repository, this single `AI_CODE_GUIDE.md` is enough.

---

## 17. Recommended Improvements for the Codebase

These are not required to understand the current code, but they would make the repository much more robust and AI-agent-friendly.

### 17.1 Add a proper entry point

At the end of `moke_control_code.py`, add:

```python
if __name__ == "__main__":
    __main__()
```

### 17.2 Rename `__main__`

The function name `__main__()` may confuse users. A clearer name would be:

```python
def run_moke_time_scan():
    ...
```

Then use:

```python
if __name__ == "__main__":
    run_moke_time_scan()
```

### 17.3 Replace hard-coded Windows paths

Instead of:

```python
save_dir = r'F:\Git\MOKE_measurement\results'
```

use:

```python
from pathlib import Path
save_dir = Path(__file__).resolve().parents[1] / "results"
save_dir.mkdir(parents=True, exist_ok=True)
```

### 17.4 Add metadata saving

Save metadata alongside data:

```python
metadata = {
    "delay_array_start": float(delay_array[0]),
    "delay_array_stop": float(delay_array[-1]),
    "n_delay_points": int(len(delay_array)),
    "measurement_time_s": float(t_measure_array[0]),
    "lockin_device": li_SN,
    "lockin_host": li_HOST,
    "delay_stage_serial": BBD_serial_number,
}
```

### 17.5 Add partial autosave

Inside the scan loop, save each row immediately or periodically.

### 17.6 Add time-zero correction function

Add a separate method:

```python
def t_scan_with_t0_correction(self, t_requested, t_measure):
    t_stage = t_requested + self.t0
    return self.t_scan_no_t0_correction(t_stage, t_measure)
```

Only use this after confirming the sign convention experimentally.

### 17.7 Add live plotting

For experimental feedback, plot `r` or `phase` versus delay while scanning.

### 17.8 Add structured exceptions

Wrap hardware communication failures with clear messages:

```python
try:
    ds.goto_t(t_raw[i])
except Exception as exc:
    raise RuntimeError(f"Delay stage failed at index {i}, delay {t_raw[i]}") from exc
```

### 17.9 Add mock instrument mode

For testing without hardware, add mock versions of:

- `TL_ds`
- `TL_kcube`
- `MFLI`

This would allow software development without connecting instruments.

---

## 18. AI-Agent Answering Rules

When answering user questions about this repository, the AI agent should follow these rules.

### Rule 1 — Distinguish active code from planned/commented code

The agent must clearly distinguish:

- Active implemented time scan
- Commented-out spatial scan scaffolding
- Future galvo/HWP balancing functionality

Correct phrasing:

> The active code currently performs a time-delay scan. The spatial galvo scan is only scaffolded in commented code and is not currently active.

Incorrect phrasing:

> The code performs full time-resolved spatial MOKE mapping.

### Rule 2 — Do not assume magnetic field or temperature control

The code explicitly says magnetic field and temperature are not controlled.

Correct phrasing:

> You need to set magnetic field and temperature using separate hardware or manually.

### Rule 3 — Warn before hardware changes

When a user asks to modify delay range, measurement time, lock-in settings, HWP behavior, or galvo movement, the agent should mention relevant hardware safety checks.

### Rule 4 — Mention external dependencies

For import errors, the first thing to check is whether the external local instrument toolbox exists.

### Rule 5 — Be careful with units

The delay values likely represent time delay, probably ps, but the actual unit is defined by `TL_ds.goto_t`. The AI agent should avoid claiming a unit unless it has inspected the external `t_bbd_ds` wrapper.

### Rule 6 — Explain result columns clearly

The result columns are:

```text
delay, r, phase, r_std, phase_std
```

where `r` and `phase` are from lock-in polar-mode averaging.

### Rule 7 — When debugging, route by function

For measurement values, inspect:

```text
moke_rig.single_measurement
```

For delay movement, inspect:

```text
moke_rig.t_scan_no_t0_correction
```

For hardware serial numbers and scan arrays, inspect:

```text
moke_control_code.__main__
```

For saving, inspect the `np.savetxt` block in:

```text
moke_control_code.__main__
```

### Rule 8 — Do not overclaim completeness

This repository is a minimal working/control script, not a polished full experiment platform.

### Rule 9 — Prefer small, reversible code changes

For lab hardware code, recommend small changes and testing with safe values.

### Rule 10 — Recommend mock mode for software-only testing

If the user wants to develop without hardware, suggest mock classes rather than trying to run the hardware code.

---

## 19. Example Questions and Ideal AI Answers

### Q1. “What does this code do?”

**Ideal answer:**  
This code controls a time-resolved MOKE measurement. It creates hardware-control objects for a Thorlabs delay stage, a Thorlabs K-Cube HWP mount, and a Zurich Instruments MFLI lock-in amplifier. The implemented workflow scans a delay array, moves the delay stage to each delay point, records lock-in amplitude and phase using `measure_avg('polar', ...)`, and saves a text file with columns `delay`, `r`, `phase`, `r_std`, and `phase_std`. Galvo-based spatial scanning is mentioned but not active in the current code.

---

### Q2. “Where do I change the delay scan range?”

**Ideal answer:**  
Change this line in `script/moke_control_code.py`:

```python
delay_array = np.linspace(0, 10, 100)
```

The first value is the start delay, the second is the stop delay, and the third is the number of points. Make sure the values are inside the delay-stage range defined by `ds.tmin` and `ds.tmax`.

---

### Q3. “Where do I change the integration time?”

**Ideal answer:**  
Change this line in `script/moke_control_code.py`:

```python
t_measure_array = np.ones(len(delay_array))
```

This sets a nominal measurement time of 1 second at every delay. For 2 seconds per delay point:

```python
t_measure_array = 2 * np.ones(len(delay_array))
```

Remember that `single_measurement()` divides this value by `TIMING_RATIO = 2` before passing it to the MFLI wrapper, because the wrapper appears to measure for twice the requested time.

---

### Q4. “Why does the code divide measurement time by 2?”

**Ideal answer:**  
Inside `moke_rig.single_measurement()`, the code uses:

```python
TIMING_RATIO = 2
li.measure_avg('polar', t_measure/TIMING_RATIO)
```

The comment says the actual measurement time in the lock-in wrapper is about twice the requested time. Dividing by 2 compensates for that mismatch.

---

### Q5. “Does the code perform spatial MOKE mapping?”

**Ideal answer:**  
Not in the active implementation. The README and comments mention a galvo-controlled focused beam, and `moke_rig.py` contains commented-out functions for spatial sweeps. However, the active runner sets `galvo_device = None`, and the galvo import is commented out. The current working path is a 1D time-delay scan.

---

### Q6. “Does the code control magnetic field?”

**Ideal answer:**  
No. The code comments explicitly state that magnetic field is not controlled by this code. Field must be controlled manually or by a separate program.

---

### Q7. “Does the code control temperature?”

**Ideal answer:**  
No. Temperature is not controlled by this code. Use the cryostat or temperature controller separately.

---

### Q8. “What is the output file?”

**Ideal answer:**  
The output file is currently:

```text
F:\Git\MOKE_measurement\results\lock_in_test.txt
```

It is a tab-delimited text file with intended columns:

```text
delay, r, phase, r_std, phase_std
```

You can change the folder through `save_dir` and the file name through `result_fname` in `moke_control_code.py`.

---

### Q9. “Why does the script not start when I run it?”

**Ideal answer:**  
The reviewed code defines a function called `__main__()`, but it does not visibly call that function at the bottom of the script. Add:

```python
if __name__ == "__main__":
    __main__()
```

or call `__main__()` manually from your Python session.

---

### Q10. “What should I inspect if the lock-in data look wrong?”

**Ideal answer:**  
Inspect:

1. `moke_rig.single_measurement()` — this calls `li.measure_avg('polar', t_measure/2)`.
2. The external `zi_mfli.MFLI.measure_avg` implementation — this actually communicates with the lock-in.
3. Lock-in hardware settings — reference input, time constant, sensitivity, demodulator settings, and chopper reference.
4. Balanced detector alignment and HWP balance.

---

## 20. Suggested AI Retrieval Chunks

For an AI agent using retrieval, this document can be chunked by the following headings:

1. Repository Purpose
2. Hardware and Software Architecture
3. `moke_control_code.py`
4. `moke_rig.py`
5. Function Reference
6. Parameter Reference
7. Troubleshooting Guide
8. AI-Agent Answering Rules
9. Example Questions and Ideal AI Answers

The most useful retrieval queries are likely:

```text
delay scan
single_measurement
run_experiment_t
t_scan_no_t0_correction
MFLI measure_avg polar
TIMING_RATIO
output columns
galvo scanning
magnetic field not controlled
temperature not controlled
serial number
lock-in host
K-Cube HWP
delay stage range
```

---

## 21. Minimal Human-Facing README Replacement

If this repository needs a better `README.md`, this shorter text could replace the current README:

```markdown
# MOKE Measurement

Python control code for time-resolved magneto-optical Kerr effect (tr-MOKE) measurements in the Huang Lab.

The active workflow performs a 1D delay scan. At each delay point, the code moves a Thorlabs delay stage, reads the reflected signal using a Zurich Instruments MFLI lock-in amplifier, and saves lock-in amplitude/phase data.

## Main files

- `script/moke_control_code.py` — top-level experiment runner
- `script/moke_rig.py` — experiment rig abstraction and scan methods

## Hardware

The code is designed for:

- Thorlabs BBD301 / DDS300 delay stage
- Thorlabs K-Cube rotation mount for HWP control
- Zurich Instruments MFLI lock-in amplifier
- Balanced photodetector
- Chopper reference
- Optional galvo scanner, not active in current implementation

Magnetic field and temperature are not controlled by this code.

## Output

The time-scan output is a tab-delimited text file with columns:

```text
delay, r, phase, r_std, phase_std
```

## Notes

The repository depends on external local hardware-control wrappers from `optical_devices_toolbox`.
```

---

## 22. Final Agent Grounding Statement

The AI agent should answer questions about this repository using the following concise mental model:

> This is a small hardware-control repository for tr-MOKE. The active code creates a lock-in, delay stage, optional HWP, and placeholder galvo device. The implemented measurement is a 1D delay scan without time-zero correction. At each delay, the delay stage moves, the MFLI lock-in is averaged in polar mode, and the result is saved as delay, amplitude, phase, and their standard deviations. Galvo scanning, HWP auto-balancing, magnetic-field control, and temperature control are not implemented in the active code.

