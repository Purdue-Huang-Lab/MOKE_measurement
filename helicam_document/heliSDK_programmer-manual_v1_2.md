# heliSDK 1.x — Programmer's Manual

Document Number: UM.SDK.0001.EN
Release Version: 1.2
Release Date: 03.05.2016

## How to contact Heliotis

**Americas / Europe / Asia Pacific:**
Heliotis AG — Längenbold 5, CH 6037 Root (Luzerne), Switzerland
voice +41-41-455-6700, fax +41-41-455-6701, support@heliotis.ch, www.heliotis.ch

**Japan:** LinX Corporation, 1-13-11 eda-nishi Aoba-ku, Yokohama 225-0014, Japan
voice +81-45-979-0731, fax +81-45-979-0732, info@linx.jp, www.linx.jp

**Korea:** IOVIS, 1305 Hyundai Knowledge Industrial Center C-dong, 7, Seoul, Korea 05836
voice +82-2-424-8832, fax +82-2-6455-8832, sales@iovis.co.kr, www.iovis.co.kr

---

## Preface

### About this document
This document supports installation and usage of the heliSDK to build a software application based on the libHeLIC library. It covers the most important information for each supported programming language.

Check www.heliotis.ch for updates to this document and related software components.

### Related documentation
- **heliCam™ C3 User's Manual** — background on the sensing technology of the heliInspect™ and heliCam™ products, and the meaning/relationships of all register parameters used to configure the available acquisition modes.
- **heliInspect™ H6 User's Manual** — installation, configuration and operation of the heliInspect™ H6 measurement head and the LINAX/XENAX standard scanner.
- **Register description file** — description of all registers settable in the heliCam C3.
- **Programmer's Manual XENAX** — advanced programming features, interface options, optimization, and troubleshooting for the XENAX servo controller.

### Conventions
`>IMPORTANT<`, `>WARNING<`, `>HINT<` callouts are used throughout.

All rights reserved, particularly regarding registration of patents and proprietary designs. The company reserves the right to alter specification, design, price or conditions of supply without notice.

HALCON is a trademark of MVTec Software GmbH. MATLAB is a registered trademark of The Math Works, Inc. LABVIEW is a registered trademark of National Instruments, Inc. Windows is a registered trademark of Microsoft, Inc.

---

## Chapter I. Installation

The heliSDK is available for 32 and 64bit Windows operating systems since Windows XP. Latest version: www.heliotis.ch

By default, setup installs all language interfaces. For normal use and flexibility, the default (full) installation is recommended.

