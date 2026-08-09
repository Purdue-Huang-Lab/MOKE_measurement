vs# Wide-Field tr-MOKE — Field Guide & Code Spec

**Rev 3.** PEM polarimetry → heliCam lock-in imaging of pump-induced Kerr rotation on CrSBr.
§1–4 = bench reference. §5 = software architecture (the part to hand an AI along with the task).

---

## 1. Physics quick reference

PEM fast axis ∥ incident polarization, analyzer at 45°, `δ(t) = A sin(ωt)`, `E ∝ (1, θ_K + iε_K)`:

```
I ∝ ½[ 1 + 2θ_K·J₀(A) + 4ε_K·J₁(A)·sin(ωt) + 4θ_K·J₂(A)·cos(2ωt) + ... ]
```

| | demod at | A for max | value |
|---|---|---|---|
| ellipticity ε_K | **1×** f_PEM | 1.841 rad | J₁ = 0.5819 |
| rotation θ_K | **2×** f_PEM | 3.054 rad | J₂ = 0.4865 |

One channel per acquisition — the camera demodulates at a single frequency.

```
θ_K     = (V_2f / V_DC) / (4·J₂(A))        # needs a paired intensity-mode frame
θ_min   ≈ 1 / (2·J₂·√N) ≈ 1/√N            # 10 µrad → N~1e10;  1 µrad → N~1e12
Δθ_meas = Δθ_MOKE + ½·sin(2α)·Δδ(t)        # α = probe azimuth vs. crystal axis
```

The birefringence term does **not** cancel in the differential — it *is* a differential
signal. Suppression by azimuth alignment is only first order in α (1° error → 3.5% leakage).

**Separation:** ±H subtraction (MOKE odd in M, birefringence even) if field available.
Otherwise azimuth decomposition — MOKE is **constant** in α, artifact goes as **sin(2α)**.
Sample α = 0/45/90/135°, project.

---

## 2. Optics

**Probe** — monochromatic, Glan-Taylor polarized (extinction ≤1e-5), focused at objective BFP
→ wide-field Köhler illumination. Azimuth on a CrSBr principal axis (find by static
crossed-pol extinction on the flake, ~0.1°).

**Azimuth HWP** — K-cube motorized, in the **common path** between BS and objective.
Double-pass = identity, so the return beam hits the PEM at the original azimuth regardless
of φ. (Input-arm placement would inject a static offset of exactly 2φ.) Sign: θ_K → −θ_K on
return; absorb into calibration.

**Pump** — focused, chopped 200 Hz at a beam waist. FOV ≥ 3× pump spot so the unpumped
annulus is a reference ROI. Near-normal incidence (pulse-front tilt `Δt = d·sinφ/c`;
100 µm @ 10° → 58 fs). Spectral filter at detection.

**Detection** — PEM (0°) → analyzer (45°) → heliCam.
- **PEM at a pupil-conjugate plane**, not an image plane. Retardance varies across its
  aperture; at a pupil every field point samples the same footprint. Verify: phase image
  must be spatially uniform.
- Beamsplitter s/p phase is usually the dominant static ellipticity source — worse than the
  objective. Null it (§4).
- Analyzer angle forgiving (±1° → second order). PEM-axis-to-polarization is **not**:
  a 0.5° error appears at 2f, the demod frequency itself, and a 1e3 dynamic-range demand on
  a 10-bit ADC clips before software differencing ever runs.

---

## 3. Timing

Two lines. Only the first is a hard lock.

```
PEM 2f ref ──────────────────► heliCam demod clock          [MANDATORY — PEM is resonant, drifts]
heliCam internal trig (200 Hz) ──► chopper ext ref          [timing master]
```

Per 5 ms period, free-running lock-in stream:

```
trig → wait φ₁ → accumulate N_demod → readout   = A
     → wait T/2+φ₂ → accumulate N_demod → readout = B
differential = A − B
```

φ₁/φ₂ are software params absorbing chopper mechanical lag + blade transit. Self-
resynchronizing: both accumulations hang off one trigger edge, so a dropped frame costs one
period, not the polarity of the whole run.

