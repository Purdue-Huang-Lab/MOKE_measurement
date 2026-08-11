# TODO / handoff — heliCam C3 driver work (updated 2026-08-11)

Background reading, in order of how foundational they are:
1. `archive/helicam_document/helicamC3_practical_knowledge_base.md` — what
   we've learned about the hardware itself (sensor border pixels, ~512
   baseline, dual-channel HDR pair, frame-averaging rationale). Start here.
2. `moke/devices/open_issue_helicam.md` — open bugs/gaps in the driver code.
3. This file — what's still outstanding and what to check.

Since the last version of this file, `crop_unphysical()` being wired into
the acquire path and CamMode-3's mean-not-sum reduction have both now seen
repeated real hardware runs (mode 2 lock-in, mode 4 auto_expose, mode 5
`good_mode5_test`, mode 7 no-flush) without incident, so those items are
dropped from this list.

---

## 1. Needs a hardware run — rawIQ offset correction (`self` vs `null`)

**Why:** `mode2_lockin()`'s rawIQ amplitude/phase looked wrong — amplitude
dominated by a large flat value, phase nearly constant across the whole
frame. Root cause (confirmed from a real capture, `260811-lockin mode`):
`OffsetMethod` doesn't apply to CamMode 0 at all (register description
§2.18, `OffsetProc`'s CamMode column is "1,2,4,5,7" — 0 excluded), so
rawIQ always returns raw, uncorrected ADC counts. The manual's nominal
offset of 512/channel was off by **~88 counts on I, ~67 on Q** on this
camera — a residual bias comparable to or larger than the real amplitude
signal, which is why the phase map came out looking like a fixed constant
(it's dominated by that bias vector's angle, `atan2(66.6, 87.9) ≈ 0.646
rad`, matching the observed phase mean almost exactly).

**What was built (not yet tested on hardware):**
- `HeliCamC3.null_offset(n_acquisitions=10)` (`helicam.py`) — dedicated
  per-pixel offset calibration, thin wrapper around `acquire_avg()`.
  Requires rawIQ mode already set, and requires no modulated signal
  present while it runs (light blocked / demod detuned) to be meaningful.
- `mode2_lockin()` (`helicam_test.py`) gained an `offset_method` param
  (`"self"` — this capture's own `I.mean()`/`Q.mean()`, free, vs.
  `"null"` — a dedicated `null_offset()` calibration just before the real
  capture), wired to a new `--offset-method {self,null}` CLI flag
  (default `self`). `mode2_params.json` and the summary plot record which
  was used plus the resulting offset values, so runs are comparable.
- `RAWIQ_SETTINGS`'s dead `OffsetMethod` entry was removed (it never did
  anything for CamMode 0), replaced with an explanatory comment.

**To test:** run `--mode 2 --offset-method self`, then `--mode 2
--offset-method null` (physically block the beam / detune the demod
frequency right as it logs "measuring null_offset()..."), and compare
`mode2_rawiq_amplitude.npy`/`mode2_rawiq_phase.npy` and the summary PNGs
between the two runs — does a real, spatially-varying signal emerge once
the flat bias is properly removed, and does `null` (per-pixel, dedicated)
actually do meaningfully better than `self` (scalar, same-frame)?

---

## 2. Needs a hardware run — CamMode-3 short-exposure fix + mode-switch warm-up

**Why:** `mode2_lockin()`'s "steady" frame looked much worse quality than
`mode1_lifecycle()`'s sweep at comparable `t_acquire_us`. Confirmed via
register dumps (`mode2_registers_at_start.json` vs `registers.json` in
`helicam_test_000_selfoffset`): `data_reformat()`'s old CamMode-3 branch
summed channel 0 (long) + channel 1 (short), and channel 0's *real*
integration time is `SensExpRatio × SensExpTime` — so the reported
brightness was actually controlled by `SensExpRatio`, not just
`t_acquire_us` as expected. `mode1_lifecycle()` never touches
`SensExpRatio` (inherits `STEADY_SETTINGS`'s default of 3, i.e. 1:16),
while `mode2_lockin()` explicitly sets it to 1 (1:4) — same nominal
`t_acquire_us=16`, but channel 0 really integrated 256µs in mode 1 vs only
64µs in mode 2, a 4× difference in the channel that dominated the sum.

**What changed:** `data_reformat()`'s CamMode-3 branch now returns
`_dark_subtract_channels(data)[..., 1]` (channel 1 / short exposure only)
instead of `.sum(axis=-1)`. Steady-state's reported intensity is now tied
directly and unambiguously to `t_acquire_us`, independent of
`SensExpRatio`, and consistent with how CamMode 0 (rawIQ) already works.
Channel 0 is still measured/dark-subtracted every acquisition (same HDR
pair) but no longer returned by `data_reformat()` — still available via
`_dark_subtract_channels()` directly, which `auto_expose()` still uses.

**Update — `SensExpRatio` wasn't the whole story.** After this fix,
mode 2's steady frame *still* looked much worse than mode 1's sweep at
the same `t_acquire_us=16`. Compared `mode1_t16us_frame.npy`
(`helicam_test_001`) against `mode2_steady_frame.npy`
(`helicam_test_000`) directly: `std` was actually close (6.3 vs 5.1) but
the two frames didn't correlate at all (-0.02), and mode 2's frame showed
uniform noise with no detectable real spatial signal, while mode 1's
showed a strong, localized feature (a beam spot). The deciding test:
**mode 1's own *first* acquisition** (`t=1us`, right after its mode
switch) has nearly identical statistics to mode 2's steady frame
(top/bottom-half std ~5.0-5.2 in both, row-mean-std ~0.1 in both) — while
mode 1's *later* steps (e.g. `t=16us`, 5 acquisitions into the same loop,
no mode-switch in between) look completely different (row-mean-std 2.6,
23× higher, matching the real visible feature). So it isn't about
`SensExpRatio` or which channel is reported at all: **the first
acquisition right after any mode switch carries a settling artifact**
(weak/absent real signal, elevated flat noise) that clears up by the next
acquisition, regardless of what registers are touched in between (tested:
varying `set_attributes()`/`set_measurement_mode()`/`flush()` between the
two acquisitions didn't change the outcome — the second one was always
better).

