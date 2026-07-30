# Helicam 3.0 — Register Description
*Document date: 05/11/2015*

The goal of this list is to show the register mapping and to describe the different parameters.

## 1. Overview

For the register type, the following abbreviations are used:

- **r**: Register is readable
- **w**: Register is writable
- **u**: Register may be updated by FPGA
- **S**: Special function

### Global Control registers (0x00 – 0x0ff)

| Address | Name | Type | Description | Default |
|---|---|---|---|---|
| 0x00 (0) | - | - | DO NOT USE! | - |
| 0x02 (2) | AcqCtrl0 (7:0) | rwu | Set camera and acquisition modes | 0x50 |
| 0x03 (3) | AcqCtrl1 (15:8) | rwu | | 0x07 |
| 0x04 (4) | DataPathCtrl | rwu | BIST, Build in self tests, others | 0x00 |
| 0x06 (6) | HwCtrl | rw | Controls HW on board | 0x00 |
| 0x07 (7) | PowerCtrl | rw | Controls the on board switching regulators | 0x21 |
| 0x08 (8) | TrigOnPosCtrl | rw | Enables and controls the trigger on position feature | 0x00 |
| 0x09 | TrigOnPos0 (7:0) | rw | Position (Encoder value) where a trigger is generated. Only active if 'TrigOnPos' feature is enabled | 0x00 |
| 0x0a | TrigOnPos1 (15:8) | rw | | 0x00 |
| 0x0b | TrigOnPos2 (23:16) | rw | | 0x00 |
| 0x0c | TrigOnPos3 (31:24) | rw | | 0x00 |
| 0x0d–0x0f | | | | |

### Sensor configuration (0x10 – 0x2f)

| Address | Name | Type | Description | Default |
|---|---|---|---|---|
| 0x10 (16) | SensTqp0 (7..0) | rw | Time quarter period (in sequencer cycles) of the sensor demodulation stage | 0x1d |
| 0x11 (17) | SensTqp1 (15..8) | rw | | 0x00 |
| 0x12 (18) | SensTqp2 (23..16) | rw | | 0x00 |
| 0x14 (20) | SensNavM20 | rw | Ncyc = SensNavM2 × 2 + 2. Allowed range for SensNavM2: [1…255] | 0x30 |
| 0x15 (21) | SensNavM21 | | | 0x00 |
| 0x16 (22) | SensNFrames0 | rw | Number of frames taken when triggering | 0x80 |
| 0x17 (23) | SensNFrames1 | rw | | 0x00 |
| 0x18 (24) | FrmDur35MHz0 (7:0) | r | Frame duration T_Frame between two consecutive frames. Calculated from parameters SensTqp and SensNavM2. Value in 1/35MHz sequencer clock cycles. | 0x00 |
| 0x19 (25) | FrmDur35MHz1 (15:8) | r | | 0x00 |
| 0x1a (26) | FrmDur35MHz2 (23:16) | r | | 0x00 |
| 0x1b (27) | FrmDur35MHz3 (31:24) | r | | 0x00 |
| 0x1c (28) | TDemodCyc35MHz0 (7..0) | r | Duration of a sensor demodulation cycle in 1/35MHz clock cycles. | 0xec |
| 0x1d (29) | TDemodCyc35MHz1 (16..8) | r | | 0x00 |
| 0x1e (30) | SensDeltaExp0 (7..0) | rw | This value (multiplied by 1/35MHz) will be subtracted from the sensor exposure time of a quarter period | 0x00 |
| 0x1f (31) | SensDeltaExp1 (11..8) | rw | | 0x00 |
| 0x20 (32) | SensRegAnaFct | rw | Sensors analogue functions register | 0x0a |
| 0x21–0x24 | | | | |
| 0x25 | SensNDarkFrames | rw | HDR intensity mode parameter | 0x0a |
| 0x26 | SensExpTime0 (7:0) | rw | HDR intensity mode parameters | 0x80 |
| 0x27 | SensExpTime1 (15:8) | rw | | 0x00 |
| 0x28 (40) | SensCaldur0 (7:0) | rw | Duration of offset compensation in sequencer cycles (1/35MHz) | 0x98c |
| 0x29 (41) | SensCaldur1 (11:8) | rw | | |
| 0x2a–0x2f | | | | |