Default installation path: `C:\Program Files\Heliotis\heliCam\` (64bit) or `C:\Program Files (x86)\Heliotis\heliCam\` (32bit). All Heliotis documentation paths are based on this location.

After SDK installation, with the heliCam connected and powered, the Windows Device Manager shows **heliCam C3** under "libusb-win32 devices". If not, something went wrong with the installation or the camera connection is broken.

### a. Locations

Folder structure under the install path:

| Folder/File | Contents |
|---|---|
| `.\Cpp` | C++ examples (if C++ selected during install) |
| `.\documents` | All documentation, including this file |
| `.\Halcon` | HALCON files (if selected); updates also available from MVTec |
| `.\LabView` | LabView library and examples (if selected) |
| `.\libHeLIC` | The API library. Documentation at `.\documents\heliCamAPI.chm` |
| `.\Python` | Python wrapper and examples (if selected) |
| `.\sys` | Windows driver files for the heliCam C3 |
| `.\libHeLICTester.exe` | Small test program to check connectivity/functionality |
| `.\Uninstall.exe` | Uninstalls the heliSDK and all files |

Important files are linked to the Windows Start Menu under **All Programs → Heliotis → heliSDK** (or heliSDK64).

If something is missing, rerun the heliSDK installation and select the needed components.

> **HINT**: Before starting a new installation, close all applications using the heliSDK interface, including documentation viewers.

---

## Chapter II. C++

The base API of the heliCam is written in C++. A detailed doxygen API doc is at `.\documents\heliCamAPI.chm` (linked to Start Menu).

### a. Setup new Visual Studio project

1. Create new project: *File → New Project*
2. Choose "Win32 Project"
3. Create a project with "Precompiled header"
4. Configure project settings: *Project → Properties*

**x86 platform:**

*Configuration Properties → C/C++ → General* — Add to "Additional Include Directories":
```
C:\Program Files (x86)\Heliotis\heliCam\libHeLIC
C:\Program Files (x86)\Heliotis\heliCam\Cpp\heliCam
C:\Program Files (x86)\Heliotis\heliCam\Cpp\axis
$(ProjectDir)
```

*Configuration Properties → Linker → General* — Add to "Additional Library Directories":
```
C:\Program Files (x86)\Heliotis\heliCam\libHeLIC
```

*Configuration Properties → Linker → Input* — Add to "Additional Dependencies": `libHeLIC.lib`

**x64 platform:**

*Configuration Properties → C/C++ → General* — Add to "Additional Include Directories":
```
C:\Program Files\Heliotis\heliCam\libHeLIC
C:\Program Files\Heliotis\heliCam\Cpp\heliCam
C:\Program Files\Heliotis\heliCam\Cpp\axis
$(ProjectDir)
```

*Configuration Properties → Linker → General* — Add to "Additional Library Directories":
```
C:\Program Files\Heliotis\heliCam\libHeLIC
```

*Configuration Properties → Linker → Input* — Add to "Additional Dependencies": `libHeLIC.lib`

5. Add the HeliCam class to your project: *Project → Add Existing Item…* → choose `heliCamC3.h` and `heliCamC3.cpp` from `...\Cpp\heliCam\`

   Add the axis class (e.g. Jenny axis): *Project → Add Existing Item…* → choose `Xenax.h` and `Xenax.cpp` from `...\Cpp\axis\`

6. Include the header files:
```cpp
#include "heliCamC3.h"
#include "Xenax.h"
```

7. Use the heliCam and enjoy. A good starting point is the example projects.

### b. Functions

All API functions are documented in the doxygen documentation (`heliCamAPI.chm`, linked from the Start Menu). A flowchart of typical function usage is in the Appendix.

The basic application flow can be found in the example projects.

### c. Data format

The data format changes depending on the camera mode used — different allocation types apply for different modes. See the doxygen docs for `HE_AllocCamData` and the `format` parameter of type `CamDataFmt`.

#### CamMode = 4, CamMode = 7

Uses `CamDataFmt = DF_A16Z16`. After `HE_ProcessCamData`, `HE_GetCamData` returns a pointer to the result, laid out as an amplitude (A) and surface/z (Z) value pair per pixel, for a `y size × x size` grid (typically 293 × 281), i.e. interleaved `A_{y,x}, Z_{y,x}` pairs row by row.

```cpp
cd = HE_ProcessCamData(currInst->heHdl, 1, 0, 0);
cd = HE_GetCamData(currInst->heHdl, 1, 0, metadata);
ushort* camData = (ushort*)cd->data;

uint ySize = metadata->dimSz[2]; // y - 293
uint xSize = metadata->dimSz[1]; // x - 281
uint arraySize = metadata->dimSz[0]; // z or a - 2

const ULONG zStrideRead = 1;
const ULONG yStrideRead = arraySize * xSize;
const ULONG xStrideRead = arraySize;

float imgFixedPoint;

for (uint arrayId = 0; arrayId < (arraySize); arrayId++) {
  for (uint y = 0; y < (ySize); y++) {
    for (uint x = 0; x < (xSize); x++) {
      if (arrayId == 0) {
        // aValue
        aScaledData[y][x] = camData[arrayId * zStrideRead + y * yStrideRead + x * xStrideRead] / (float)16;
      }
      else {
        // zValue
        imgFixedPoint = camData[arrayId * zStrideRead + y * yStrideRead + x * xStrideRead] / (float)32;
        zScaledData[y][x] = (float)imgFixedPoint*frameThickness;
      }
    }
  }
}
```

#### CamMode = 1, CamMode = 2

Uses `CamDataFmt = DF_A16`. Result is a stack of amplitude frames (z = SensNFrames, y ≈ 292, x ≈ 282).

```cpp
cd = HE_ProcessCamData(currInst->heHdl, 1, 0, 0);
cd = HE_GetCamData(currInst->heHdl, 1, 0, metadata);
ushort* camData = (ushort*)cd->data; //16 bit Data