**Budget per 2.5 ms half-period:** `φ (~200 µs) + N_demod×10 µs (2.0 ms) + readout (~300 µs)` → ~80% duty, N_demod = 200.

**N_demod must be even** — consecutive demod cycles at f_d = 2f_PEM are half a PEM period
apart, so 1f contributions cancel pairwise *regardless of start phase*. This is what frees
line 2 from any PEM phase constraint.

| f_PEM | f_demod | f_chop | N_demod | duty |
|---|---|---|---|---|
| ~50 kHz | 100 kHz | 200 Hz | 200 (even) | ~80% |

**Camera limits:** C3 f_demod ≤ 250 kHz; C4 305 Hz–134 kHz. 4-tap square demod passes odd
harmonics (J₆/3 ÷ J₂ ≈ 0.8% gain error). 10-bit I/Q. FWC 500 ke⁻. Raw rate ~440 MB/s.

---

## 4. Bench procedure

1. Coarse alignment; confirm BFP focus (Bertrand lens).
2. Find CrSBr principal axes by crossed-pol extinction → set α = 0.
3. PEM: flat-top at half-wave retardation, set A = 3.054 rad.
4. Set f_demod = 2×f_PEM from the PEM 2f output. Check phase image is uniform → PEM plane OK.
5. **Null static offset** with analyzer / Soleil-Babinet. Watch the live I/Q histogram for
   clipping. Acquire per-pixel offset map (pump blocked) — spatial variation can't be nulled.
6. Calibrate: Faraday coil DC sweep, then AC at 200 Hz (§5.9).
7. φ-sweep → set φ₁/φ₂, determine A/B polarity.
8. Find t₀ on the **ΔR/R channel**, not MOKE.
9. Acquire. 

---

## 5. Software

Target repo: `MOKE_measurement` (Purdue-Huang-Lab). Python, NumPy, PyQt5 for preview.

### 5.1 Package layout

```
moke/
  config.py       MokeConfig dataclass + JSON (de)serialization; single source of truth
  devices/
    base.py       Device ABC: open/close/status, context-manager protocol
    helicam.py    HeliCam    — ctypes binding to heliSDK DLL
    stage.py      DelayStage — move_ps, wait_settle, limits
    kcube.py      KCube      — probe azimuth HWP, backlash-aware
  acquire.py      RunState machine + run loop
  accumulate.py   Accumulator
  calibrate.py    phase_scan, faraday_calibrate, null_offset, dark_flat_badpix, find_t0
  io.py           H5Writer (chunked, incremental)
  preview.py      lossy display consumer
  sim.py          fake devices for dry-run
  cli.py          entry point
```

### 5.2 Config — one dataclass, serialized into every output file

```python
@dataclass
class MokeConfig:
    # timing
    f_pem_hz: float;  pem_amplitude_rad: float = 3.054
    f_demod_hz: float;  n_demod: int;  f_chop_hz: float = 200.0
    phi1_us: float;  phi2_us: float
    polarity: Literal["A_is_pump_on", "B_is_pump_on"]
    channel: Literal["rotation", "ellipticity"]     # sets f_demod = 2f or 1f
    # scan
    delays_ps: list[float];  azimuths_deg: list[float];  repeats: int
    delay_order: Literal["sequential", "random", "bidirectional"] = "random"
    # geometry
    roi_signal: tuple[int,int,int,int];  roi_reference: tuple[int,int,int,int]
    # provenance
    git_commit: str;  operator: str;  sample_id: str;  temperature_k: float
```

`from_json` / `to_json`. Never read a timing number from anywhere else.

### 5.3 Device layer

All devices subclass `Device` and implement `__enter__`/`__exit__`. Acquisition runs inside
a `DeviceStack` context manager so **every exit path closes hardware**, including exceptions
and Ctrl-C. Partial data is flushed before teardown.

heliCam specifics:
- Mode switching (intensity ↔ lock-in) is a config change, not a per-frame flag. Wrap it with
  an explicit settling delay; do not assume the next frame is valid.