### Data processing + configuration of algorithms (0x30 – 0x4f)

| Address | Name | Type | Description | Default |
|---|---|---|---|---|
| 0x30 (48) | ProcConfig | rw | -- not used -- | 0x00 |
| 0x31 (49) | AscanProc | rw | Global Ascan processing parameters | 0x3f |
| 0x32 (50) | BiasI0 | rw | Bias value on I for the first two frames of the volume (10Bit) | 0x000 |
| 0x33 (51) | BiasI1 | rw | | |
| 0x34 (52) | BiasQ0 | rw | Bias value on Q for the first two frames of the volume (10Bit) | 0x000 |
| 0x35 (53) | BiasQ1 | rw | | |
| 0x38 (56) | OffsetProc0 | rw | Offset modes, parameters and meta/debug information | 0x0c |
| 0x39 (57) | OffsetProc1 | rw | | 0x00 |
| 0x3a (58) | OffsetProc2 | rw | | 0xff |
| 0x3b (59) | OffsetProc3 | rw | | 0x03 |
| 0x3c–0x3f | | | | |
| 0x40 (64) | ExSimpMaxHwin | rw | Window size of data transmitted to host. Values 1..10 valid → window sizes 3–21 | 0x05 |
| 0x41 (65) | FirstSurfAtsh0 | rw | First surface amplitude threshold registers | 0x00 |
| 0x42 (66) | FirstSurfAtsh1 | rw | | 0x00 |
| 0x43 (67) | FirstSurfCtrl | rw | First surface configuration register | 0x00 |
| 0x44–0x45 | | | | |
| 0x46 (70) | EnergyLutCtrl | rwS | Control register for writing energy function LUT | 0x00 |
| 0x47 (71) | EnergyLutData0 (7:0) | rwS | Energy LUT word | 0x00 |
| 0x48 (72) | EnergyLutData1 (16:8) | rwS | | 0x00 |
| 0x49 (73) | UndRelParam | rw | Under relaxation parameter u(0.8) | 0xc0 |
| 0x4a (74) | ZRangeStart0 | rw | Starting point minimize energy u(12.0) | 0x00 |
| 0x4b (75) | ZRangeStart1 | rw | | 0x00 |
| 0x4c (76) | ZRangeEnd0 | rw | Last/ending point minimize energy u(12.0) | 0xff |
| 0x4d (77) | ZRangeEnd1 | rw | | 0x01 |
| 0x4e (78) | MinEnergWin | rw | Half size of the window (around the 'mean z' of the neighbours) taken into account | 0x10 |
| 0x4f | | | | |

### Test, BIST: Configuration and Results (0x50 – 0x53)

| Address | Name | Type | Description | Default |
|---|---|---|---|---|
| 0x50 (80) | ObsAddr | rw | Address to observe | 0x00 |
| 0x51 (81) | ObsData | ru | Data observed | 0x00 |
| 0x52 (82) | BistNum | rw | Number of build-in test to be applied | 0x00 |
| 0x53 | | | | |

### Segmented volume feature (0x54 – 0x59)

| Address | Name | Type | Description | Default |
|---|---|---|---|---|
| 0x54 | Seg1SensNFrames0 (7:0) | rw | Number of frames for the 1st segment (sensor delivers data) | 0x64 |
| 0x55 | Seg1SensNFrames1 (8) | | | 0x00 |
| 0x56 | Seg2SensNFrames2 (7:0) | rw | Number of frames for the 2nd segment (no data from sensor) | 0xff |
| 0x57 | Seg2SensNFrames3 (11:8) | | | 0x03 |
| 0x58 | Seg2SensMultiple0 (7:0) | rw | Multiplier for the number of frames in the 2nd segment | 0x01 |
| 0x59 | Seg2SensMultiple1 (11:8) | | | 0x00 |