uint zSize = metadata->dimSz[2]; // z - SensNFrames
uint ySize = metadata->dimSz[1]; // y - 292
uint xSize = metadata->dimSz[0]; // x - 282

const ULONG zStrideRead = xSize * ySize;
const ULONG yStrideRead = xSize;

float *dataBuffer;

for (uint x = 0; x < (xSize); x++) {
  for (uint y = 0; y < (ySize); y++) {
    for (uint z = 0; z < (zSize); z++) {
      aScaledData[z][y][x] = camData[x + y * yStrideRead + z * zStrideRead] / (float)16;
    }
  }
}
```

#### CamMode = 0

Uses `CamDataFmt = DF_I16Q16`. Result alternates I and Q frames (z = SensNFrames, y ≈ 300, x ≈ 300).

```cpp
cd = HE_ProcessCamData(currInst->heHdl, 1, 0, 0);
cd = HE_GetCamData(currInst->heHdl, 1, 0, metadata);
ushort* camData = (ushort*)cd->data; //16 bit Data

uint zSize = metadata->dimSz[3]; // z - SensNFrames
uint ySize = metadata->dimSz[2]; // y - 300
uint xSize = metadata->dimSz[1]; // x - 300
uint arraySize = metadata->dimSz[0]; // I or Q - 2

const ULONG zStrideRead = xSize * ySize * arraySize;
const ULONG yStrideRead = xSize * arraySize;
const ULONG xStrideRead = arraySize;

for (uint x = 0; x < (xSize); x++) {
  for (uint y = 0; y < (ySize); y++) {
    for (uint z = 0; z < (zSize); z++) {
      for (uint arrayId = 0; arrayId < (arraySize); arrayId++){
        if (arrayId == 0) {
          IData[z][y][x] = camData[x * xStrideRead + y * yStrideRead + z * zStrideRead + arrayId];
        }
        else {
          QData[z][y][x] = camData[x * xStrideRead + y * yStrideRead + z * zStrideRead + arrayId];
        }
      }
    }
  }
}
```

#### CamMode = 3

Uses `CamDataFmt = DF_Hf` (32-bit float data). Result is a stack of long-exposure, short-exposure, and HDR frames (z = SensNFrames − SensNDarkFrames − 3, y ≈ 300, x ≈ 300).

```cpp
cd = HE_ProcessCamData(currInst->heHdl, 1, 0, 0);
cd = HE_GetCamData(currInst->heHdl, 1, 0, metadata);
float* camData = (float*)cd->data; //32 bit Data

uint zSize = metadata->dimSz[2]; // z - SensNFrames-SensNDarkFrames-3
uint ySize = metadata->dimSz[1]; // y - 300
uint xSize = metadata->dimSz[0]; // x - 300

const ULONG zStrideRead = xSize * ySize;
const ULONG yStrideRead = xSize;

for (uint x = 0; x < (xSize); x++) {
  for (uint y = 0; y < (ySize); y++) {
    for (uint z = 0; z < (zSize); z++) {
      Image[z][y][x] = camData[x + y * yStrideRead + z * zStrideRead];
    }
  }
}
```

#### CamMode = 5

Uses `CamDataFmt = DF_Z16A16P16`. Result has three interleaved types per pixel per z-slice: surface (ushort 11.5), amplitude (ushort 12.4), and phase phi (ushort 3.13).

```cpp
cd = HE_ProcessCamData(currInst->heHdl, 1, 0, 0);
cd = HE_GetCamData(currInst->heHdl, 1, 0, metadata);
ushort* camData = (ushort*)cd->data; // 16 bit Data

uint ySize = metadata->dimSz[3]; // 292
uint xSize = metadata->dimSz[2]; // 280
uint zSize = metadata->dimSz[1]; // 2 * exSimpHwin + 1
uint typeSize = metadata->dimSz[0]; // 3
// type => 0: surface (ushort 11.5), 1: amplitude (ushort 12.4), 2: phase phi (ushort 3.13)

