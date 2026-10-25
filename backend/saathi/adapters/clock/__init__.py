"""Clock adapters: the real calendar, and one a simulator can set."""

from .controlled import ControlledClock
from .system import SystemClock

__all__ = ["ControlledClock", "SystemClock"]
