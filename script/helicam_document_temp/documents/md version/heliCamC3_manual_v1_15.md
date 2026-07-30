# HELICAM C3 — User's Manual

heliotis AG — heliCam C3 — v1.15

## Revision history

| Revision | Date | Description of evolution |
|---|---|---|
| 1.15 | 31.01.2017 | Updated chapter package contents, added sensor specs for S3.1 |
| 1.14 | 29.06.2016 | Corrected Znew formula in chapter 5.3.3 minimize energy |
| 1.13 | 8.01.2016 | Added information about the minimize energy algorithm and S3.1, formatting |
| 1.12 | 5.11.2015 | Register typos after jv review |
| 1.11 | 26.10.2015 | Phase correction by pi/4, typos |
| 1.10 | 02.04.2015 | Updated chapter 5.4 and added chapter 5.5 |
| 1.9 | 30.03.2015 | Extended chapter 5.3.4 by deltaZ feature |
| 1.8 | 24.02.2015 | Added chapter 5.3.4 First surface, updated introduction |
| 1.7 | 10.10.2014 | Changed chapter 7 software examples |
| 1.6 | 19.09.2014 | Language/typos revision |
| 1.5 | 05.09.2014 | Added ExtTqp on IN4 for deliveries from Q1 2014. Additional smaller changes |
| 1.4 | 22.07.2014 | Updated different parts of the document and added appendix a) + b) |
| 1.3 | 24.07.2013 | Added description of Extended Simple Max Mode |
| 1.2 | 28.06.2013 | Added frame rate considerations for ExtTqp mode in chapter 4.4 ExtTqp |
| 1.1 | 18.06.2013 | SensCaldur calculation adapted, CalDur1Cyc adapted to driver implementation, picture with open connector board removed, typos |
| 1 | 11.01.2013 | Creation of Version 1.0 (beta) |

## Table of Contents

1. Introduction
2. Hardware Installation
   2.1 Package Contents (2.1.1 Basic Cable Option, 2.1.2 Full Lab Cable Kit with heliDriver)
   2.2 The heliCam 3.0 Lock-In Camera (2.2.1 Connector Side, 2.2.2 Mounting Holes and Thermal Requirements, 2.2.3 Lens Cap and Sensor Cleaning)
   2.3 Trigger Cable
   2.4 Interface Cable (2.4.1 Synchronization Signal OUT1, 2.4.2 Inputs for Incremental Encoder Signals IN3/IN4)
3. Software Installation
4. Camera Triggering Modes (4.1 Internal Trigger, 4.2 External Trigger, 4.3 Trigger On Position, 4.4 ExtTqp Trigger, 4.5 Combined Trigger On Position and ExtTqp Trigger)
5. Camera Acquisition Modes (5.1 Measure Raw IQ, 5.2 Measure Amplitude, 5.3 Measure Surface, 5.4 Intensity Mode, 5.5 Segmented Acquisition Feature)
6. Understanding the Most Significant Registers
7. Software Examples
8. Sensor Specification (8.1 heliSens S3.0, 8.2 heliSens S3.1)
9. Appendix (9.1 A, 9.2 B)

---

## 1. Introduction

The heliCam C3 has been designed for real-time 3D imaging applications based on Optical Coherence Tomography (OCT). In this configuration, the sample under test is illuminated by a low-coherence light source. The light reflected from the sample is combined with a reference signal, producing an interferometric signal that is further processed to yield depth information.

Heliotis' approach is based on a proprietary CMOS image sensor where every pixel can acquire and process the optical signals in parallel ("smart pixel" technology). Each pixel features an electronic circuit performing real-time analogue preprocessing. A single sweep of the reference mirror allows a scan through the complete sample, yielding a full 3D tomographic or topographic image.

The camera also offers characteristics useful beyond OCT: each pixel contains a low-power signal demodulation circuit enabling simultaneous detection of envelope and phase information of an optical interferometry signal, or other amplitude-modulated signals where the carrier frequency doesn't exceed 250 kHz. Pixel-level features also include an automatic photocurrent offset-compensation circuit, a synchronous sampling stage, and programmable time averaging.

The massive parallel detection and signal processing enables an internal frame rate of more than one million 2D pictures per second and an external frame rate of up to 3800 full frames per second. The camera supports different acquisition modes for tomographic and topographic applications with flexible parameter adjustment. More than ten processed 3D surfaces per second can be transferred to a host computer, depending on scan range and camera settings.