### Global minEnergy settings (0x5a – 0x5c)

| Address | Name | Type | Description | Default |
|---|---|---|---|---|
| 0x5a | IterCtrl | rw | Enable integer/frac algorithm | 0x03 |
| 0x5b | IterMaxInt | rw | Max. number of iterations in integer path | 0x08 |
| 0x5c | IterMaxFrac | rw | Max. number of iterations in fractional path | 0x08 |
| 0x5d–0x5f | | | | |

### Status Registers (0x60 – 0x7f)

| Address | Name | Type | Description | Default |
|---|---|---|---|---|
| 0x60 | StatSens | ru | Status of sensor quarters | 0x00 |
| 0x61 | StatMem | ru | Status of the DDR2 memories | 0x00 |
| 0x62–0x77 | Reserved | | | |
| 0x78 | VerV | r | Version sub information Version | - |
| 0x79 | VerD | r | Version sub information Day | - |
| 0x7a | VerM | r | Version sub information Month | - |
| 0x7b | VerY | r | Version sub information Year | - |
| 0x7e–0x7f | | | | |

---

## 2. Detailed register description

Columns used below:

| Field | Meaning |
|---|---|
| Addr | Address of the register |
| Bit | Used bits for this parameter |
| Name | Parameter name |
| Description | Detailed description for this parameter |
| Cammode | This parameter can be used if one of the listed commodes is selected (0–7) |
| Level | Degree of difficulty: 1 = basic, 2 = intermediate, 3 = advanced |
| Range | Possible value range for this parameter |
| Default | Default value after power up and open the camera |

### 2.1  0x02 – 0x03, AcqCtrl

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x02 | 0 | PhiAEdgeDet | — | | | | - |
| | 1 | SegVolume | 1: Enable segmented volume feature. 0: Disable segmented volume feature. | all | 2 | 0–1 | '0' |
| | 2 | ExtTqp | 0: TQP from CSR (TqpReg) is used. 1: External TQP. IN3, IN4 or both (e.g. quadrature encoder mode) generate the trigger for starting integrating a quarter period (TQP) on the sensor. | all | 3 | 0–1 | '0' |
| | 3 | SingleVolume | 0: Off (normal mode). 1: Single volume acquisition (AcqStop set after having scanned one volume after AcqStop was cleared) | all | 3 | 0–1 | '0' |
| | 4 | TrigFreeExtN | 0: Acquisition controlled by external trigger source. 1: Free running acquisition | all | 1 | 0–1 | '1' |
| | 5 | reserved | | | | | - |
| | 6 | AcqStop | 0: Acquisition is running. 1: Acquisition is stopped (default) | all | 1 | 0–1 | '1' |
| | 7 | DoSeqRld | 0: No sequencer code reloading active. 1: Sequencer reloading triggered; cleared by FPGA when done. | all | 2 | 0–1 | '0' |
| 0x03 | 2:0 | CamMode | 000: raw IQ, 001: Amplitude, 010: smoothed Amp., 011: intensity, 100: SimpleMax (ini. Surface), 101: Extended SimpleMax, 111: MinEnergy | | 1 | 0–7 | "111" |
| | 3 | VolReady | 1: Volume in AB_Memory. 0: AB_Memory empty (read only register) | all | 3 | - | '0' |
| | 4 | MemSoftRes | 1: AB_Memory soft reset (must be set back to 0) | all | 3 | 0–1 | '0' |
| | 5 | CalDur1Cyc | 1: Offset compensation takes exactly 1 cycle (calculated from FPGA with TQP reg). 0: Time for offset compensation defined by register 'SensCaldur' (0x28/0x29) | all | 3 | 0–1 | '1' |
| | 6 | SensCfgBusy | 0: Device ready to receive trigger and start new acquisition. 1: Device is busy and triggers will be ignored | all | 2 | - | '0' |
| | 7 | ExtTqpPuls | 0: External TQP pulses generated on one channel only. 1: External TQP pulses generated on both channels | all | 2 | 0–1 | '0' |

