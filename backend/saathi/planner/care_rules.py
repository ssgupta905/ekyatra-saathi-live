"""Hard care-team rules that remove an option before it is ever shown.

Distinct from `language.guard`, which re-checks rendered *text* against an
already-chosen plan. This module runs earlier and guards *options*: a
candidate that would break a rule like "echo before every fourth dose" never
reaches the navigator or doctor's list at all, exactly as the brief
describes ("Guard removes it from the list") rather than the guard blocking
a message about it afterwards.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from ..domain.enums import StepKind
from ..domain.models import MaintenanceCycle, PlanOption
from . import tools
from .search import Considered, Search, Verdict


def echo_before_every_fourth_dose(option: PlanOption, cycle: MaintenanceCycle) -> bool:
    """True when `option` is fine under the echo-gate rule.

    A maintenance-dose option that goes ahead (GO) without its echo+review
    bundled, on a dose that requires one, violates the rule. Step ids follow
    this codebase's `<patient>-<kind>` convention, so the echo step riding
    along shows up as a bundled id ending in the `ECHO_REVIEW` kind value.
    """
    if not tools.requires_echo_bundle(cycle.dose_index):
        return True
    if option.decision.value != "go":
        return True
    echo_suffix = f"-{StepKind.ECHO_REVIEW.value}"
    return any(step_id.endswith(echo_suffix) for step_id in option.bundled_step_ids)


CARE_RULES: tuple = (echo_before_every_fourth_dose,)


def filter_options(
    options: Sequence[PlanOption],
    cycle: MaintenanceCycle | None,
    search: Search | None = None,
) -> tuple[PlanOption, ...]:
    """Drop any option a hard rule rejects, silently — never shown, never
    presented-then-blocked.

    Silent to the *family*, which is the point: offering a date and then
    refusing it is worse than never offering it. But silent to everybody was
    an accident. Pass a `Search` and every candidate is recorded with the
    rule that killed it, for the reasoning log and the Console — two views of
    one search, and the filtering itself is unchanged.
    """
    kept = []
    for option in options:
        allowed = cycle is None or echo_before_every_fourth_dose(option, cycle)
        if allowed:
            kept.append(option)
        if search is not None:
            # `target_on` is the day the step itself lands on, which is what a
            # reader compares. `travel_on` answers a different question — when
            # they may set out — and for an unblocked plan is simply tomorrow,
            # so a log built on it would show every candidate as the same day.
            search.note(
                Considered(
                    ref=option.target_step_id,
                    on=option.target_on or option.travel_on,
                    verdict=Verdict.OFFERED if allowed else Verdict.CARE_RULE,
                    detail="" if allowed else "an echo is due before the next dose",
                    nights_added=getattr(option, "nights_added", None),
                    trips_added=getattr(option, "extra_trips", None),
                )
            )
    return tuple(kept)



def within_shift_tolerance(
    option: PlanOption,
    booked_on: date | None,
    tolerance_days: int | None,
) -> bool:
    """True when this option keeps the step inside the hospital's stated tolerance.

    A family asking to delay a dose by ten days is asking for something the
    schedule may not allow, and the right answer is not to refuse them — it is
    to keep the impossible option off the list so the doctor only chooses
    between things that are actually on offer.

    An unstated tolerance permits nothing to be filtered: without a number from
    the hospital there is no basis to remove an option, and inventing one here
    would be the same mistake as inventing the lead times was.
    """
    moved_to = option.target_on
    if tolerance_days is None or booked_on is None or moved_to is None:
        return True
    return abs((moved_to - booked_on).days) <= tolerance_days