const ULONG zStrideRead = typeSize;
const ULONG yStrideRead = typeSize * zSize * xSize;
const ULONG xStrideRead = typeSize * zSize;

for (uint x = 0; x < (xSize); x++) {
  for (uint y = 0; y < (ySize); y++) {
    for (uint z = 0; z < (zSize); z++) {
      for (uint t = 0; t < (typeSize); t++) {
        if (t == 0) {
          Surface[z][y][x] = camData[t + x * xStrideRead + y * yStrideRead + z * zStrideRead] / (float)32;
        } else if (t == 1) {
          Amplitude[z][y][x] = camData[t + x * xStrideRead + y * yStrideRead + z * zStrideRead] / (float)16;
        } else {
          Phi[z][y][x] = camData[t + x * xStrideRead + y * yStrideRead + z * zStrideRead] / (float)8192;
        }
      }
    }
  }
}
```

### d. zTag calculation

The measured surface in surface mode (CamMode = 4 or 7) refers to the frame number with sub-frame resolution, in unsigned 11.5 fixed point representation. Full detail on sub-frame calculation is in the heliCam C3 manual, chapter 5.3.3.

#### Basic surface calculation

A first basic calculation of the surface can be done using the frame thickness: multiply each pixel value by the frame thickness.

Frame thickness depends on camera settings:

- If `BSEnable=1` and `CalDur1Cyc=1`:  d_frame = 0.5 × (2 × SensNavM2 + 3) × λ
- If `BSEnable=0`:  d_frame = 0.5 × (2 × SensNavM2 + 2) × λ

`SensNavM2` is the camera parameter; λ (lambda) is the wavelength of the light source (typically 640nm with red LED). The unit of lambda is the unit of the resulting frame thickness (e.g. set λ=0.00064 for output in mm).

```cpp
float frameThickness = 0.5*(2 * SensNavM2 + 3)*lambda;
float imgFixedPoint = camData[arrayId * zStrideRead + y * yStrideRead + x * xStrideRead] / (float)32;
float zScaledData[y][x] = (float)imgFixedPoint*frameThickness;
```

#### Surface calculation with zTags

Each measurement contains header (meta) information including "zTag" values — a counter incremented by the linear axis encoder ticks, stored at the start of each frame readout. This is a 16-bit unsigned value; with a 100nm encoder resolution the counter can be incremented over 6.55mm without wraparound. To avoid wraparound issues, reset the position at the start of the measurement (~300µm before the trigger position) using the heliCam method `resetCamZCounter(..)`. Don't move the axis during this process.

After acquiring a measurement, header info is in measurement buffer 0. Full header layout is described in the register description (chapter 3, Header). Access zTag info via a pointer named `zTags`.

Add the reset position (in encoder ticks) to each zTag value in the header, and also add 2^16 = 65536 to each to prevent wraparound in the next calculation (a wraparound in zTagsReferenced is possible if the zTag counter was decremented by the axis encoder, depending on scan/trigger direction).

For representation in mm, divide each zTag value by "Ticks per mm" (10000 for a 100nm encoder). Results are stored in `zTagsReferenced`, giving position in mm for each integer frame number.

Since zValues from the surface are sub-frame resolution but zTagsReferenced values are only integer-frame resolution, linear interpolation is used between them:

```cpp
// This buffer includes the header with zTags.
cd = camera.getCamData(0, 0, 0);
// Pointer to the first zTag in the header
ushort* zTags = (ushort*)cd->data + 0x10;

// Allocate memory for the zTag reference
float *zTagsReferenced;
zTagsReferenced = new float[SensNFrames + 1];

// Calculate the zTag reference values
for (int i = 0; i < SensNFrames; i++) {
  zTagsReferenced[i] = ((pow(2, 16) + resetPosition) - zTags[i]) / TicksPerMM;
}

// Duplicate the last value (needed for calculating zScaledData)
zTagsReferenced[SensNFrames] = zTagsReferenced[SensNFrames - 1];