The heliViewer software configures the camera, manages data transfer, and provides data analysis functions via a GUI — no programming knowledge required. This software is a compiled LabView application. Demo software packages in C/C++, Python and LabView for interfacing the camera are available after driver installation.

This manual covers hardware and software installation, the main camera modes, and technical data useful for application development.

---

## 2. Hardware Installation

### 2.1 Package Contents

The heliCam C3 is delivered with two different sets of accessories.

#### 2.1.1 Basic Cable Option
1. HeliCam C3 lock-in camera
2. 2m USB 2.0 cable
3. Standard 1m connection cable (see Appendix A for pinning)

#### 2.1.2 Full Lab Cable Kit with heliDriver
1. HeliCam C3 lock-in camera
2. heliDriver (connection module, with integrated signal conditioning)
3. Lab cable kit: 0.5m supply cable with banana plugs for lab supply, 1m extTqp cable, 2m trigger cable, 2m camera cable, 2m USB cable

### 2.2 The heliCam 3.0 Lock-In Camera

#### 2.2.1 Connector Side

The connector side has a 12Pin Power Supply/Trigger/I-O connector and a USB Type B receptacle. Four holes in the center allow viewing the Status LEDs inside the camera on the connector board.

Status LEDs D1–D4:

| D1 | D2 | D3 | D4 |
|---|---|---|---|
| Volume trigger (low active) | Acquisition time out | Sensor busy signal | Ready signal |

#### 2.2.2 Mounting Holes and Thermal Requirements

The camera can be mounted via 7× M6 mounting holes, 4× M4 mounting holes, and 2× positioning holes. *Deliveries from Q1 2014 have a slightly different housing — see Appendix B for details.*

The M6 holes were originally designed for mounting on an optical table. It's recommended to mount the camera on a base with good thermal conduction, or use a small fan (forced airflow), keeping housing temperature below 40°C. Under controlled room temperature (20°C) with good convection, an additional heat sink may not be necessary.

#### 2.2.3 Lens Cap and Sensor Cleaning

The camera ships with a lens cap; there's no additional protective glass on the sensor. Take care when removing the lens cap. The optical active area is cleaned before shipping; if the sensor needs cleaning, use a Q-tip and a 50-50 mixture of distilled water and isopropyl alcohol.

> **Take care not to harm the open bond wires! To be on the safe side, clean the pixel array only.**

### 2.3 Trigger Cable

> *Attention: Only deliveries before Q1 2014 have a distinct trigger cable with a BNC connector. Check Appendix A for the actual cable and placement of the trigger input.*

The trigger cable (coax) has a BNC connector, used as an input. If the correct trigger mode is configured (see 4.2 External Trigger or 4.4 ExtTqp), this input triggers the camera to acquire a volume (a given number of frames).

The inner wire of the BNC cable connects to Pin 9 of the camera connector; the shield connects to GND (Pin 10). A 1KΩ pull-up resistor to 3.3V is integrated in the camera.

Ideal external trigger signal characteristics:
- An open collector circuit shortens the input to GND. The falling edge of the trigger pulse defines the start of the measurement.
- Signal width: > 10 µs.

### 2.4 Interface Cable

> *Attention: Only deliveries before Q1 2014 have a distinct interface cable. Check Appendix A for the actual cable and placement of the IOs.*

The interface cable is not used in every application; only in a few applications are all signals used. The cable comes without any pre-assembled connector.

Bare interface cable pinout (12Pin Hirose connector):

| Wire | Color | Direction | Function | Pin # Hirose connector |
|---|---|---|---|---|
| w1 | brown | OUT1 | Synch. | 6 |
| w2 | grey | IN1 | * | 7 |
| w3 | white | IN2 | * | 8 |
| w4 | green | IN3 | Encoder phiA / EXTTQP Trg | 11 |
| w5 | yellow | IN4 | Encoder phiB | 12 |
| w6 | shield | - | Connected to GND | 10 |

\* reserved. Pin 10 and Pin 2 of the 12Pin Hirose connector are connected to camera's GND.

**I/O circuit inside the camera:** IN1–IN4 each have pull-up resistors (1K for IN1/IN2, 100R for IN3/IN4) to +3.3VDC, feeding into an I/O buffer that interfaces to the FPGA (inputs to FPGA, OUT1 output from FPGA).

Electrical signal specification of OUT1: CMOS 3.3V, 4mA max.