### 2.2  0x04, DataPathCtrl

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x04 | 4:0 | reserved | | | | | - |
| | 5 | CalSurfWhileAcq | 0: Normal acquisition mode (new measurement after results transferred to host). 1: High-speed acquisition mode (new measurement while surface calculations are in process). Do not use ztags from header in this case! | 7 | 3 | 0–1 | '0' |
| | 6 | EnSBIS | 0: No Sensor Built-in Self Test. 1: Sensor BIST enabled → electrical stimulation of sensor; not used for extTQP or intensity mode | all | 3 | 0–1 | '0' |
| | 7 | DoBist | 0: No BIST active. 1: BIST triggered, cleared by FPGA when done. Ensure AcqStop=1 and all remaining data fetched from USB before triggering (DDR memory data will be overwritten). | all | 3 | 0–1 | '0' |

### 2.3  0x06, HwCtrl

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x06 | 0 | EnSynFOut | 0: Disables synchronization signal on OUT3 (rectangular waveform at demodulation frequency fd, see appendix A2). 1: Enables it (not available in extTQP mode) | all | 3 | 0–1 | '0' |
| | 1 | OutEnDrv | 0: OutEnDrv (Pin 5 on Hirose) = 0 → driver off. 1: = 1 → driver on. Not available with ConBrd2V0 | all | 1 | 0–1 | '0' |
| | 2 | Out1 | General purpose output (if ConBrd3V0 configured Pin 12 of Hirose as output). Not available with ConBrd2V0 | all | 2 | 0–1 | '0' |
| | 3 | In1 | General purpose input (if ConBrd3V0 configured Pin 12 of Hirose as input). Not available with ConBrd2V0 | all | 2 | 0–1 | '0' |
| | 4 | InvEncCnt | Invert encoder counter from camera (invert profile if using zTags) | 0,1,2,4,5,7 | 1 | 0–1 | '1' |
| | 5 | EnSprOsc | 0: disable spread spectrum oscillator. 1: enable | all | 3 | 0–1 | '0' |
| | 6 | reserved | | | | | - |
| | 7 | SoftRes | 0: Normal (running) mode (default). 1: FPGA in SoftReset mode; CSR contents preserved | all | 3 | 0–1 | '0' |

### 2.4  0x07, PowerCtrl

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x07 | 7:0 | PowerCtrl | Length of 1/3 of the synchronisation period for sensor board power regulators, 200MHz system clock cycles. Default: 2.02 MHz (33 / 0x21). If set to 0x00, power synchronisation outputs are kept at '0' continuously. | all | 3 | 0x00–0xff | 0x21 |

### 2.5  0x08, TrigOnPosCtrl

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x08 | 3:0 | reserved | | | | | '0' |
| | 4 | MskTrgOnPos | 0: Counter cleared on every Sync (on pulse w1, see manual). 1: Counter cannot be cleared by Sync (input masked). Use only if EnTrigOnPos=1 | all | 2 | 0–1 | '0' |
| | 5 | TrgDown | 0: TriggerUp (trigger generated passing TrigOnPos smaller→bigger). 1: TriggerDown (bigger→smaller). Use only if EnTrigOnPos=1 | all | 2 | 0–1 | '0' |
| | 6 | ClrPosCnt | 1: Sets position counter to 0 (reset). Use only if EnTrigOnPos=1 | all | 2 | 0–1 | '0' |
| | 7 | EnTrigOnPos | 1: Global Trigger on Position feature enabled. 0: disabled | all | 2 | 0–1 | '0' |

### 2.6  0x10 – 0x12, SensTqp

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x10, 0x11 | 11:0 | SensTqp | Time quarter period (in sequencer cycles) of the sensor demodulation stage. SensTqp = f_sens / (8×f_dem) − 30 | 0,1,2,4,5,7 | 1 | 0–0xfff | 0x1d |
| | 15:12 | reserved | | | | | |