for (uint arrayId = 0; arrayId < (metadata->dimSz[0]); arrayId++) {
  for (uint y = 0; y < (metadata->dimSz[1]); y++) {
    for (uint x = 0; x < (metadata->dimSz[2]); x++) {
      if (arrayId == 0) {
        // amplitude value (12.4 fixed point value)
        aData[y][x] = camData[arrayId*arrayIdStride + y*yStride + x*xStride] / (float)16;
      }
      else {
        // interpolate the z value; raw z-value is 11.5 fixed point
        imgFixedPoint = camData[arrayId*arrayIdStride + y*yStride + x*xStride] / (float)32;
        imgFloor = (int)imgFixedPoint;                        // round off
        imgResidue = imgFixedPoint - imgFloor;                // residue for interpolation
        imgFloorScaled = zTagsReferenced[imgFloor];            // z value at rounded value
        imgStepsScaled = zTagsReferenced[imgFloor + 1] - imgFloorScaled;
        zScaledData[y][x] = imgFloorScaled + imgStepsScaled*imgResidue;  // linear interpolation
      }
    }
  }
}
```

#### Advanced surface calculation with zTags

In the basic calculation, zTag values are based on the measurement end of each frame, which may fall on the top or bottom depending on measurement direction. To make the zTagReference value independent of scan direction, add an approximate offset from frame start to frame middle. This depends on measurement speed (ticks/s) and the camera parameters `SensNavM2` and `SensTqp`.

```cpp
// This buffer includes the header with zTags.
cd = camera.getCamData(0, 0, 0);
ushort* zTags = (ushort*)cd->data + 0x10;

// Offset to the middle of a frame, using speed [ticks/s] and SensNavM2, SensTqp
// (35000000 = 35MHz internal frequency)
float zTagOffset = measurementSpeed * 4 * (SensNavM2 + 1) * (SensTqp + 6) / 35000000;

float *zTagsReferenced;
zTagsReferenced = new float[SensNFrames + 1];

for (int i = 0; i < SensNFrames; i++) {
  zTagsReferenced[i] = ((pow(2, 16) + resetPosition - zTagOffset) - zTags[i]) / 10000;
}

