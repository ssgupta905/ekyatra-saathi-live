"""The day a family is told to set out: ready, but not weeks before a booked visit."""

from __future__ import annotations

from datetime import date

from saathi.domain.enums import StepKind, StepStatus
from saathi.domain.models import CareStep
from saathi.planner import tools

TODAY = date(2026, 11, 27)


def _scan(scheduled_for: date | None) -> CareStep:
    return CareStep(
        id="s1",
        patient_id="P1",
        kind=StepKind.SCAN,
        status=StepStatus.SCHEDULED,
        scheduled_for=scheduled_for,
    )


def test_a_visit_booked_days_away_is_not_travelled_for_tomorrow() -> None:
    assert tools.travel_date_for(_scan(date(2026, 12, 1)), [], TODAY) == date(2026, 11, 30)


def test_a_visit_booked_for_tomorrow_still_means_setting_out_tomorrow() -> None:
    assert tools.travel_date_for(_scan(date(2026, 11, 28)), [], TODAY) == date(2026, 11, 28)


def test_a_visit_already_due_never_pushes_the_date_into_the_past() -> None:
    assert tools.travel_date_for(_scan(date(2026, 11, 20)), [], TODAY) == date(2026, 11, 28)


def test_a_step_with_no_booking_keeps_the_earliest_safe_date() -> None:
    assert tools.travel_date_for(_scan(None), [], TODAY) == date(2026, 11, 28)
