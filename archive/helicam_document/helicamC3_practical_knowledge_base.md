# heliCam C3 — practical knowledge base

Empirical findings from bench-testing `moke/devices/helicam.py` against real
hardware (camera serial 1002688069, `c3cam_sl70`), cross-checked against the
vendor docs in `archive/helicam_document_temp/documents/md version/`
(`heliCamC3_manual_v1_15.md`, `heliCamC3_register-description_v151105.md`).
This is a running record of *what we now know to be true about the hardware*
— for open bugs/gaps in the driver code itself, see
`moke/devices/open_issue_helicam.md`.

Evidence trail: `moke/devices/helicam_test_data/helicam_test_NNN/` folders,
produced by `moke/devices/helicam_test.py --mode N`. Specific runs are cited
inline below.

---

## 1. Sensor has non-image border pixels — crop before trusting any pixel stat

Per the manual, ch. 8 "Sensor Specification" (heliSens S3.0 / S3.1, both
apply to this camera):

> Number of Rows: 300 (**centre 292 usable; 2×4 rows are test rows**)
> Number of Columns: 300 (**centre 280 usable; 2×10 columns are test columns**)

So of the raw 300×300 frame every acquisition returns, only the center
292×280 pixels are real photodiode data. The border rows/columns carry a
fixed self-test pattern, not light-dependent signal.

Confirmed empirically on `helicam_test_016/in_run_frame.npy` (32-frame
CamMode-3 raw capture): row 0 and row 299 have per-row std ≈335 (values
alternating hard against 0/1023) vs. ≈8 for interior rows; column 0 and
column 299 have std ≈150 vs. ≈40 for interior columns — a fixed checkerboard
pattern, not photodiode noise.

**Fixed:** `HeliCamC3.crop_unphysical(data)` crops any raw array containing
a `(SENSOR_HEIGHT, SENSOR_WIDTH)` axis pair down to the centered
`SENSOR_HEIGHT_USABLE x SENSOR_WIDTH_USABLE` (292×280) region — it locates
the 300×300 axes by shape, so it works on both the volume-mode layout
(`n_frames, 300, 300, [channels]`) and the surface-mode layout
(`300, 300, channels`). Called automatically inside `acquire_single()`,
*before* `data_reformat()` — so the CamMode-3 dark-frame baseline itself
isn't skewed by border pixels either, not just the final statistic.
`get_image_shape()` now returns the cropped `(292, 280)`.

`acquire_avg()` crops the same way, per-frame, before accumulating. Still
not cropped: `save_raw_np()`, deliberately — it exists to preserve the
fully raw, untouched array, border pixels included, for later
reprocessing.

---

## 2. Raw I/Q values sit on a ~512 baseline, not 0 — real dynamic range is roughly halved

Manual §5.1 ("Measure Raw IQ"): `raw_I`/`raw_Q` range 0–1023 (10-bit), and
**"a non-modulated signal corresponds to a value around 512, not 0."** This
is a property of the demodulation electronics itself, not a fixable dark
current — `iq_to_amplitude()` already defaults `offset_I=offset_Q=512.0` for
exactly this reason.

Confirmed on `helicam_test_016`: per-frame means across all 32 frames sit at
522–534 (both "dark" and "signal" frames), per-channel means I≈537, Q≈525 —
consistent with the ~512 nominal center, not a near-zero dark level.

**Practical consequence:** since raw counts are hard-clipped to [0, 1023]
and already centered near 512, a signal reading has only ≈±511 of headroom
before clipping in either direction. In other words: with this acquisition
method, a channel's *dark-baseline-subtracted* value can realistically only
reach roughly **half** of `SENSOR_ADC_MAX` (1023), not the full range —
`SENSOR_ADC_MAX` itself is never actually reachable as a *post-subtraction*
ceiling. Anything computing a "fraction of full scale" against the full
`SENSOR_ADC_MAX` (e.g. `_intensity_full_scale()`'s `2 * SENSOR_ADC_MAX`
upper bound in `helicam.py`) should be read with this halving in mind — it's
a best-case theoretical ceiling that this acquisition method structurally
can't reach, not a realistic target.

