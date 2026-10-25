"""The simulation clock's pacing.

The demo needs to show days passing in minutes, because a pathology report
takes a week and a judge has ten minutes. This holds the *pace* — how many real
seconds a simulated day takes, whether it is running, how many days have
elapsed. The date itself lives in a `ControlledClock` (the `Clock` port's demo
adapter), so everything that reads time through the port follows this one.

It is deliberately dumb: it advances one day when told to. The runner owns the
timing; keeping that out of here means the whole world can be stepped
synchronously in a test with no sleeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..adapters.clock import ControlledClock


@dataclass
class SimulationClock:
    """A date that moves a day at a time, at a chosen wall-clock pace."""

    start: date
    #: Real seconds per simulated day. 4.0 means a week passes in half a minute.
    seconds_per_day: float = 4.0
    running: bool = False
    #: Simulated days elapsed since `start`. Survives a speed change.
    day: int = field(init=False, default=0)
    #: The date, as the rest of the system reads it.
    source: ControlledClock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.source = ControlledClock(self.start)

    @property
    def current(self) -> date:
        return self.source.today()

    def advance(self, days: int = 1) -> date:
        self.day += days
        self.source.set(self.start + timedelta(days=self.day))
        return self.current

    def reset(self, start: date | None = None) -> None:
        if start is not None:
            self.start = start
        self.day = 0
        self.source.set(self.start)

    def snapshot(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "current": self.current.isoformat(),
            "day": self.day,
            "seconds_per_day": self.seconds_per_day,
            "running": self.running,
        }


class WallClock:
    """The real calendar, shaped like `SimulationClock` so the runner needs no branch.

    Nothing here can be sped up, stepped or reset: `advance` only notes that
    another real day has been reached. `tick_seconds` is how often the runner
    looks again, since a "day" is no longer something it paces.
    """

    real = True
    running = True

    def __init__(self, source, tick_seconds: float = 300.0) -> None:
        self.source = source
        self.start = source.today()
        self.tick_seconds = tick_seconds
        self.seconds_per_day = 86400.0

    @property
    def day(self) -> int:
        return (self.current - self.start).days

    @property
    def current(self) -> date:
        return self.source.today()

    def advance(self, days: int = 1) -> date:
        return self.current

    def reset(self, start: date | None = None) -> None:
        raise RuntimeError("the real calendar cannot be reset")

    def snapshot(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "current": self.current.isoformat(),
            "day": self.day,
            "seconds_per_day": self.seconds_per_day,
            "running": True,
            "real": True,
        }