### 2.7  0x14 – 0x15, SensNavM2

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x14, 0x15 | 11:0 | SensNavM2 | Number of averaging/demodulating cycles per frame: SensNavM2 × 2 + 2 (from symmetrical sequencer) | 0,1,2,4,5,7 | 1 | 0–0xff | 0x30 |
| | 15:12 | reserved | | | | | |

### 2.8  0x16 – 0x17, SensNFrames

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x16, 0x17 | 8:0 | SensNFrames | Number of frames taken by the sensor when triggered | all | 1 | 0xa–0x1ff | 0x80 |
| | 15:9 | reserved | | | | | |

### 2.9  0x18 – 0x1b, FrmDur35MHz

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x18–0x1b | 31:0 | FrmDur35MHz | Frame duration T_Frame between two consecutive frames. Calculated from SensTqp and SensNavM2. Value in 1/35MHz sequencer clock cycles. | all | 2 | - | 0x00 |

### 2.10  0x1c – 0x1d, TDemodCyc35MHz

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x1c, 0x1d | 16:0 | TDemodCyc35MHz | Duration of a sensor demodulation cycle in 1/35MHz clock cycles. | all | 2 | - | 0xec |

### 2.11  0x1e – 0x1f, SensDeltaExp

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x1e, 0x1f | 11:0 | SensDeltaExp | This value (× 1/35MHz) is subtracted from the sensor exposure time of a quarter period | 0,1,2,4,5,7 | 2 | 0–0xfff | 0x000 |
| | 12:15 | reserved | | | | | |

### 2.12  0x20, SensRegAnaFct

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x20 | 0 | LoadTestSeq | 1: load Testsequencer without patching. 0: load normal sequencer, enable patching | 3 | 3 | 0–1 | '0' |
| | 1 | BSEnable | Bias suppression enable (offset compensation in sensor). 1: enabled, 0: disabled | all | 1 | 0–1 | '1' |
| | 3:2 | DdsGain | Gain in sensor's DDS stage. Voltage amplification factor: 00: 3, 01: 1.5, 10: 1, 11: 0.75 | all | 1 | 0–3 | "10" |
| | 5:4 | SensExpTimeMult | Multiplier for exposure time in intensity mode. short exposure time [µs] = (SensExpTimeMult+1) × SensExpTime | 3 | 1 | 0–3 | "00" |
| | 7:6 | SensExpRatio | Ratio between short and long exposure time. "00" 1:2 / "01" 1:4 / "10" 1:8 / "11" 1:16 | 3 | 1 | 0–3 | "00" |

### 2.13  0x25, SensNDarkFrames

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x25 | 8:0 | SensNDarkFrames | Number of dark frames used for offset calculation. SensNDarkFrames ≤ (SensNFrames − 4) | 3 | 1 | 0x7–0xff | 0x0a |

### 2.14  0x26 – 0x27, SensExpTime

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x26, 0x27 | 8:0 | SensExpTime | Exposure time for short exposure image in µs. short exposure time [µs] = (SensExpTimeMult+1) × SensExpTime | all | 1 | 1–0xfff | 0x80 |
| | 15:9 | reserved | | | | | |

### 2.15  0x28 – 0x29, SensCaldur

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x28, 0x29 | 11:0 | SensCaldur | Number of sequencer cycles (2/fs = 28.57ns) for the offset compensation. EffNCal* = SensCaldur + 53 (*effective number of sequencer cycles for the offset calibration) | 0,1,2,4,5,7 | 3 | 0–0xfff | 0x98c |
| | 12:15 | reserved | | | | | |