---

## 3. CamMode 3 ("intensity"/"steady" mode) does NOT do lock-in demodulation

Manual §5.4, verbatim: *"the control electronics of the sensor is modified
in such a way that not demodulated signals i.e. usual integrated signals are
generated on the two channels I and Q."*

So in CamMode 3, the two channels reuse the same data-path/format
(`DF_I16Q16`, same as true lock-in CamMode 0) but are **not** in-phase/
quadrature components — demodulation (sine/cosine × local oscillator,
§5.1) is specifically disabled in this mode. Instead:

> "The sensor returns two images with different exposure times."

### 3a. The two channels are a short/long exposure HDR pair, with a known ratio

- `SensExpTime` × `(SensExpTimeMult+1)` = the **short** exposure time, in µs
  (register description §2.14 — this is exactly what `set_acquire_time()`
  controls, i.e. every `t_acquire_us` used throughout this project's test
  modes is the *short*-exposure duration only).
- `SensExpRatio` sets the short:long ratio (register description §2.13,
  corroborated by the manual table):

  | `SensExpRatio` | short:long ratio |
  |---|---|
  | 0 | 1:2 |
  | 1 | 1:4 |
  | 2 | 1:8 |
  | 3 | 1:16 |

  `STEADY_SETTINGS["SensExpRatio"] = 3` in `helicam.py` → **1:16** — e.g. at
  `t_acquire_us=1.0`, the long-exposure channel is actually integrating for
  ~16µs, not 1µs. Note: the SDK's own live register comment for
  `SensExpRatio` (pulled via `get_registers()`) says *"Dead time to comply
  with the frame rate"* — this is wrong/misleading; trust the manual's
  short:long description instead (already flagged in `STEADY_SETTINGS`'s
  inline comment).

### 3b. Empirically confirmed channel mapping: channel 0 = long, channel 1 = short

Tested directly via mode 6 (`mode6_sensexpratio_sweep`, added specifically
for this question), sweeping all 4 `SensExpRatio` values at fixed
`t_acquire_us=1.0` and capturing the raw, pre-`data_reformat()` I/Q pair via
`cam.save_raw_np()` (see `helicam_test_018/mode6_summary.png` and
`mode6_sensexpratio_table.csv`):

- **Channel 0** grows dramatically with `SensExpRatio`: colorbar range on the
  dark-subtracted, frame-averaged image goes from roughly [-15, 10] at
  ratio=0 (1:2) to [-10, 80] at ratio=3 (1:16) — i.e. its magnitude tracks
  the short:long ratio directly. This is the **long-exposure** channel.
- **Channel 1** stays roughly constant across all 4 ratios (colorbar range
  ~[-15, 25] throughout) — expected, since its exposure time is fixed by
  `SensExpTime` alone and doesn't depend on `SensExpRatio`. This is the
  **short-exposure** channel.

This also explains an earlier observation (an ad-hoc bench capture,
`helicam_test_015`/`016` era): channel 0 was eyeballed as ~10x stronger than
channel 1 — consistent with whatever `SensExpRatio` that capture happened to
be using giving channel 0 (long exposure) substantially more integration
time than channel 1 (short exposure).

**Now reflected in code:** `HeliCamC3.SENSEXPRATIO_SHORT_LONG` (`{0:2, 1:4,
2:8, 3:16}`) records the ratio table and the channel-0=long/channel-1=short
mapping, used by the rewritten `auto_expose()` (§5). `data_reformat()`'s
CamMode-3 branch still combines the two channels via
`_dark_subtract_channels(data).sum(axis=-1)` — i.e. it still adds the
short- and long-exposure channels together as if they were
equivalent/redundant quantities. Per the above, they are not: they're two
different-duration exposures of the same scene, intended (per the manual's
"HDR" framing) to be combined as a proper HDR merge (favor the
long-exposure pixel unless saturated, fall back to a scaled short-exposure
pixel otherwise) — not summed directly. This part is flagged but **not
fixed** yet; see `open_issue_helicam.md` #3 for the related
`DF_Hf`-vs-`DF_I16Q16` divergence this ties into.

