"""Pretend timetables, so the screen can be shown without a key.

Every option says `source="demo"` and the screen says so. Refused in
production (config). The buses and stops are invented and must never be read as
real: they exist to show how a family is guided, nothing more.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ...domain.itinerary import FareBasis, RouteOption, Step, StepMode
from ...ports.routes import Place


class DemoRoutes:
    name = "demo"

    async def options(
        self,
        origin: Place,
        destination: Place,
        *,
        mode: str,
        arrive_by: datetime | None = None,
        depart_at: datetime | None = None,
    ) -> list[RouteOption]:
        base = (depart_at or datetime.now(UTC)).replace(
            second=0, microsecond=0
        ) + timedelta(minutes=20)

        def at(m: int) -> datetime:
            return base + timedelta(minutes=m)

        if mode == "driving":
            return [
                RouteOption(
                    id="demo-car",
                    steps=(Step(mode=StepMode.TAXI, minutes=38, metres=14_200),),
                    minutes=38,
                    departs=at(0),
                    arrives=at(38),
                    source="demo",
                )
            ]
        return [
            RouteOption(
                id="demo-bus-direct",
                steps=(
                    Step(mode=StepMode.WALK, minutes=7, metres=500, note="Walk to the stop"),
                    Step(
                        mode=StepMode.BUS, line="A-12", towards="Hospital Gate",
                        board_at="Station Road stop", get_off_at="Hospital Gate",
                        stops=11, departs=at(7), arrives=at(58), minutes=51,
                    ),
                    Step(mode=StepMode.WALK, minutes=3, metres=200),
                ),
                minutes=61, departs=at(0), arrives=at(61), fare_paise=2000,
                fare_basis=FareBasis.SERVICE, source="demo",
            ),
            RouteOption(
                id="demo-metro-bus",
                steps=(
                    Step(
                        mode=StepMode.WALK, minutes=12, metres=900,
                        note="Walk to the metro station",
                    ),
                    Step(
                        mode=StepMode.METRO, line="Line 1", towards="Central",
                        board_at="City Station", get_off_at="Central",
                        stops=6, departs=at(12), arrives=at(30), minutes=18,
                    ),
                    Step(
                        mode=StepMode.BUS, line="C-7", towards="Hospital Gate",
                        board_at="Central bus bay", get_off_at="Hospital Gate",
                        stops=4, departs=at(36), arrives=at(48), minutes=12,
                    ),
                    Step(mode=StepMode.WALK, minutes=3, metres=200),
                ),
                minutes=51, departs=at(0), arrives=at(51), fare_paise=3500,
                fare_basis=FareBasis.SERVICE, source="demo",
            ),
            RouteOption(
                id="demo-bus-long-walk",
                steps=(
                    Step(mode=StepMode.WALK, minutes=14, metres=1000),
                    Step(mode=StepMode.BUS, line="D-3", towards="Market", board_at="Old Town stop",
                         get_off_at="Market", stops=9, departs=at(14), arrives=at(44), minutes=30),
                    Step(mode=StepMode.WALK, minutes=17, metres=1300, note="Walk to the hospital"),
                ),
                minutes=61, departs=at(0), arrives=at(61), fare_paise=1500,
                fare_basis=FareBasis.SERVICE, source="demo",
            ),
        ]

    async def close(self) -> None:
        pass