### 2.16  0x31, AscanProc

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x31 | 3:0 | SigTsh | Signal threshold, up to this level peak considered noise (simpleMax). Used to calc OffsetSens metric in header (# Ascans within ± SigTsh) | 1,2,4,5,7 | 3 | 0–0xf | "0001" |
| | 6:4 | FWHMnFrame | Full Width at Half Max of signal envelope in frames, used to filter the Ascan (smoothing). 000: none, 001: 2 frames, 010: 6 frames, 011: 10 frames, 100: 20 frames. N_fwhm = l_co / (λc × Ncycles) | 2,4,5,7 | 2 | 0–7 | "011" |
| | 7 | Comp11to8 | Enable amplitude compression to 8 Bit. Function defined in Appendix A. | 1,2 | 2 | 0–1 | '0' |

### 2.17  0x32 – 0x35, Bias

Register can be used to let the algorithm's z-value snap to the 2nd frame (when filtering is enabled, else the 1st frame). This results in a defined height for the user. The software could set the confidence of these pixels to very low.

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x32, 0x33 | 9:0 | BiasI | Bias/Signal I-value for the first 2 frames in the volume. | all | 3 | 0–0x3ff | 0x000 |
| | 15:10 | reserved | | | | | |
| 0x34, 0x35 | 9:0 | BiasQ | Bias/Signal Q-value for the first 2 frames in the volume. | all | 3 | 0–0x3ff | 0x000 |
| | 15:10 | reserved | | | | | |

> Take care to set these values bigger than the value in the sigTsh register (AscanProc 0x31). Also note that the values are filtered and the peak value of the calculated amplitude may be strongly reduced — check the filter parameter FWHMnFrame for the right setting.

### 2.18  0x38 – 0x3b, OffsetProc

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x38 | 0 | OffsetMethod | 0: Offset by histogram. 1: Offset by average | 1,2,4,5,7 | 2 | 0–1 | '0' |
| | 1 | UseLastFrame | 0: First frames used in averaging mode. 1: Last frames used in averaging mode | 1,2,4,5,7 | 2 | 0–1 | '0' |
| | 5:2 | NFrmAvg | Number of frames used for averaging: nAvg = 2^NFrmAvg | 1,2,4,5,7 | 2 | 0–0xf | "0011" |
| | 7:6 | HistStrt (1:0) | Start address of histogram — can speed up creation (increase value) (not used yet) | 1,2,4,5,7 | 3 | 0–0x3ff | 0x000 |
| 0x39 | 7:0 | HistStrt (9:2) | | | | | |
| 0x3a | 7:0 | HistEnd (7:0) | End address of histogram — can speed up creation (decrease value) (not used yet) | 1,2,4,5,7 | 3 | 0–0x3ff | 0x3ff |
| 0x3b | 1:0 | HistEnd (9:8) | | | | | |
| | 6:2 | HistPixOut | HistPixOut × 8 = allowed number of pixels outside the margin (±SigTsh) (not used yet) | 1,2,4,5,7 | 3 | 0–0x1f | 0x03 |

### 2.19  0x40, ExSimpMaxHwin

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x40 | 3:0 | ExSimpMaxHwin | Half window size in extended simple max CamMode. Max half window size is 10 (default 5) → window size of 21. WindowSize = 2×ExSimpMaxHwin+1 | 5 | 2 | 0–0xf | 0x5 |

### 2.20  0x41 – 0x42, FirstSurfAtsh

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x41, 0x42 | 13:0 | FirstSurfAtsh | Amplitude threshold value, interpreted as unsigned (10.4) fixed point integer. | 4,7 | 2 | 0–0x3fff | 0x0000 |
| | 15:14 | reserved | | | | | |

### 2.21  0x43, FirstSurfCtrl

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x43 | 7 | EnFirstSurf | 1: Enable first surface detection feature. 0: Disable | 4,7 | 2 | 0–1 | '0' |
| | 6 | EnMaxUnderTsh | Choose whether a normal simple max is done below threshold (=1) or Z/A values for ascans below threshold are set to 0 (A=0,Z=0). Only if EnFirstSurf=1 | 4,7 | 2 | 0–1 | '0' |
| | 5 | EnDiffuseSurf | 1: Surface detected/saved as soon as signal exceeds FirstSurfAtsh. 0: disabled. Only if EnFirstSurf=1 | 4,7 | 2 | 0–1 | '0' |
| | 4 | EnLastSurf | 1: Results of first surface (A,Z) cleared and new maxSearch takes place on the rest of the volume if signal crosses threshold again. 0: disabled. Only if EnFirstSurf=1 | 4,7 | 2 | 0–1 | '0' |
| | 3 | EnDeltaZ | 1: Enable returning difference of two surfaces found in the Ascan. 0: disable. Only if EnFirstSurf=1 | 4,7 | 2 | 0–1 | '0' |
| | 2:0 | reserved | | | | | |

### 2.22  0x46, EnergyLutCtrl

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x46 | 1:0 | LutCtrl | 0→1 starts reading or writing LUT (write to 0x47-0x48 writes into LUT; read reads from LUT). Default length 241 (not used yet) | 7 | 3 | 0–3 | 0x0 |

### 2.23  0x47 – 0x48, EnergyLutData

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x47, 0x48 | 15:0 | EnergyLutData | Data written/read to the energy function LUT. Read/write 0x47 then 0x48 (auto address increment) (not used yet) | 7 | 3 | 0–0xffff | 0x00 |

### 2.24  0x49, UndRelParam

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x49 | 7:0 | UndRelParam | Under relaxation parameter for minimize energy algo u(0.8). Weights the DeltaZ (BestZ−InitZ), used as newZ | 7 | 3 | 0–0xff | 0xc0 |

### 2.25  0x4a – 0x4b, ZRangeStart

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x4a, 0x4b | 11:0 | ZRangeStart | Starting frame for energy function to be applied | all | 3 | 0–0xfff | 0x000 |
| | 15:12 | reserved | | | | | |

### 2.26  0x4c – 0x4d, ZRangeEnd

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x4c, 0x4d | 11:0 | ZRangeEnd | Last frame where energy function is applied. If not set, value from SensNFrames is taken | all | 3 | 0–0xfff | 0x1ff |
| | 15:12 | reserved | | | | | |

### 2.27  0x4e, MinEnergWin

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x4e | 7:0 | MinEnergWin (7:0) | Half size of the window (around the 'mean z' of neighbours) taken into account for the Minimize Energy Algorithm (cam_mode=7). Smaller values may shorten computing time. Must be a multiple of 8. | 7 | 2 | 0–0xff | 0x10 |

### 2.28  0x50, ObsAddr

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x50 | 7:0 | ObsAddr (7:0) | Address to select internal FPGA signals to observe. Debugging feature. | all | 3 | 0–0xff | 0x00 |

### 2.29  0x51, ObsData

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x51 | 7:0 | ObsData (7:0) | Output for observed internal FPGA signals. | all | 3 | - | 0x00 |

### 2.30  0x52, BistNum

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x52 | 7:0 | BistNum | 0x10: Test ZTAG chain (encoder signals generated internally; emulate motor with 100nm encoder driving 5mm/s) | all | 3 | 0x00–0x10 | 0x00 |

### 2.31  0x54 - 0x55, Seg1SensNFrames

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x54, 0x55 | 8:0 | Seg1SensNFrames | Number of frames taken by sensor in Segment 1. Only if SegVolume=1 | all | 2 | 0xa–0x1ff | 0x64 |
| | 15:9 | reserved | | | | | |

### 2.32  0x56 - 0x57, Seg2SensNFrames

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x56, 0x57 | 11:0 | Seg2SensNFrames | Number of frames taken by sensor in segment 2 (no data output). Only if SegVolume=1 | all | 2 | 0xa–0xfff | 0x3e8 |
| | 15:12 | reserved | | | | | |

### 2.33  0x58 - 0x59, Seg2SensMultiple

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x58, 0x59 | 11:0 | Seg2SensMultiple | Multiplication factor of Seg2SensNframes. Only if SegVolume=1 | all | 2 | 0x1–0xfff | 0x01 |
| | 15:12 | reserved | | | | | |

### 2.34  0x5a, IterCtrl

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x5a | 1:0 | IterCtrl | 00: integer and fractional algo disabled. 01: integer enabled, fractional disabled. 11: integer enabled, fractional enabled | 7 | 2 | 0–0x3 | 0x3 |

### 2.35  0x5b, IterMaxInt

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x5b | 7:0 | IterMaxInt | Maximum number of iterations done by the integer algorithm | 7 | 2 | 0–0xff | 0x02 |

### 2.36  0x5c, IterMaxFrac

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x5c | 7:0 | IterMaxFrac | Maximum number of iterations done by the fractional algorithm | 7 | 2 | 0–0xff | 0x02 |

### 2.37  0x60, StatSens

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x60 | 3:0 | SensSens | One bit per sensor quarter gives go/no-go info. 0: Sensor quarter OK (good DCLK, DVAL). 1: bad (DCLK and/or DVAL unexpected) | all | 3 | - | 0x0 |
| | 7:4 | reserved | | | | | |

### 2.38  0x78 – 0x7b, bcd_revision

| Addr | Bit | Name | Description | Cammode | Level | Range | Default |
|---|---|---|---|---|---|---|---|
| 0x78 | 7:0 | VerV (7:0) | FPGA version code, format YYMMDDVV (e.g. 0x12120101 reads "01.12.2012 Version 01") | all | 1 | - | - |
| 0x79 | 7:0 | VerD (15:8) | | all | 1 | - | - |
| 0x7a | 7:0 | VerM (23:16) | | all | 1 | - | - |
| 0x7b | 7:0 | VerY (31:24) | | all | 1 | - | - |

---

## 3. Header

Header words (16-bit) stored at fixed addresses within the measurement buffer:

| Addr | Value | Comments |
|---|---|---|
| 0x3FF–0x3FE | Nvolume | Number of volumes since power on. Counter never cleared (32 Bit) |
| 0x3FD | 0x0000 | |
| 0x3FC | Nframes | Number of frames in volume (16 Bit) |
| 0x3F8 | TimeStamp | Number of system clock cycles since power on. Counter never cleared (64 Bit). Timestamp on Trigger |
| 0x3F4 | ScanDuration | Number of system clock cycles for the acquisition of the volume (64 Bit). Time from Trigger event until the whole volume is written into the first memory. |
| 0x3F3 | | |
| 0x3F2 | FrameDur | Measured frame duration Tf in 70MHz clock cycles |
| 0x3F1 | TempLaser | Laser temperature. Only for MHT. Not used in RTSD! |
| 0x3F0 | TempOptics | Optics temperature. Only for MHT. Not used in RTSD! |
| 0x3EF–0x210 | free space | zeros… |
| 0x20F | ZTagFrm511 | Ztag for frame 511 / last (possible) Ztag (16 Bit counter) |
| … | Ztag space | |
| 0x010 | ZTagFrm0 | Ztag for frame 0 / first Ztag |
| … | zeros | |
| 0x001 | 0xc000 | Header SYNCWORD / First word read |
| 0x000 | 0x0000 | Not read from the FX2!! |

*(16 Bit words)*

---

## Appendix A

### A1. 11To8 compression function

The function is combined by two parts:

```
f(x) =  x                                  { for x = 0..100 }
        156 * (1 - exp(-0.005*(x-100))) + 100    { for x = 101..1023 }
```

*(See the original PDF for the plotted curve: rises linearly to x=100, then approaches a saturating value near 256 as x→1023.)*

### A2. Synchronization signal OUT3

Some applications need to be synchronized with the pixel internal lock-in frequency fd (e.g. to modulate a light source). By setting the *EnSynFOut* register to '1', a rectangular signal on OUT3 is generated.

The frequency of the signal corresponds exactly to the demodulation frequency fd. The signal amplitude A ranges from 0V to 3.3V (4mA max. output current). The period between rising edges is 1/fd.
