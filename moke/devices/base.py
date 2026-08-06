"""
Device ABC: open/close/status, context-manager protocol.

Every device in moke/devices/ subclasses this so a `DeviceStack` (moke/acquire.py,
not yet written) can open and close arbitrary hardware uniformly -- including on
exceptions and Ctrl-C. See device_interface_instruction.md for the full set of
conventions this class underpins.
"""

from abc import ABC, abstractmethod


class Device(ABC):
    """Common lifecycle contract for all MOKE hardware wrappers."""

    @abstractmethod
    def open(self) -> None:
        """
        Establish the connection and put the device in a known state.

        Raises
        ------
        Exception
            On any failure to reach a usable state. Must never fail silently
            (no sentinel return values) -- callers rely on `open()` either
            succeeding completely or raising.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """
        Release the connection.

        Must be safe to call more than once, including after a failed or
        partial `open()`, and must not raise -- `close()` runs during
        exception unwinding in `DeviceStack`, where a second exception would
        mask the first.
        """
        ...

    @abstractmethod
    def status(self) -> dict:
        """
        Return a small dict of cheap, currently-known device state (e.g.
        ``{"open": True, "position_deg": 12.3}``).

        For startup logging and the preview panel -- not a substitute for a
        real telemetry/logging system, and not expected to issue new
        hardware queries beyond what's already cheap to read.
        """
        ...

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