**Fix (not yet tested on hardware):** `set_measurement_mode()`
(`helicam.py`) now triggers and discards one throwaway acquisition itself,
right after switching modes -- `warmup: bool = True` parameter, on by
default for every mode, with `warmup=False` to opt out. This applies
uniformly (steady, rawIQ, amplitude, smooth_amplitude, minE) since the
underlying cause (settling after a mode switch) isn't specific to CamMode
3 — we just happened to only be able to *measure* it there, via mode 1's
convenient multi-step sweep giving an unsettled-vs-settled comparison for
free. `mode2_lockin()`'s manual "acquire twice, discard the first"
workaround (added to test this before the real fix existed) was removed
now that `set_measurement_mode()` handles it.

**Cost/caveat:** every `set_measurement_mode()` call now costs one extra
full acquisition (several seconds for volume modes at `SensNFrames=256`).
Modes 5 and 6 call it repeatedly in a sweep loop (10 and 4 iterations) --
this roughly doubles their runtime. Left as-is (correctness over speed,
and it's exactly the scenario this fix targets), but worth passing
`warmup=False` there if the extra time becomes annoying and the sweep
step's own settings changes are trusted not to need it.

**To test:** re-run mode 1 and mode 2 at the same `t_acquire_us` and
confirm the steady frames now look comparable; confirm mode 2's rawIQ/
amplitude/smooth_amplitude first-acquisitions (which we've never directly
verified against a "settled" comparison the way steady was) look
reasonable now too.

**Correction, not a new issue:** an earlier version of the CamMode-3 fix
above wrongly
also forced `crop_unphysical()` onto the CamMode 1/2 branch, on the
assumption that its `(292, 282)` output (instead of `(292, 280)`) was a
bug from a dropped crop call. It isn't — confirmed via
`heliSDK_programmer-manual_v1_2.md`'s own `metadata->dimSz` numbers that
CamMode 1/2 (292×282) and CamMode 4/7 (293×281) are the FPGA's genuine
native output sizes for those modes, pre-cropped on-device to something
other than `SENSOR_HEIGHT_USABLE`/`WIDTH_USABLE` (which only describes the
raw 300×300 sensor's own test-pixel border, and only applies to CamMode
0/3, the two modes that actually return the full raw frame). Forcing the
crop there crashed (`ValueError: no axis pair of shape (300, 300) found`)
-- reverted. `data_reformat()` now only crops for `cam_mode in (0, 3)`;
see the knowledge base for the full per-CamMode size table.

---

## 3. test the effectness of FWHMnFrame in smooth_amplitude run

---

## 4. Uncommitted state — nothing has been committed yet

Current `git status --short`: modified `TODO.md`, `moke/devices/helicam.py`,
`moke/devices/helicam_test.py`; deleted `moke/devices/test.py`; new
`moke/devices/manual_test.py` and a `moke/devices/helicam_test_data/
260811-lockin mode/` results folder. None of this is committed — do that
(or review/discard) before considering this work "saved" in git history.

---

## 5. Open design questions (not blocking, but worth deciding)

See knowledge base's "Open questions" section for the full list. Top ones:
- Now that CamMode-3 reports channel 1 (short exposure) only instead of
  summing (§2 above), is that the right long-term choice, or should it
  become a real HDR merge (favor long exposure unless saturated, fall
  back to scaled short) once low-light dynamic range matters more than
  simplicity?
- `SensNavM2`/`SensTqp` gap in `STEADY_SETTINGS` vs. the heliViewer
  GUI-confirmed reference — not applied/tested.
- Now that `auto_expose()`'s known bugs are effectively resolved
  (see `open_issue_helicam.md` #9), should mode 1 switch from its
  hardcoded exposure sweep back to using `auto_expose()`?
