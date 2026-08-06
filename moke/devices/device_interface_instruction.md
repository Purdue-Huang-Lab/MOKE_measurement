# Device-interfacing code — guidelines

Rules for anything in `moke/devices/`. The goal: every piece of hardware looks the
same from the outside, so `acquire.py`'s run loop and a `DeviceStack` context
manager can treat a camera, a delay stage, and a K-cube identically, and so a
crash or Ctrl-C mid-run never leaves hardware in a stuck state.

---

## 1. Every device implements the `Device` ABC

```python
class Device(ABC):
    @abstractmethod
    def open(self) -> None: ...
    @abstractmethod
    def close(self) -> None: ...
    @abstractmethod
    def status(self) -> dict: ...

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc_info):
        self.close()
```

- `open()` establishes the connection and puts the device in a known state. It
  raises on failure — never returns a sentinel the caller might forget to check.
- `close()` must be safe to call twice (e.g. after a failed `open()`, or during
  `__exit__` following an exception in `open()` itself). Log and return rather
  than raising if already closed.
- `status()` returns a small dict of live, cheap-to-read state (e.g.
  `{"open": True, "position": 12.3}`) — used for startup logging and the
  preview panel, not a substitute for a real telemetry system.
- Don't override `__enter__`/`__exit__` per device unless there's a real reason
  (e.g. partial-state cleanup); the base implementation covers the common case.

## 2. Fail loud, fail at the boundary

- Never swallow an exception with `except Exception: print(e)`. That pattern
  exists in the current `stage.py`/`kcube.py` (copied from
  `optical_devices_toolbox`) and is exactly what this rewrite must not repeat —
  it converts a hardware fault into a silently-wrong position/frame instead of
  a stopped run.
- Guard every hardware call with an explicit "is this device open" check and
  raise `RuntimeError` if not — see `HeliCamC3._require_open()` for the
  pattern to reuse. Don't let a call on a closed device segfault into ctypes
  or return garbage.
- Validate arguments before they reach ctypes: range-check, raise
  `ValueError` with the value and the valid range in the message (see
  `set_internal_demod`, `set_acquire_time` in `helicam.py` for the tone to
  match).
- A wrong-but-plausible hardware response is worse than a crash. If the SDK
  distinguishes "call failed" from "call succeeded but value is implausible"
  (e.g. `HE_Open`'s return code vs. its handle, documented in
  `HeliCamC3.open()`), trust the documented signal, not the naive one — and
  write down *why* in a comment, since it's the kind of thing that looks like
  a bug to the next reader.

## 3. Units and naming

- Every parameter and attribute name that carries a physical quantity encodes
  its unit: `t_acquire_us`, `f_demod_hz`, `pos_mm`, `delay_ps`. No bare `t`,
  `f`, `pos` — the plan's config (§5.2) does this throughout and device code
  should match it so a value can't cross a device boundary and silently change
  units.
- Match the vocabulary in the plan doc exactly where it names something
  (`move_ps`, `wait_settle`, `arm`, `read_frame`, `set_demod_clock`) — these
  names are referenced elsewhere (acquire.py's run loop, the invariant
  asserts in §5.4) and a rename here is a rename everywhere.

## 4. Logging, not print

- One module-level logger: `_log = logging.getLogger(__name__)`. No bare
  `print()` in device code (the existing `stage.py`/`kcube.py` prints are
  legacy and should be converted, not extended).
- `_log.debug` for per-call chatter (register writes, polling), `_log.info`
  for lifecycle events (open/close/mode changes) and calibration numbers,
  `_log.warning` for recoverable oddities (stale-frame flush, retry), never
  `_log.error` + swallow — if it's an error, raise.
- On `open()`, log anything a future debugging session will want and can only
  be read from the live device: measured readout time, firmware/serial ID,
  soft limits. `HeliCamC3` does this for frame duration; `stage.py`/`kcube.py`
  don't yet and should on their rewrite.

## 5. Docstrings

- NumPy style (`Parameters` / `Returns` / `Raises` / `Notes`), matching
  `helicam.py`. Every public method gets one; private helpers (`_foo`) get a
  one-liner only if the name doesn't already say it.
- Use `Notes` for hardware quirks that would otherwise look like a bug:
  return-code conventions that don't mean what they look like, register
  formulas, calibration constants tied to a specific serial number and why
  they'd need retuning on different hardware. `HeliCamC3.open()` and
  `estimate_acquire_time()` are the reference examples.

## 6. Blocking, settling, and timeouts

- Motion/settling calls (`wait_settle`, homing, K-cube moves) block the
  caller — that's expected and documented, not hidden. Don't silently launch
  a background thread inside a device method; if the run loop needs
  non-blocking motion, that's a decision for `acquire.py`, made explicitly.
- Every blocking call has a bounded timeout — see `HeliCamC3.flush()`'s
  `max_frames` bound and the reasoning in its docstring (free-running mode
  makes an unbounded loop hang forever). No `while True` waiting on hardware
  state without a timeout and a clear failure path.
- Don't estimate a settle time and just `sleep()` it as the only
  confirmation (current `stage.py.goto_d` does this). Poll the device's own
  "am I there yet" state where the SDK exposes one; where it doesn't, treat
  the sleep-based estimate as a documented limitation, not a solved problem.

## 7. Context manager discipline

- All device state changes that need cleanup (mode switches, acquisition
  armed, motion in progress) must be undoable from `close()`, including when
  `close()` runs because `__exit__` is unwinding an exception. Assume `close()`
  can be called from a state where the last operation didn't finish cleanly.
- Never assume the caller wraps you in `with` — but design so that they
  always should. `DeviceStack` (moke/acquire.py, not yet written) is what
  guarantees every exit path — including Ctrl-C — closes every open device;
  individual device classes just need to make that safe to call.

## 8. Simulator parity

- Any public method added to a real device should be plausible to fake in
  `sim.py` (§5.11) — return synthetic data of the right shape/dtype, not just
  `pass`. If a method can't be meaningfully simulated, that's worth a comment
  explaining why, since it means that code path won't get exercised by the
  offline test loop.

## 9. Before merging a device change

- [ ] Subclasses `Device`, implements `open`/`close`/`status`
- [ ] Every hardware call is guarded by an open-check
- [ ] No bare `except Exception: print(...)`
- [ ] Units in every physical-quantity name
- [ ] `_log`, not `print`
- [ ] NumPy-style docstrings, `Notes` for anything surprising
- [ ] Blocking calls have a bound/timeout
- [ ] `close()` is idempotent and safe after a partial/failed `open()`
