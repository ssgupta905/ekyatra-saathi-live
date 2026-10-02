"""The simulation clock.

The demo needs to show days passing in minutes, because a pathology report
takes a week and a judge has ten minutes. The clock is the only thing that
compresses time — nothing else in the system knows it is being run fast, and
nothing else is allowed to.

It is deliberately dumb: it holds a date and a speed, and it advances one day
when told to. The runner owns the timing; keeping that out of here means the
whole world can be stepped synchronously in a test with no sleeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class SimulationClock:
    """A date that moves a day at a time, at a chosen wall-clock pace."""

    start: date
    #: Real seconds per simulated day. 4.0 means a week passes in half a minute.
    seconds_per_day: float = 4.0
    running: bool = False
    current: date = field(init=False)
    #: Simulated days elapsed since `start`. Survives a speed change.
    day: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.current = self.start

    def advance(self, days: int = 1) -> date:
        self.day += days
        self.current = self.start + timedelta(days=self.day)
        return self.current

    def reset(self, start: date | None = None) -> None:
        if start is not None:
            self.start = start
        self.day = 0
        self.current = self.start

    def snapshot(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "current": self.current.isoformat(),
            "day": self.day,
            "seconds_per_day": self.seconds_per_day,
            "running": self.running,
        }
