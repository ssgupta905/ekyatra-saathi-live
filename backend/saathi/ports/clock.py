"""Time, as the application sees it.

Nothing in the product reads the system date directly. In production the clock
is the real calendar in the hospital's timezone; in a demo, a simulator sets it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    def today(self) -> date:
        """The hospital's current calendar date."""
        ...

    def now(self) -> datetime:
        """The current moment, timezone-aware."""
        ...