- Expose `arm(n_demod, phi_us)`, `read_frame() -> (I, Q)`, `set_demod_clock(external=True)`.
- Log the measured readout time and minimum retrigger latency at startup.

### 5.4 Invariants — assert at startup, fail loud

```python
assert cfg.n_demod % 2 == 0                                   # 1f cancellation
assert abs(cfg.f_demod_hz - k*cfg.f_pem_hz) < tol             # k=2 rotation, 1 ellipticity
assert cfg.phi1_us*1e-6 + cfg.n_demod/cfg.f_demod_hz + readout_s <= 0.5/cfg.f_chop_hz
assert chopper.lock_status() == "locked"                      # poll, settles in seconds
assert helicam.demod_clock_source == "external"               # never free-run against PEM
assert iq_percentile(99.9) < CLIP_THRESHOLD                   # static offset nulled
assert stage.within_limits(cfg.delays_ps)
```

The clip check is the one that silently ruins data. Re-run it whenever the sample or
alignment changes, not just at startup.

### 5.5 State machine

```
IDLE → INIT → PREVIEW → NULL → CALIB → PHASE_SCAN → FIND_T0 → ACQUIRE → FINALIZE → CLOSE
                                                                   ↑↓
                                                                 PAUSE
ABORT reachable from any state → flush partial → CLOSE
```

`ACQUIRE` is resumable: on restart, read `n_pairs` from the open file and continue from the
first incomplete (azimuth, delay) cell.

### 5.6 Threading

Three roles, decoupled by queues:

| thread | behavior on backpressure |
|---|---|
| acquisition | blocking camera read → bounded queue; **never** blocks on consumers |
| writer | queue → chunked HDF5; if it falls behind, raise (do not drop science data) |
| preview | **latest-frame-wins ring buffer, drop freely**; must never apply backpressure |

Accumulation is cheap — do it in the acquisition thread, not a fourth one.

### 5.7 Accumulator

Never retain raw frames. Per (azimuth, delay) cell:

```python
class Accumulator:
    sum_diff: np.ndarray      # Σ(A−B)        float64, (Y,X)
    sumsq_diff: np.ndarray    # Σ(A−B)²       for variance / SEM
    sum_total: np.ndarray     # Σ(A+B)        intensity normalization
    ref_series: list[float]   # per-pair reference-ROI value
    n_pairs: int

    def add_pair(self, A, B): ...
    @property
    def mean(self): return self.sum_diff / self.n_pairs
    @property
    def sem(self):  return np.sqrt(self.sumsq_diff/self.n_pairs - self.mean**2) / np.sqrt(self.n_pairs)
```

Rules:
- Difference **adjacent A/B pairs**, then average the differences. Block-averaging all-A vs
  all-B re-admits every 1/f component below the block rate.
- Normalize the signal ROI to `roi_reference` per pair — the residual static 2f offset there
  is ∝ probe intensity, i.e. a free per-frame intensity monitor in the same demodulated frame.
- ABBA ordering within a pair sequence to cancel linear drift.
- Keep raw frames only for short, explicitly-flagged diagnostic bursts.

### 5.8 File layout (HDF5, chunked, written incrementally)

```
/config                    attrs: every MokeConfig field
/calibration/dark          (Y,X)
/calibration/flat          (Y,X)
/calibration/bad_pixels    (Y,X) bool
/calibration/static_offset (Y,X)          pump-blocked per-pixel 2f offset
/calibration/faraday       attrs: scale_urad_per_mA, linearity_r2
/data/delay_ps             (T,)
/data/azimuth_deg          (Az,)
/data/diff                 (Az,T,Y,X) f32   mean of (A−B)
/data/sem                  (Az,T,Y,X) f32
/data/intensity            (Az,T,Y,X) f32   paired intensity-mode frame → V_DC
/data/n_pairs              (Az,T) i32       resume cursor
/data/ref_roi              (Az,T,P) f32
/log/                      timestamps, temperature, powers, stage positions
```