> *For deliveries from Q1 2014, as well as deliveries with the heliDriver, the camera IOs are opto-coupled:* PIN3, PIN4, PIN9, PIN8, PIN12 (switchable input/output via SW), PIN5, PIN6, PIN7 connect through a high-speed opto-coupler (ACSL-6400, channels A1–A4/C1–4) to the FPGA, and three PS2911 opto-couplers drive FPGA out1/out2/out3.

Pin 12 can be configured as input or output via the switch (SW). PIN 8 must be connected to "userGND" and Pin 7 to "userVDD" if any camera outputs are used. Camera inputs can be used at voltages from 4.5V to 6V. Input current for the internal opto-couplers must be between 8mA and 15mA. Maximum input voltage on "userVDD" is 36VDC; maximum output current is 5mA.

#### 2.4.1 Synchronization Signal OUT1

If the correct trigger mode is configured (4.1 Internal Trigger, 4.2 External Trigger, 4.3 Trigger On Position), a synchronization signal is available on OUT1 — useful for synchronizing with the pixel-internal lock-in frequency fd (e.g. to modulate a light source). This is a rectangular signal at the electrical specs above; its frequency exactly matches the configured demodulation frequency fd (period 1/fd).

#### 2.4.2 Inputs for Incremental Encoder Signals IN3/IN4

IN3 and IN4 are inputs for quadrature encoder signals, e.g. to track the exact position of a linear axis. Signals are processed by an internal quadrature decoder and a 32-bit position counter. The least significant 16 bits of the position counter are saved for every frame and returned in the header of the volume data (see Register Description, chapter 3 Header).

Typical quadrature encoder signals: PhiA and PhiB, 90° out of phase, giving a quadrature-decoded count that increments through states 0,1,2,3,4,5,6,7… per encoder resolution step.

If the correct trigger mode is configured (4.4 ExtTqp Trigger), IN3 is additionally used to trigger the quarter-period in-pixel integration, synchronizing the sensor's demodulation process with the movement of the stage. IN3/PhiA (deliveries from Q3 2014: IN4/PhiB) generates pulses inside the camera used to trigger the integration process — a pulse is generated on both the rising and falling edge of IN3/PhiA (deliveries from Q3 2014: IN4/PhiB).

*For deliveries from Q3 2014, pulses can be generated on both channels by setting the register "AcqCtrl.ExtTqpPuls" (Addr 0x03, bit 7) to 1 — see register description file.*

---

## 3. Software Installation

Follow the instructions in the `ReadMe.txt` file supplied with the software package.

---

## 4. Camera Triggering Modes

There are several ways to trigger the camera to start a measurement. Some triggering features exclude certain modes or have other implications.

Overview of trigger modes and register settings:

| Mode | TrigFreeExtN | ExtTqp | EnTrigOnPos | ClrPosCnt | TrgDown | MskTrgOnPos | TrigOnPos | BNC Trigger input | Interface cable | Intensity Mode |
|---|---|---|---|---|---|---|---|---|---|---|
| 1) Internal Trigger | = 1 | – | – | – | – | – | – | – | not used | available |
| 2) External Trigger | = 0 | = 0 | = 0 | – | – | – | – | used | not used | available |
| 3) Trigger On Position | = 0 | = 0 | = 1 | ● | ● | ● | ● | optional | used | available |
| 4) ExtTQP Trigger | = 0 | = 1 | = 0 | – | – | – | – | used | used | not available |
| 5) Trigger On Position + ExtTqp Trigger | = 0 | = 1 | = 1 | ● | ● | ● | ● | optional | used | not available |

(● = fully usable, set by the user's application; "–" = don't care)

### 4.1 Internal Trigger

**Must-have register setting:** `TrigFreeExtN = 1`

**Optional registers:** `EnSynFOut`: [0 or 1], synchronization signal on OUT1

Most applications don't use internal trigger mode in their final configuration, but it's recommended for getting started with the HeliCam and aligning the optical setup. In this mode, the camera starts capturing frames automatically and saves them in RAM. The user's program, heliCam Viewer, or a sample program can always acquire data.

### 4.2 External Trigger

**Must-have register settings:** `TrigFreeExtN = 0`, `ExtTqp = 0`, `EnTrigOnPos = 0`

**Optional registers:** `EnSynFOut`: [0 or 1]

**Must-have connections:** Trigger cable