zTagsReferenced[SensNFrames] = zTagsReferenced[SensNFrames - 1];
```

Surface interpolation proceeds the same way as described above.

### e. Examples

Folder `.\Cpp\example` includes the Visual Studio 2013 solution "Example" with two independent example projects.

**Minimize_Energy** — four examples demonstrating simple use of the camera in minimize-energy mode, each running a full measurement sequence and controlling a linear motor.
- `sample1()`/`sample2()`: result stored in a text file
- `sampleA()`/`sampleB()`: result rescaled for graphical output with OpenCV
- `sample1()`/`sampleA()` calculate topology using zTag info from the header (more accurate, harder to implement)
- `sample2()`/`sampleB()` calculate topology using frame thickness (simpler, less error-prone — better starting point)

Configure via parameters at the top of `Minimize_Energy.cpp` (motor IP, port, measurement area). **Be careful with measurement area parameters — ensure optical components can't crash into the sample!**

**Change_Mode** — one example with an init sequence and measurement loop. Initializes heliCam and motor with default (simple max) parameters, measures in minimize-energy mode and plots, reconfigures to intensity mode for a 2D image, plots, reconfigures back. Loops `NofLoops` times (configurable at top of `Change_Mode.cpp`).

**Plot color mapped image** — C++ examples plot results as black-and-white images using a small part of OpenCV. Full OpenCV (tested with 2.49) is required for color-mapped images, and isn't included in the heliSDK installation.

To enable: in `Minimize_Energy`, set `USE_FULL_OPENCV` to 1 and add the full OpenCV library to the project:
```
include: $(SolutionDir)\openCV\include\opencv2
lib:     $(SolutionDir)\openCV\x86\vc12\lib , $(SolutionDir)\openCV\x64\vc12\lib
dll:     $(SolutionDir)\openCV\x86\vc12\bin , $(SolutionDir)\openCV\x64\vc12\bin
```

Color map requires `opencv_contrib249d.lib`. Add to *Linker → Input → Additional Dependencies*:

| Debug | Release |
|---|---|
| libHeLIC.lib | libHeLIC.lib |
| opencv_core249d.lib | opencv_core249.lib |
| opencv_highgui249d.lib | opencv_highgui249.lib |
| opencv_contrib249d.lib | opencv_contrib249.lib |

---

## Chapter III. Python

Python enables fast application development. Heliotis provides a Python wrapper for the C++-based libHeLIC library, exposing all functions from the doxygen documentation (`heliCamAPI.chm`), plus some Python-specific helper functions.

The wrapper (must be imported in every script using the heliCam) is stored at `.\Python\wrapper`.

### a. Basic script

```python
import os, sys
prgPath=os.environ["PROGRAMFILES"]
sys.path.insert(0,prgPath+r'\Heliotis\heliCam\Python\wrapper')
from libHeLIC import *
```

### b. Examples

`.\Python\example\libHeLIC_Simple.py` is a good starting point: a simple measurement sequence in surface mode that initializes and configures the camera and z-axis, with all relevant parameters defined at the top of the script.

`libHeLICTester.py` includes various tests and more advanced functionality — check the source for details on sequences and configuration.

---

## Chapter IV. LabView

Heliotis provides a LabView library with VIs to configure the heliCam and acquire measurements. Note: a separate Acquire VI exists for each camera mode / data format — select the correct one for your CamMode.

### a. Setup new LabView project

1. Create new LabView Project: *File → New… → Empty Project*
2. Add `libHeLIC.lvlib` to the project: right-click "My Computer" → *Add → File…* → select
   `C:\Program Files\Heliotis\heliCam\LabView\lib\libHeLIC.lvlib` (or the `(x86)` path for 32bit)
3. Optional, for Xenax motors: add the Xenax library the same way from
   `C:\Program Files\Heliotis\heliCam\LabView\lib\Xenax\Xenax.lvlib` (or `(x86)` for 32bit)
4. The project is now ready — create a new VI and implement your application.

### b. Library

Most important VIs:

| VI | Description |
|---|---|
| `AcquireA8.vi` | Acquire a measurement from heliCam in CamMode=1 and Comp11to8=1 |
| `AcquireA16.vi` | Acquire a measurement from heliCam in CamMode=1, 2 |
| `AcquireIntensity.vi` | Acquire a measurement from heliCam in CamMode=3 |
| `AcquireRawIQ.vi` | Acquire a measurement from heliCam in CamMode=0 |
| `AcquireZ16.vi` | Acquire a measurement from heliCam in CamMode=4, 7 |
| `AcquireZ16A16P16.vi` | Acquire a measurement from heliCam in CamMode=5 |
| `Close.vi` | Close the connection to the heliCam |
| `GetAttrib.vi` | Read the current value from a register |
| `GetSerials.vi` | Returns the number of connected heliCams and the first serial number |
| `Init.vi` | Initialize the driver for use with LabView. Call before any other library call! |
| `Open.vi` | Open the connection to a heliCam |
| `SetAttrib.vi` | Set a register. Register names/value ranges are in the register description file |
| `SetTimeout.vi` | Change the timeout for all other VI calls |

### c. Examples

Two examples are available.

**Change_Config** — a simple example structured as a "Flat sequence": *Parameter definition → axis configuration → camera configuration → measurement loop → termination.* These five parts form the basic subdivision of a LabView application.

**Minimize_Energy** — implemented as a state machine:

- **S_Start**: Set parameters for the axis and camera config. Default heliCam settings are fine to start.
- **S_Init_axis**: Configure the axis with previously defined parameters.
- **S_Init_heliCam**: Configure the heliCam with previously defined settings.
- **S_Ready**: System ready for a measurement. "Measure" button runs a measurement; "Configure" button returns to S_Start to reconfigure the axis.
- **S_Measure**: Runs a measurement; when finished, shows the result on the display and returns to S_Ready.

---

## Chapter V. HALCON

Heliotis provides an interface to HALCON from MVTec Software GmbH. Check www.halcon.com for interface updates — it's recommended to use the newest HALCON interface with the newest heliSDK.

### a. Installation

Update the HALCON Acquisition interface by downloading the newest files from the HALCON website. Copy the received `*.dll` files into `%HALCONROOT%\bin\%HALCONARCH%`.

`%HALCONROOT%` = HALCON's base install directory. `%HALCONARCH%` = system architecture: `x86sse2-win32` for 32bit HALCON, `x64-win64` for 64bit HALCON.

Note: HALCON 32bit requires heliSDK 32bit (`heliSDK-x.x.x.x-win32.exe`); HALCON 64bit requires heliSDK 64bit (`heliSDK-x.x.x.x-win64.exe`). To work with both HALCON versions, install both heliSDK versions.

### b. Examples

| Name | Description |
|---|---|
| `helicamc3_simple` | Very simple example defining only the most important parameters — fast topology measurement |
| `helicamc3_bidirectional` | Scans alternately up/down while moving the axis — for fast measurement sequences |
| `helicamc3_modes` | All possible camera modes (topology and tomography), with a procedure per mode |
| `helicamc3_motor_control` | Doesn't control the linear motor — user implements moving/triggering |
| `helicamc3_2cameras` | HALCON can control up to 127 heliCams from one script; this example controls two cameras with different settings |

---

## Troubleshoot

### Warnings and error messages

The heliSDK returns problem info as a warning or error message, differing by interface used.

**C++ / Python**: heliSDK returns popup windows (e.g. "FPGA download failed: tried 8 times."). Suppress popups in your own application using the API function `HE_SetCallback(..)`.

**LabView**: warnings/errors are redirected into LabView's error handling — the error flag is set and the message included in the error structure.

**HALCON**: default HALCON error messages popup; the heliSDK error message is written to the HALCON output console as message type "HALCON-low-level-error".

### Couldn't load FPGA firmware

**Symptoms**: When opening the connection to the heliCam (e.g. `HE_Open(..)` in C++, Open VI in LabView, or `open_framegrabber` in HALCON), the FPGA firmware is downloaded. Possible messages: "FPGA download failed: tried 8 times." or "CFactory::BuildSysVA(): upload firmware failed"

**Solution**: The type of built-up FPGA must be passed when opening the connection. Normally the type is `"c3cam_sl70"`. For the previous version (sl50), use type `"c3cam"` instead. (Must be set in each example and in heliViewer.)

To check connectivity with the current (sl70) version, use `libHeLICTester` (Start Menu → All Programs → heliotis → heliSDK(64) → libHeLICTester). Select "Test6: GetSerial numbers from all connected heliCams!" (type 6) — lists all correctly detected devices. If one is missing, see "heliCam detection failed" below.

To check data transfer between heliCam and computer, test number 3 is a good start.

### heliCam detection failed

If no heliCam C3 is listed by Test 6 in `libHeLICTester`, check all wires and the power supply for the whole measurement system — the camera system without motor controller can consume up to 24W; verify the power supply has enough capacity.

Check the USB cable from heliCam to computer. With the heliCam connected, power up the computer — the heliCam should now be listed in Device Manager under "libusb-win32 devices" as "HeliCam C3" (or "HeliCam C2" on some systems).

If still not listed, install the heliSDK with administrator rights and reboot, then repower the heliCam device. See "Chapter I Installation" for the full installation process.

---

## Appendix

### Flow chart

Example software flow, divided into two areas covering only camera communication: configuration and measurement. Advanced implementations may alternate between the two sections.

**Configuration:**
1. Initialize heliCam — `HE_Open(..)`
2. Configure heliCam — `HE_GetRegDesc(..)`, `HE_GetMap(..)`, `HE_GetReg(..)`, `HE_SetMap(..)`, `HE_SetReg(..)`
3. Allocate Memory — `HE_AllocCamData(..)`
4. Set Timeout — `HE_SetTimeout(..)`
5. Turn on illumination — `HE_GetRegDesc(..)`, `HE_SetMap(..)`, `HE_SetReg(..)`
6. Reset buffer — `HE_Acquire(..)` (loop while return value is positive)

**Measurement:**
7. Acquire — `HE_Acquire(..)`
8. GetCamData — `HE_GetCamData(..)`
9. ProcessCamData — `HE_ProcessCamData(..)`
10. GetCamData — `HE_GetCamData(..)`
11. Turn off illumination, close connection — `HE_Close(..)`

### Index

*(Not populated in source document.)*