Chunk along (Y,X) per cell so a cell writes in one op. Flush after every cell.

### 5.9 Calibration routines

```python
phase_scan(cam, chop, n=64) -> PhaseScanResult
    # sweep φ over a full chopper period, record signal(φ)
    # returns: flat-top edges (→ true chopper lag), usable window width,
    #          suggested φ₁/φ₂ (flat-top centers), and A/B polarity
    # this single scan replaces the old "check even/odd frames" step

faraday_calibrate(cam, coil, currents_mA) -> (scale_urad_per_mA, r2)
    # DC sweep → linearity + absolute scale.  TGG: θ = V·μ₀·n·I·L ≈ 1.6 µrad/mA
    #   (n=2000 turns/m, L=5 mm, V≈130 rad·T⁻¹m⁻¹ @633nm — check datasheet)
    # then AC at f_chop: injects a synthetic pump-induced Kerr signal of known
    #   amplitude → validates demod, A/B assignment, pairing, ROI normalization
    #   end-to-end with no laser and no sample.  BUILD THIS FIRST.

null_offset(cam, analyzer_or_babinet) -> offset_map
    # minimize field-averaged 2f; return per-pixel residual map

find_t0(cam, stage) -> float
    # ΔR/R channel (chopper-demodulated, no polarization analysis). NOT the MOKE channel.
```

Absolute anchor for the Faraday scale: rotate the **input polarizer** by known δ → injects
θ = δ exactly. Do **not** use the analyzer for this (its 2f effect goes as cos 2Δ, second order).

### 5.10 Preview

1–10 Hz is ample. Bin 2×2 or 4×4. Three panels, not one:

- **amplitude image** — beam position, alignment
- **I/Q histogram** — clipping is silent otherwise; this is the §4 null feedback
- **phase map** — must be spatially uniform; non-uniformity = PEM in the wrong conjugate plane

### 5.11 Simulator

`sim.py` provides drop-in fakes for every device, generating frames from the §1 expressions
plus shot noise, a static offset, and an injectable `sin(2α)` birefringence term. Lets the
full state machine, accumulator, resume logic, and file layout be tested without the bench —
and lets an AI agent iterate on acquisition code offline.

### 5.12 Scheduling note

K-cube moves take seconds. **Do not nest azimuth inside the delay loop.** Characterize the
α-dependence at a few representative delays, then run long delay scans on-axis and subtract
the characterized residual. If interleaving, always approach each azimuth from the same
direction (backlash).

---

## 6. Open items

- [ ] **Confirm heliCam C3 frame-sync / trigger output** — heliSDK register description PDF, or ask Heliotis
- [ ] Measure readout time **and minimum retrigger latency** → fix N_demod (both must fit in 2.5 ms)
- [ ] Photon budget with *actual* probe power over *actual* FOV → expected θ_min per delay point
- [ ] Layer parity: even-layer compensated A-type AFM has no net M → no polar Kerr rotation.
      Decide whether out-of-plane field access is required.
- [ ] Co-register DC reflectance every point — Fabry-Pérot makes θ_K thickness-dependent
      (incl. sign reversals), so spatial Kerr maps mix magnetic and interference contrast.
- [ ] Steady-state heating vs. T_N ≈ 132 K — Kerr amplitude vs. nominal cryostat T is itself a thermometer.
- [ ] Verify pump spot centroid vs. delay (beam walk is directly visible in wide field).

---

## References

1. J. McCord, *J. Phys. D: Appl. Phys.* **48**, 333001 (2015) — wide-field MO microscopy, artifacts.
2. *Transient Absorption Microscopy Using Widefield Lock-in Camera Imaging*, *J. Phys. Chem. C* (2024),
   DOI 10.1021/acs.jpcc.4c02984 — heliCam in widefield pump-probe.
3. Hinds Instruments, *Magneto-Optic Kerr Effect* app note — PEM geometry, V_DC/V_1f/V_2f ratios.
4. Heliotis heliCam C3/C4 datasheets + heliSDK register description.