---

## 4. `data_reformat()`'s frame-count handling (CamMode 3)

- `SensNFrames` sets the *total* number of frames per acquisition; the first
  `SensNDarkFrames` (≥7) are dark/unexposed reference frames, averaged into
  a per-pixel baseline and subtracted from the rest (BSEnable=0 is mandatory
  in this mode — the hardware does not do baseline suppression itself, per
  manual §5.4).
- `data_reformat()` **averages** (not sums) the dark-subtracted frames over
  the frame axis, deliberately diverging from the vendor's own on-device HDR
  accumulation. Rationale: this driver doesn't need `SensNFrames` to act as
  a second light-budget knob (which summing would make it, since more
  frames would mean more accumulated signal, extending effective dynamic
  range) — averaging keeps `SensNFrames` purely a noise-reduction control,
  and keeps the returned pixel scale independent of `SensNFrames`/
  `SensNDarkFrames`. (The old `_intensity_full_scale()` helper that depended
  on this — a fixed `2 * SENSOR_ADC_MAX` upper bound — has since been
  removed entirely; `auto_expose()` no longer needs an absolute ceiling at
  all, see §5.)
- Confirmed empirically via mode 5 (`mode5_frames_sweep`): before the
  sum→mean fix, raw peak intensity scaled roughly linearly with
  `SensNFrames` (`helicam_test_012`: 63.75 → 79.65 across a 32→256 sweep, a
  ~25% climb, consistent with summation). After the fix, `max_val` comes out
  flat across the same sweep (`helicam_test_014`/`015`: 81.0–82.6 across
  10 points spanning 32→256, a ~2% spread).
