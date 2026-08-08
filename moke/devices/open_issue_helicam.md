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
