"""The real calendar, in the hospital's timezone."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


class SystemClock:
    """What production uses.

    The date is the hospital's, not the server's: a cloud host in another
    timezone must not decide that "today" is already tomorrow at the ward.
    """

    def __init__(self, timezone: str = "Asia/Kolkata") -> None:
        self._tz = ZoneInfo(timezone)

    def today(self) -> date:
        return datetime.now(self._tz).date()

    def now(self) -> datetime:
        return datetime.now(self._tz)