Most applications use this setting. The camera starts capturing frames on a pulse of the external trigger input (see 2.3 Trigger Cable for electrical specs).

### 4.3 Trigger On Position

**Must-have register settings:** `TrigFreeExtN = 0`, `ExtTqp = 0`, `EnTrigOnPos = 1`, `TrigOnPos`: [0 to 2³²−1] (desired trigger position), `TrgDown`: [0 or 1]

**Optional registers:** `ClrPosCnt`: [0 or 1] (clears position counter if set to 1), `MskTrgOnPos`: [0 or 1] (masks the clear-by-external-trigger feature), `EnSynFOut`: [0 or 1]

**Must-have connections:** Encoder inputs of the interface cable (IN3/IN4) connected to a digital incremental encoder stage (see 2.4.2).

The value of the in-camera position counter is compared with the 32-bit register `TrigOnPos`. With `TrgDown=0`, the trigger fires when passing `TrigOnPos` from smaller to bigger values; with `TrgDown=1`, vice versa.

The position counter can be zeroed via `ClrPosCnt=1` then `=0` (holding `ClrPosCnt=1` holds the counter at 0). The counter is also cleared when a trigger signal is generated on the trigger input (2.3) — disable this via `MskTrgOnPos=1` (e.g. if the trigger input is connected to a linear scale's reference index, to prevent unwanted resetting).

The least significant 16 bits of the position counter are saved for every captured frame and returned in the header of the volume data (Register Description, chapter 3 Header).

### 4.4 ExtTqp Trigger

**Must-have register settings:** `TrigFreeExtN = 0`, `ExtTqp = 1`, `EnTrigOnPos = 0`

**Must-have connections:** At least PhiA (IN3) (deliveries from Q3 2014: IN4/PhiB) from the encoder inputs (2.4.2); Trigger cable.

Some applications synchronize the in-pixel demodulation process to the modulation of the light (e.g. given by the scanner passing the coherence plane in an interferometer setup) rather than the reverse. In ExtTqp mode, IN3 (deliveries from Q3 2014: IN4) defines the start of the sensor's integration process; the start of the measurement is given by a pulse on the trigger input (4.2). Pulses generated by toggling IN3/IN4 (2.4.2) start the integration of quarter periods (TQP = time quarter period) on the sensor — four samples per cycle to run the in-pixel demodulation process.

The "normal" (untriggered) mode samples an equidistant sine wave; the sampling interval is set by register `SensTqp`:

```
ΔT = 2 × (SensTqp + 30) / fs      (sensor frequency fs = 70MHz)
fd = 1 / (4 × ΔT)                  (lock-in demodulation frequency)
```

For a linear axis with non-constant velocity (frequency-modulated sine wave), equidistant sampling would corrupt the measurement. In ExtTqp mode the user fully controls sampling time via a rectangular signal on IN3/IN4; samples are generated on rising and falling edges.

`SensTqp` defines the integration duration of one sample. Constraint:

```
(SensTqp + 11) × 1/35MHz  <  T_pulsewidth
```
where T_pulsewidth is the pulse width of the rectangular signal on IN3.

**Theoretical maximum for SensTqp** (with encoder signals, 2.4.2):
```
(SensTqp + 11) × 1/35MHz  <  2 × EncRes / vmax
```
where EncRes = encoder resolution [mm], vmax = maximum scanner velocity during measurement [mm/s].

**Maximum frame rate** (with encoder signals): the system must satisfy
```
MaxFramerate > vavg / (8 × EncRes × (2×SensNavM2 + 3))     [BSEnable=1, CalDur1Cyc=1]
MaxFramerate > vavg / (16 × EncRes × (SensNavM2 + 1))      [BSEnable=0]
```
where vavg = average scale speed during a frame. The camera's maximum frame rate is 3800 fr/s (see chapter 8).

### 4.5 Combined Trigger On Position and ExtTqp Trigger

**Must-have register settings:** `TrigFreeExtN = 0`, `ExtTqp = 1`, `EnTrigOnPos = 1`, `TrigOnPos`: [0 to 2³²−1], `TrgDown`: [0 or 1]

**Optional registers:** `ClrPosCnt`: [0 or 1], `MskTrgOnPos`: [0 or 1]

**Must-have connections:** At least PhiA (IN3) (deliveries from Q3 2014: IN4/PhiB) with electrical specs per 2.4.2; Trigger cable.

The modes described in 4.3 and 4.4 can be combined.

---

## 5. Camera Acquisition Modes

### 5.1 Measure Raw IQ

**Must-have register setting:** `CamMode = 0`

The camera detects the modulated part of the light in every pixel. At pixel level, the incoming modulated light signal is multiplied by a sine and cosine from a fixed-frequency local oscillator (LO) at demodulation frequency fd, and integrated over Nc cycles (low-pass over a given number of cycles), yielding In-phase (I) and Quadrature (Q) values. This is repeated Nfr times (Nfr = number of frames).

**Raw IQ:** `raw_I` and `raw_Q` values are returned, ranging 0–1023 (10-bit, unsigned u10.0). A non-modulated signal corresponds to a value around 512, not 0. `offset_I`/`offset_Q` should be measured per-pixel and subtracted:

```
I = raw_I - offset_I     Q = raw_Q - offset_Q
Amplitude = sqrt(I² + Q²)
Phase = atan2(I, Q) - π/4
```

Strategies to determine `offset_I`/`offset_Q`:
- Average a few frames known to have no modulated signal (implemented as register `OffsetMethod=1`).
- Use a slightly different modulation frequency for the light vs. the lock-in camera; I and Q oscillate progressively between min/max frame-to-frame (sine/cosine), and half the peak-peak value gives the offset.
- When no modulated signal is present most of the time, take the most frequent value from a per-pixel histogram (implemented as `OffsetMethod=0`).

### 5.2 Measure Amplitude

#### 5.2.1 Amplitude

**Must-have register setting:** `CamMode = 1`
**Optional registers:** `OffsetMethod = [0 or 1]`, default '0'

The offset_I/offset_Q calculation is done directly in-camera; the algorithm (histogram- or average-based) is user-selectable via `OffsetMethod`. The returned 16-bit value is the amplitude, interpreted as u12.4 (unsigned fixed-point, 12 bits integer, 4 bits fractional). Phase information is not transferred.

#### 5.2.2 Smoothed Amplitude

**Must-have register setting:** `CamMode = 2`
**Optional registers:** `FWHMnFrame`

Provides a filtered signal, i.e. a "matched-filter" configuration where the signal envelope shape corresponds to the filter's impulse response, maximizing SNR. Filter length set via `FWHMnFrame`. Returned amplitude format is also u12.4.

#### 5.2.3 Compressed Amplitude

**Must-have register setting:** `CamMode = [1 or 2]`, `Comp11to8=1`

In both Amplitude and Smoothed Amplitude modes, values can be compressed to 8-bit to reduce data volume and transfer time. Set `Comp11to8=1`; the returned format becomes u8.0. Compression function:

```
f(x) = x                                    for x = {0..100}
f(x) = 156×(1 - e^(0.5 - 0.005x)) + 100      for x = {101..1023}
```

*(Curve rises linearly to x=100, then saturates smoothly toward ~256 as x→1023.)*

### 5.3 Measure Surface

Since the data volume in rawIQ and amplitude modes is large, the interface to the host computer is a limiting factor. The camera can calculate and transmit a surface extracted from the volume. The algorithm was originally developed for OCT topology measurements — opaque surfaces returning one interference fringe per A-scan in a white-light interferometer setup — and works well for volumes/signals with a single envelope. If the signal has multiple envelopes, the algorithm snaps to the one with the strongest amplitude (not necessarily correct).

#### 5.3.1 Simple Max

**Must-have register setting:** `CamMode = 4`
**Optional registers:** `FWHMnFrame`

The maximum signal strength S and corresponding Z (position/frame number) are saved per pixel. Example: S=100 found at frame 250 → Z=250, S=100.

In the surface modes SimpleMax and MinEnergy, only S and Z per pixel are transferred: S in u12.4 (16-bit), Z in u11.5 (16-bit) — 32 bits/pixel total. The compression factor scales with the number of frames per volume (e.g. rawIQ with 400 frames → compression factor 250). With `SensNFrames` (Nfr) set to 100, ~20 3D-images/second can be acquired.

#### 5.3.2 Extended Simple Max

**Must-have register setting:** `CamMode = 5`, `ExSimpMaxHwin`
**Optional registers:** `FWHMnFrame`, `SigTsh` (values below considered noise)

In addition to the SimpleMax data (16-bit Amplitude Smax, 16-bit FrameNumber Zmax), the camera transmits a user-defined number of additional Amplitude (A) and Phase (φ) values around the maximum. The half-window size is set via `ExSimpMaxHwin` (legal values 1–10), giving a minimum of 9 (3×3) and maximum of 63 (3×21) values per pixel.

Data formats:

| Value | Format |
|---|---|
| Surface Z | Unsigned (11.5) |
| Amplitude S | Unsigned (12.4) |
| Phase Phi | Unsigned (3.13) |

Benefits: (a) a fast acquisition mode, (b) enough data to implement custom fitting algorithms (using the additional Amplitude S and/or phase values) to find the true maxima of the envelope.

#### 5.3.3 Minimize Energy

**Must-have register setting:** `CamMode = 7`
**Optional registers:** `FWHMnFrame`, `IterCtrl`, `IterMaxInt`, `IterMaxFrac`, `MinEnergWin`, `UnderRelParam`

Two options: normal **IntegerMode** (`IterCtrl=1`) and **FractionalMode** (`IterCtrl=2`). FractionalMode gives sub-frame resolution by fitting a parabola through the three points around the maximum in Z, applied after minimize energy — slightly slower than IntegerMode.

Minimize Energy is based on Simple Max: S and Z are calculated first per pixel. The algorithm finds a Z value that best fits the neighboring Z values (minimizing energy). For a pixel 'a' with neighbors 1,2,3,4 (and a second neighbor set 3,5,6,7 for pixel 'b'), the ΔZ from pixel 'a' and the weighted average of the neighboring Z_nb are input to a quality function that returns the best Z:

```
Zbest = max( Ascan[n] × exp( -0.5 × ((Z[n] - Znb)/σ)² ),  n in ± MinEnergWin )
```

The quality function picks the maximum value inside the window 2×`MinEnergWin` (register 0x4e) centered on Znb, described by a limited Gaussian bell curve with weighted average Znb as expectation value. Implemented in the FPGA as a pre-calculated LUT with σ=20, 241 values, maximum at LUT index x=120.

**Under Relaxation parameter `UndRelParam`:** After finding Zbest via the quality function, the distance between Zbest and the Z from the last iteration (Zlast) is weighted by `UndRelParam`:

```
Znew = Zlast + (Zbest - Zlast) × UndRelParam
```

`UndRelParam` is a U0.8 register, default 0.75 (see register description file).

**Sub-frame resolution by parabola fit:** Updating pixel "a" may significantly change the average of neighboring Z_nb values used when calculating other pixels, so the process is iterative — max iterations set via `IterMaxInt` and `IterMaxFrac`. The maximum of the envelope (or fitted parabola) lies between the frame X with maximum signal strength S and frame X+1; the peak of the fitted parabola gives sub-frame resolution. Since 16-bit Z-values are interpreted as U11.5, a sub-frame resolution of 2⁻⁵ is achieved.

#### 5.3.4 First Surface

**Must-have register setting:** `CamMode = 4` or `CamMode = 7`, `EnFirstSurf=1`, `FirstSurfAtsh`
**Optional registers:** `EnMaxUnderTsh`, `EnDiffuseSurf`, `EnLastSurf`, `EnDeltaZ`, and other registers used for commode 4/7.

Some transparent/semitransparent samples return more than one surface — the interferometer returns multiple fringe patterns for one volume, i.e. a true tomographic signal (e.g. "first surface" at Z=86, A=96, and "second surface" at Z=308, A=102, with DeltaZ between them).

If `EnFirstSurf=0`, the surface algorithms (commode 4 and 7) find/snap to the "second surface". Setting `EnFirstSurf=1` with an appropriate `FirstSurfAtsh` makes the algorithm snap to the "First surface" instead.

The threshold `FirstSurfAtsh` is set in unsigned 10.4 format. E.g. for a threshold value of 10: `FirstSurfAtsh = 10×16 = 160`.

- **`EnMaxUnderTsh`**: If 1, enables maximum-peak search even for pixels where the signal is below `FirstSurfAtsh`. If 0, A and Z for such pixels are set to zero.
- **`EnDiffuseSurf`**: If 1, saves A/Z as soon as the signal crosses the `FirstSurfAtsh` threshold (useful for semi-transparent surfaces returning signal over a wide frame range where peak search can't take place). If 0, feature disabled.
- **`EnLastSurf`**: If 1, starts a new maximum search after every below→above threshold crossing (a transition is required) — in a multi-surface sample, the last surface in the volume is picked; also useful if scan direction is inverted but the user still wants the "first surface". If 0, feature disabled.
- **`EnDeltaZ`**: If 1, returns the height difference in Z (frames) between two surfaces: `Zxy = Z2 - Z1`. The returned signal S corresponds to the surface with the lower amplitude: `Sxy = min(S1, S2)`.

Surface detection is governed by `FirstSurfAtsh`.

### 5.4 Intensity Mode

**Must-have register setting:** `CamMode = 3`, `SensNFrames`, `SensExpTime`, `BSEnable = 0`
**Optional registers:** `SensNDarkFrames`, `SensExpTimeMult`, `SensExpRatio`, `TrigFreeExtN`

In intensity mode the HeliCam works like a standard 2D camera — useful for aligning a light beam or imaging an object like a consumer camera. The sensor's control electronics are modified so that non-demodulated (usual integrated) signals are generated on channels I and Q. The sensor returns two images with different exposure times.

```
short exposure time [µs] = SensExpTime × (SensExpTimeMult + 1)
```

`SensExpRatio` (2-bit register) sets the ratio between short and long exposure:

| SensExpRatio | Ratio (short:long) |
|---|---|
| 0 | 1:2 |
| 1 | 1:4 |
| 2 | 1:8 |
| 3 | 1:16 |

Offset compensation is done by the SDK: the sensor returns a defined number of "dark" (unexposed) images, and the SDK subtracts the offset automatically. `SensNDarkFrames` must be ≥ 7 (increase to improve offset calculation on the host).

`SensNFrames` sets the total number of measured images. The SDK returns the following number of HDR (high dynamic range) images:

```
SensNFrames - SensNDarkFrames - 3
```

Constraint: `SensNDarkFrames ≤ SensNFrames - 4`.

For the first image, the SDK also returns the short and long exposure images separately.

### 5.5 Segmented Acquisition Feature

**Must-have register setting:** `SegVolume = 1`, `Seg1SensNFrames`, `Seg2SensNFrames`
**Optional registers:** `Seg2SensMultiple`

Some applications need larger scan ranges where some region between interesting segments isn't relevant (e.g. measuring pin length h on a package, where the gap P between pin tops and the package surface holds no useful information).

The user configures the camera to deliver data in Segment 1 and Segment 3, while Segment 2 contains no data — handling less data while retaining full z-resolution in Segments 1 and 3.

The feature is available in all camera modes via `SegVolume=1` (register 0x02, bit 2). Total active frames is still given by `SensNFrames`. Frames in Segment 1 = `Seg1SensNFrames` (must be smaller than `SensNFrames`); frames in Segment 3 = `SensNFrames - Seg1SensNFrames`. Frames in Segment 2 = `Seg2SensNFrames × Seg2SensMultiple`.

Both registers (`Seg2SensNFrames`, `Seg2SensMultiple`) are 12-bit wide, so the complete scan range can extend to a maximum of:

```
2^12 × 2^12 = 2^24  →  ≈ 16 million frames
```

---

## 6. Understanding the Most Significant Registers

- **`SensNFrames`**: Number of frames Nfr (300×300 pixel images) to be acquired. Maximum 512.
- **`SensTqp`**: Determines the Lock-In camera's reference frequency. For demodulation frequency fd: `SensTqp = 70MHz/(8×fd) - 30`. E.g. fd=10KHz → SensTqp=845.
- **`CalDur1Cyc`**: If 1, offset compensation time Toffset is exactly 1 cycle. If 0, define `SensCaldur` (1–4096); `Toffset = (SensCaldur + 58)/35MHz`.
- **`SensNavM2`**: Number of averaging/demodulating cycles per frame: `Nc = SensNavM2×2+2`. If `BSEnable=1`, Toffset is also used for pixel offset compensation before taking a frame; if `CalDur1Cyc=1`, Toffset equals one cycle's time. Time between two successive frames: `Tfr = (Nc/fd) + Toffset`. E.g. fd=9KHz, SensNavM2=3 → Tfr=1ms (with BSEnable=1, CalDur1Cyc=1) → 1000 frames/s. Don't exceed 3800 frames/s.
- **`DdsGain`**: Analogue signal gain in the sensor. Best SNR achieved with `DdsGain=2`.

| DdsGain | Effective gain |
|---|---|
| 0 | 3 |
| 1 | 1.5 |
| 2 | 1 |
| 3 | 0.75 |

- **`BSEnable`**: In-pixel background suppression on if `BSEnable=1`, compensating the in-pixel DC part of light.

---

## 7. Software Examples

After installing the full SDK, example programs in C/C++, LabView, and Python are available. See the following documentation folders for details:

- C/C++: `C:\Program Files\Heliotis\heliCam\Cpp\documents`
- LabView: `C:\Program Files\Heliotis\heliCam\LabView\documents`
- Python: `C:\Program Files\Heliotis\heliCam\Python\documents`

---

## 8. Sensor Specification

The heliCam C3 and other heliotis products (H6, H4, P4) are delivered with one of the following sensors.

### 8.1 heliSens S3.0

| Parameter | Value |
|---|---|
| Die Size | 19.71 mm × 16.89 mm |
| Number of Columns | 300 (centre 280 usable; 2×10 columns are test columns) |
| Number of Rows | 300 (centre 292 usable; 2×4 rows are test rows) |
| Total number of pixels | 90,000 |
| Column Pitch ΔXpixel | 39.6 µm |
| Row Pitch ΔYpixel | 39.6 µm |
| Photodiode dim. X ΔXphotodiode | 22.2 µm |
| Photodiode dim. Y ΔYphotodiode | 12.7 µm |
| Photodiode area | 282 µm² |
| Optical fill factor | 18.0% (without micro-lenses) |
| Pixel Field Width | 11.9 mm |
| Pixel Field Height | 11.9 mm |
| Max. External Frame Rate (current firmware) | 3800 fps |
| Max. Demodulation Frequency | 250 kHz (internal rate of 1M frames/s) |
| Min. Demodulation Frequency | 2137 Hz |
| Output Resolution | 10 bit |

### 8.2 heliSens S3.1

| Parameter | Value |
|---|---|
| Die Size | 19.71 mm × 16.89 mm |
| Number of Columns | 300 (centre 280 usable; 2×10 columns are test columns) |
| Number of Rows | 300 (centre 292 usable; 2×4 rows are test rows) |
| Total number of pixels | 90,000 |
| Column Pitch ΔXpixel | 39.6 µm |
| Row Pitch ΔYpixel | 39.6 µm |
| Photodiode dim. X ΔXphotodiode | 11.2 µm |
| Photodiode dim. Y ΔYphotodiode | 11.2 µm |
| Photodiode area | 125.4 µm² |
| Optical fill factor | 8% (without micro-lenses) |
| Pixel Field Width | 11.9 mm |
| Pixel Field Height | 11.9 mm |
| Max. External Frame Rate (current firmware) | 3800 fps |
| Max. Demodulation Frequency | 250 kHz (internal rate of 1M frames/s) |
| Min. Demodulation Frequency | 2137 Hz (with internal demodulation) |
| Output Resolution | 10 bit |
| Responsivity (@ gain=1.5) | 0.92 DU/µJ/m² (green), 0.1 DU/µJ/m² (red) |
| Responsivity to DC in demodulation mode (@ gain=1.5) | 0.16 DU/mJ/m² |
| Quantum efficiency | 20–90% (@350–450nm), >90% (@450–750nm), 90–20% (@750–950nm) |

---

## 9. Appendix

### 9.1 A)

Deliveries from Q1 2014 include a standard 12Pin 1m connection:

| Pin # | Wire colour | Description |
|---|---|---|
| 1 | Red | VDD |
| 2 | Blue | GND |
| 3 | Pink | A |
| 4 | Grey | B |
| 5 | Yellow | OutEnDrv |
| 6 | Green | OutFSync |
| 7 | Brown | UserVDD |
| 8 | White | UserGnd |
| 9 | Black | Trigger |
| 10 | Red/Blue | Driver current I_plus |
| 11 | Pink/Grey | Driver current I_minus |
| 12 | Violet | IOA |
| — | Orange | Shield |

### 9.2 B)

Deliveries from Q1 2014 have a different housing with the following mounting holes *(see original PDF, p.33, for the dimensioned drawing)*:

- Top face: 4× Ø3.30 ⊥11.50, M4×0.7-6H ⊥8 mounting holes at dimensions 79, 70.70, 45, 40 (horizontal) / 37.50, 22.50, 7.50 (vertical), plus Ø2.50 ⊥4 alignment holes.
- Side face: 2× per side Ø5 ⊥9, M6×1.0-6H ⊥7 mounting holes at 70.70 / 45.70 (horizontal) / 10 (vertical). Overall length 158.70 mm, height 30 mm.
