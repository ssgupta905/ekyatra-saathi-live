"""A clock whose date is set from outside.

The demo needs to show days passing in minutes. Whatever drives the demo sets
the date here; everything that reads time through the `Clock` port follows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime


class ControlledClock:
    def __init__(self, start: date) -> None:
        self._today = start

    def today(self) -> date:
        return self._today

    def now(self) -> datetime:
        return datetime.now(UTC)

    def set(self, day: date) -> None:
        self._today = day
