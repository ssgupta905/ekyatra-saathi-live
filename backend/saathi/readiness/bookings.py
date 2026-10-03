"""A booking is a fact, not a prediction.

`conformal.py` answers "when will this report land?", which is a forecast and
earns a coverage guarantee. This module answers a different question — "when is
this step going to happen?" — and for a *booked* step the answer is not a
forecast at all. The hospital has committed to a date; the right interval is
that single day, with no spread, because there is nothing to be uncertain about.

Why this matters more than it looks: without it, a scan that is merely scheduled
has no window, `decide()` sees an unbounded blocker and returns UNCERTAIN, and a
family whose entire journey is booked and confirmed is told there is no date.
That is wrong in the expensive direction — it withholds a trip that should
happen.

The inverse carries the real weight. A booking on a resource that is **down** is
not a fact either; it is a date the hospital can no longer honour. Returning
`None` there is what makes a disruption bite: the plan falls to UNCERTAIN the
moment the MRI breaks, and stays there until something re-places the step.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from ..domain.enums import REPORT_STEPS, StepStatus
from ..domain.models import CareStep, Disruption, ReadinessWindow

#: Statuses where a date on the record is a commitment rather than a guess.
BOOKED = frozenset({StepStatus.SCHEDULED})


def is_cancelled_by(step: CareStep, disruptions: Iterable[Disruption]) -> bool:
    """True when an active disruption covers this step's resource and date.

    A step with no `resource_id` books against nothing in particular and cannot
    be cancelled this way — only named resources break.
    """
    if step.resource_id is None or step.scheduled_for is None:
        return False
    for disruption in disruptions:
        if disruption.resource_id != step.resource_id:
            continue
        if step.scheduled_for < disruption.unavailable_from:
            continue
        if disruption.unavailable_to is not None and step.scheduled_for > disruption.unavailable_to:
            continue
        return True
    return False


def window_from_booking(
    step: CareStep,
    disruptions: Iterable[Disruption] = (),
) -> ReadinessWindow | None:
    """The day a booked step is committed to, as a zero-width window.

    `calibrated=True` and `alpha=0.0` are honest here: the interval covers the
    true date with certainty *conditional on the booking holding*, which is
    exactly the condition `is_cancelled_by` checks first. `n_calibration=0`
    records that no history went into it — this came from a record, not a model.

    Returns None for report steps (those are `conformal.py`'s job), for steps
    that are not booked, and for bookings a live disruption has invalidated.
    """
    if step.kind in REPORT_STEPS:
        return None
    if step.status not in BOOKED or step.scheduled_for is None:
        return None
    if is_cancelled_by(step, disruptions):
        return None
    return ReadinessWindow(
        step_id=step.id,
        earliest=step.scheduled_for,
        latest=step.scheduled_for,
        alpha=0.0,
        calibrated=True,
        n_calibration=0,
    )


def is_booking_window(window: ReadinessWindow | None) -> bool:
    """Whether a window came from a booking rather than from the model.

    Used by the console to say "booked" instead of quoting a coverage level a
    booking does not have.
    """
    return (
        window is not None
        and window.n_calibration == 0
        and window.earliest == window.latest
        and window.alpha == 0.0
    )


def first_free_date(
    resource_id: str | None,
    disruptions: Iterable[Disruption],
    not_before: date,
) -> date:
    """The earliest date on or after `not_before` that this resource is free.

    Walks forward past every disruption window covering the resource. A
    resource with no disruptions, or a step booked against no named resource,
    is free immediately.
    """
    if resource_id is None:
        return not_before

    windows = [d for d in disruptions if d.resource_id == resource_id]
    candidate = not_before
    moved = True
    # Re-check from the start after each move: windows may overlap or chain.
    while moved:
        moved = False
        for disruption in windows:
            if candidate < disruption.unavailable_from:
                continue
            if disruption.unavailable_to is None:
                # Open-ended: the resource is not coming back on a known date,
                # so there is no free date to offer.
                raise NoFreeDate(resource_id)
            if candidate <= disruption.unavailable_to:
                candidate = disruption.unavailable_to + timedelta(days=1)
                moved = True
    return candidate


class NoFreeDate(LookupError):
    """Raised when a resource is out indefinitely, so no date can be offered."""

    def __init__(self, resource_id: str) -> None:
        super().__init__(f"{resource_id} has no known return date")
        self.resource_id = resource_id