- The manual's `SensNFrames - SensNDarkFrames - 3` "HDR image count" formula
  (§5.4) does **not** apply to this driver's own reduction — that number
  describes the vendor's own on-device `DF_Hf` combination pipeline, which
  this driver bypasses (see open item #3 above / `open_issue_helicam.md`
  #3). This driver's own `to_numpy`/`data_reformat` reduction sums over
  exactly `n_frames - n_dark` frames, confirmed by matching the manual's
  `-3` term actually making a frame-count normalization *worse* (see
  session notes: dividing by `n_frames - n_dark - 3` gave a *decreasing*
  trend across `SensNFrames`, `92.78 → 83.48`; dividing by plain
  `n_frames - n_dark` gave the flat ~2%-spread result instead).

---

## 5. `auto_expose()` — rewritten around the dual-channel ratio, not an absolute ceiling

The original version searched for a `t_acquire_us` that put the summed
channel0+channel1 signal at `target_fraction` of a theoretical
`2 * SENSOR_ADC_MAX` full scale. That ceiling was never actually correct —
per §2 (the ~512 baseline halves real headroom) and §3 (channel 0/1 are a
short/long HDR pair, not equal-weight components) — so `target_fraction`
never meant what it claimed to.

**New approach**, exploiting §3b's confirmed channel mapping: in the
unsaturated regime, `channel0 / channel1` equals the nominal
`SensExpRatio`-derived ratio (`SENSEXPRATIO_SHORT_LONG`) at *any* incident
light level, since it's purely a function of the two exposure times. Once
channel 0 (long exposure) starts clipping, its growth falls behind channel
1's and the ratio drops below nominal — a self-calibrating saturation
signal that needs no assumption about the sensor's absolute ADC ceiling at
all.

Algorithm: geometric-double `t_acquire_us` from `t_min_us` while the
ratio stays within `ratio_tol` of nominal, then bisect between the last
unsaturated and first saturated `t` to refine the saturation onset
(`t_saturation_onset_us`), then set the final exposure to
`target_fraction * t_saturation_onset_us` (default 0.5 → halfway to
saturation). Each trial acquires raw data directly (`_acquire()` +
`crop_unphysical()` + the new shared `_dark_subtract_channels()` helper,
§4), keeping channels 0/1 separate rather than going through
`data_reformat()`'s CamMode-3 branch (which sums them).

Return dict changed shape accordingly: `max_frac`/`full_scale` are gone;
new fields are `t_saturation_onset_us`, `nominal_ratio`, and
`ceiling_not_found` (search reached `t_max_us`/`max_iter`, or an
acquisition failed, without ever seeing the ratio deviate — `t_acquire_us`
falls back to the largest `t` actually tried). `floor_limited` is kept,
now meaning channel 0 is already saturating at `t_min_us`.

**Effect on the two bugs tracked in `open_issue_helicam.md` #9:** the
broken "return the last failed trial" fallback is gone — there's no more
"pick the best table entry" step at all, since the new geometric-doubling
phase only ever returns a `t` it just successfully measured. The
no-pipeline-resync-after-a-timeout bug is **still open** — a failed
acquisition still isn't recovered from — but now causes `auto_expose()` to
stop and report `ceiling_not_found=True` (fail clearly) instead of
continuing past it and returning a bogus result (fail silently). See
`open_issue_helicam.md` #9 for full detail.

Mode 1 in `helicam_test.py` still bypasses `auto_expose()` (fixed exposure
sweep) — not yet re-evaluated against the rewritten version.

---

## 6. Register gaps

`STEADY_SETTINGS` in `helicam.py` does not set `SensNavM2`/`SensTqp` — steady
mode currently inherits whatever those two demod-timing registers were last
left at by an earlier mode/session, rather than the values heliViewer uses
for a confirmed-good capture (`SensNavM2=2`, `SensTqp=1392`, recorded in
`STEADY_SETTINGS_GUI_REFERENCE`). `compare_steady_settings_to_gui_reference()`
exists to check this gap but the fix (adding these two to `STEADY_SETTINGS`
itself) has not been applied/tested against hardware yet.

---

## 7. Test mode reference (`helicam_test.py`)

| Mode | Purpose | Key output |
|---|---|---|
| 1 | Lifecycle / fixed exposure sweep (gain=1x, no `auto_expose()`) | `mode1_exposure_table.csv` |
| 2 | Lock-in-style pipeline: steady → rawIQ → minE | `mode2_summary.png`, `mode2_params.json` |
| 3 | Live streaming preview (steady + minE) | interactive, optional saved frames |
| 4 | `auto_expose()` checkout in isolation | `mode4_autoexpose_table.csv` |
| 5 | `SensNFrames` sweep — validates sum→mean fix (§4 above) | `mode5_frames_sweep_table.csv` |
| 6 | `SensExpRatio` sweep — channel 0 vs channel 1 identity (§3b above) | `mode6_sensexpratio_table.csv` |

Every run dumps the full live register set to `registers.json`
(`HeliCamC3.dump_registers()`); modes 2–4 also dump registers immediately
before/after their `auto_expose()` call.

---

## Open questions (not yet resolved)

- Should `data_reformat()`'s CamMode-3 reduction do a real HDR merge
  (long-exposure pixel unless saturated, else scaled short) instead of
  summing the two channels? (§3)
- `SensNavM2`/`SensTqp` gap in `STEADY_SETTINGS` (§6) — apply and re-test?
- `auto_expose()`'s remaining bug (§5) — no pipeline resync after an
  acquisition timeout, still open in the rewritten version too.
- Now that `auto_expose()` no longer has the two bugs mode 1 was built to
  avoid, should mode 1 switch back to using it instead of its hardcoded
  exposure sweep? (§5, §7)
