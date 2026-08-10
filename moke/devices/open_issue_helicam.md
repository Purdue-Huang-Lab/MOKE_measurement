# helicam.py — open issues

Tracking doc for gaps and unresolved questions in `helicam.py`, found while
building it out against `device_interface_instruction.md` and the
tr-MOKE plan. Checked against the vendor docs in
`archive/helicam_document_temp/documents/md version/` (manual, register
description, programmer manual) on 2026-08-08 — see status per item below.

## 1. `arm(phi_us)` — no trigger-start-delay register found

`arm(n_demod, phi_us)` raises `NotImplementedError` for any `phi_us != 0`.
No register in any of the three vendor docs implements "wait φ µs after the
trigger edge, then start accumulating" (plan doc §3's φ₁/φ₂). Closest
candidates checked and ruled out:
- `SensDeltaExp` — trims sensor exposure *within* a quarter period, not a
  trigger-to-start delay.
- `TrigOnPos*` — position-based (encoder) triggering, not a time delay.

**Needed to close:** the doxygen `.chm` API reference (not in the repo) or a
direct answer from Heliotis — this is also plan doc §6's open item
("confirm heliCam C3 frame-sync/trigger output").

## 2. `set_demod_clock(external=True)` — no external demod-clock register found

Always raises `NotImplementedError`. No register anywhere locks the
demodulation clock to an external reference (e.g. the PEM 2f output) — this
is plan doc §3's one **mandatory** hard timing constraint, so it's blocking
for real lock-in acquisition, not cosmetic.
- `TrigFreeExtN` is the acquisition **trigger** source, not the demod clock
  — confirmed not to be a substitute, do not conflate them.
- `EnSynFOut`/OUT3 is an *output* (camera emits fd for other equipment to
  sync to) — the reverse of what's needed here.

**Needed to close:** same as #1 — doxygen `.chm` or Heliotis.

## 3. CamMode 3 (intensity) format mismatch — untested

The programmer's manual documents CamMode 3 as using `CamDataFmt = DF_Hf`
(32-bit float), with the SDK doing dark-frame subtraction + HDR combination
on-device. The code instead requests `DF_I16Q16` (raw I/Q) and reimplements
that reduction in `to_numpy()`.

This is a **known divergence, not a confirmed bug**: `STEADY_SETTINGS`'s
values are recorded as verified end-to-end on real hardware (serial
1002688069) using the current `DF_I16Q16` path. Do not switch to `DF_Hf`
without testing against real hardware first — it may break a working path,
or it may be the actually-correct fix. See `_MODE_TO_FMT` in helicam.py for
the inline note.

## 4. `HE_Open` return-code vs. handle — unverified against docs

`open()`'s docstring claims `HE_Open` returns non-zero (1) on a healthy open
for this camera, and that the handle (not the return code) is the real
success/failure signal. None of the three vendor docs document `HE_Open`'s
return-code convention at all. This is currently based on field
observation only. Not contradicted by the docs, just not confirmable from
them.

## 5. `AllocCamData` trailing args — unverified

The three trailing `0, 0, 0` args in `self._lib.AllocCamData(1, fmt, 0, 0, 0)`
are not explained in any of the three docs — the programmer's manual defers
to the doxygen `.chm` for this call's exact argument semantics.

## 6. `set_roi` — commented out, unconfirmed capability

Was a no-op stub with a full docstring pretending it worked (silent
wrong-but-plausible behavior). Commented out in helicam.py rather than left
active, since it's unknown whether/how a hardware ROI is even settable on
this camera. Not currently called anywhere else in the repo. Note that the
plan's `roi_signal`/`roi_reference` (config §5.2) look like **software-side**
post-acquisition windowing on the full frame, not a hardware sensor crop —
worth deciding whether a hardware `set_roi` is needed at all before
re-implementing it.

## 7. Not implemented — stubs, no hardware capability confirmed yet

These `raise NotImplementedError` and are not wired to any hardware call:
- `set_internal_trigger(f_hz, phase)`
- `get_trigger_status()`
- `stream_on_trigger(t_acquire_s, n_frames)`

## 8. Known-wrong callers already fixed

- `rig.py`'s `camera_acquire()` called a nonexistent `HeliCamC3.acquire()` —
  fixed to call `acquire_single()`.
- `helicam_test.py` still calls `cam.acquire()`, which does not exist on
  `HeliCamC3` — **left untouched deliberately** (explicit instruction not to
  touch this file). Whoever picks this file back up should either add an
  `acquire` alias or update the test to call `acquire_single()`.

## 9. `auto_expose()` — broken fallback + no recovery after a timeout

Found while debugging `helicam_test_data/helicam_test_000/run_log.txt`:
every "optimal frame" acquire in mode 1's gain sweep came back `None`. Two
separate bugs:

- **Broken fallback when the target can't be bracketed** (`auto_expose()`'s
  `if frac_hi < target_fraction:` branch, hit when the doubling search never
  reaches `target_fraction` before `t_max_us`): it returns `t_hi`/`frac_hi`
  from the *last* (failed) trial instead of the best real trial actually
  recorded in `table`. In the logged run, ~11 earlier trials (t=1..1024µs)
  produced valid frames, but `auto_expose` reported the broken ceiling
  exposure (t=16380µs, frac=0) as "optimal" anyway — so the caller's next
  `acquire_single()` at that setting timed out and returned `None`.
- **No recovery after an `Acquire()` timeout**: once one acquisition times
  out (`-116`), nothing resyncs the pipeline (no `AcqStop` toggle, no
  re-`set_measurement_mode()`) before the next trial. In that run, the first
  timeout hit mid-sweep at t=2048µs (gain=3.0), and every trial after that —
  across all three remaining gains, down to t=1µs — timed out for the rest
  of the run.

**Status: `auto_expose()` was rewritten** (channel0/channel1 ratio-based
saturation detection instead of an absolute intensity threshold against a
theoretical full scale — see
`archive/helicam_document/helicamC3_practical_knowledge_base.md` #3, and
`auto_expose()`'s own docstring). This resolves the first bug's *symptom*:
there is no more "pick the best `table` entry" fallback logic at all —
the geometric-doubling phase only ever returns a `t` it just successfully
measured (either the largest unsaturated `t` tried, via
`ceiling_not_found=True`, or the bisection-refined saturation onset), never
a failed trial's numbers.

The second bug (no pipeline resync after a timeout) is **not fixed** — a
failed acquisition still isn't recovered from. What changed is the
*consequence*: a failed trial now makes `auto_expose()` stop searching
immediately and return `ceiling_not_found=True` (fail clearly) instead of
continuing past it and returning a bogus "success" (fail silently). Still
worth fixing properly (resync via `AcqStop=1`→settings→`AcqStop=0`) so a
single timeout doesn't cut a search short.

**Workaround still in place:** `helicam_test.py` mode 1 still doesn't call
`auto_expose()` — it sweeps a fixed, hardcoded log-spaced exposure list
(`DEFAULT_MODE1_T_ACQUIRE_US_LIST`) at a single fixed gain (1x, best SNR,
`DdsGain=2`) instead. Now that `auto_expose()` has been reworked, it's
worth re-evaluating whether mode 1 should switch back to it — not yet
done.

**Needed to close:** add a resync/recovery step after a timeout, then
re-verify against real hardware before mode 1 goes back to using
`auto_expose()`.
