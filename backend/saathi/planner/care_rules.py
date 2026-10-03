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
    options: Sequence[PlanOption], cycle: MaintenanceCycle | None
) -> tuple[PlanOption, ...]:
    """Drop any option a hard rule rejects, silently — never shown, never
    presented-then-blocked."""
    if cycle is None:
        return tuple(options)
    return tuple(o for o in options if echo_before_every_fourth_dose(o, cycle))



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
