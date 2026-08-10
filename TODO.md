# TODO / handoff — heliCam C3 driver work (2026-08-10)

Everything below was written/reworked this session **against no hardware
run at all for the newest changes** — the author ran out of time to test
before handing off. Treat anything under "Needs a hardware run" as
unverified, even though it compiles clean (`py -m py_compile` only, on
both `moke/devices/helicam.py` and `moke/devices/helicam_test.py`).

Background reading, in order of how foundational they are:
1. `archive/helicam_document/helicamC3_practical_knowledge_base.md` — what
   we've learned about the hardware itself (sensor border pixels, ~512
   baseline, dual-channel HDR pair, frame-averaging rationale). Start here.
2. `moke/devices/open_issue_helicam.md` — open bugs/gaps in the driver code.
3. This file — what changed this session and what to check first.

---

## 1. Needs a hardware run — the `auto_expose()` rewrite

`HeliCamC3.auto_expose()` in `moke/devices/helicam.py` was completely
rewritten this session and **has never been run against the camera**.

**What it does now:** instead of comparing summed intensity against a
theoretical (and, per the knowledge base §2, actually wrong)
`2 * SENSOR_ADC_MAX` ceiling, it uses the ratio between CamMode 3's two
channels (channel 0 = long exposure, channel 1 = short exposure, ratio set
by `SensExpRatio`) as a self-calibrating saturation detector: the ratio
should hold near the nominal `SensExpRatio`-derived value
(`SENSEXPRATIO_SHORT_LONG`) while unsaturated, and drop once channel 0
starts clipping. See the function's own docstring and knowledge-base §5
for the full design rationale.

**To test:** `python -m moke.devices.helicam_test --mode 4` — this is the
isolated auto_expose() checkout mode, and its new summary plot
(`mode4_summary.png`) shows the channel0/channel1 ratio vs `t_acquire_us`
with the nominal ratio, detected saturation onset, and chosen exposure
marked. Things to sanity-check on the first real run:
- Does the ratio actually start near `nominal_ratio` (16, at the default
  `SensExpRatio=3`) at low `t_acquire_us`, and drop as expected once
  channel 0 saturates?
- `ratio_tol=0.1` (10% deviation) is an untested guess for what counts as
  "saturating" — may need tuning if it triggers too early/late on noise.
- Per-channel saturation stat is `np.percentile(channel, 99.9)` on the
  cropped 292×280 region — watch for `ceiling_not_found=True` (channel 0
  never saturates within `t_max_us`) or `floor_limited=True` (already
  saturating at `t_min_us=1.0`) in the log/result, both of which mean the
  search didn't behave as intended.
- Modes 2 and 3 also call `auto_expose()` internally — worth running those
  too once mode 4 looks right.

**Known remaining gap (not fixed, by design this session):** if an
acquisition times out mid-search, nothing resyncs the pipeline — the
search just stops and reports `ceiling_not_found=True` instead of
continuing on bad data. See `open_issue_helicam.md` #9.

---

## 2. Needs a hardware run — `crop_unphysical()` wired into the acquire path

`acquire_single()` and `acquire_avg()` now automatically crop every
returned frame from 300×300 down to the sensor's usable 292×280 center
(`crop_unphysical()`, `SENSOR_HEIGHT_USABLE`/`SENSOR_WIDTH_USABLE`), based
on the manual's documented border test-row/column spec. This has **not
been re-run on hardware since being added** — worth confirming saved
frames/plots from any mode now come out 292×280, not 300×300, and that
nothing downstream assumed the old 300×300 shape. `get_image_shape()` was
updated to return `(292, 280)` to match.

`save_raw_np()` deliberately does **not** crop (it's meant to preserve
the fully raw array for debugging) — that's intentional, not a gap.

---

## 3. Needs a hardware run — CamMode-3 frame reduction: mean, not sum

`data_reformat()`'s CamMode-3 branch now averages over frames (via the new
shared `_dark_subtract_channels()` helper) instead of summing, so
`SensNFrames` is purely a noise-averaging knob and doesn't change the
returned intensity scale. This *was* verified against hardware earlier in
the session (mode 5, `helicam_test_014`/`015` — see knowledge base §4) —
listed here only because `_dark_subtract_channels()` was refactored out as
a new shared method afterward and hasn't been indepedently re-tested since
that refactor. Low risk (it's the same math, just relocated), but not
re-verified.

---

## 4. New mode 6 — `SensExpRatio` sweep, tested once

`mode6_sensexpratio_sweep` (`--mode 6`) sweeps all 4 `SensExpRatio` values
and confirms channel 0 = long exposure, channel 1 = short exposure — this
**was** run once on hardware (`helicam_test_018`, see knowledge base §3b)
and is the empirical basis for the `auto_expose()` rewrite (§1 above). No
outstanding concern here, just noting it's the one piece of this session's
work that did get a real hardware check.

---

## 5. Uncommitted state — nothing in this session has been committed

`git status` currently shows (as of this session): modified
`moke/devices/helicam.py`, `moke/devices/helicam_test.py`,
`moke/devices/open_issue_helicam.md`; deleted `moke/rig.py` (moved to
`archive/rig.py` per explicit instruction — rig.py integration is
considered premature, "we are far from that stage"); new
`archive/helicam_document/` (the knowledge base doc) and
`moke/devices/test.py` (an ad-hoc analysis script, not part of the driver).
None of this has been committed — do that (or review/discard) before
considering the session's work "saved" in git history.

---

## 6. Open design questions (not blocking, but worth deciding)

See knowledge base's "Open questions" section for the full list. Top ones:
- Should `data_reformat()`'s CamMode-3 reduction do a real HDR merge
  (favor long exposure unless saturated, fall back to scaled short)
  instead of just summing channel 0 + channel 1? Currently still sums.
- `SensNavM2`/`SensTqp` gap in `STEADY_SETTINGS` vs. the heliViewer
  GUI-confirmed reference — not applied/tested.
- Now that `auto_expose()`'s two known bugs are effectively resolved
  (§1 above / `open_issue_helicam.md` #9), should mode 1 switch from its
  hardcoded exposure sweep back to using `auto_expose()`?
