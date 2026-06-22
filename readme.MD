# tr-MOKE Measurement Control

> **Status:** Work in progress — not yet functioning.

Python instrument control code for time-resolved magneto-optical Kerr effect (tr-MOKE) measurements.

## Setup

- Focused probe beam steered by galvo mirror
- Pump/probe beam delayed by Thorlab delaystage
- Balanced detector output fed to lock-in amplifier (chopper-modulated)
- DC channel: steady-state reflectivity; AC channel: tr-MOKE signal

## Requirements

**Standard:**
- Python 3.x
- numpy

**Custom (Hanjun, to be released separately):**
- `t_bbd_ds` — BBD translation stage control
- `t_kcube` — KCube motor driver interface
- `zi_mfli` — Zurich Instruments MFLI lock-in interface
- `hy_tools` — utility module (temporary dependency, to be removed in a future update)

