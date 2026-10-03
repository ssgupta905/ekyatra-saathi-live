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

