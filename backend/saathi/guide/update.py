"""What changed between two guides, in the terms a family would care about."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.guide import FamilyAction, JourneyGuide, StageKind, StageState


@dataclass(frozen=True)
class GuideUpdate:
    #: Stages that became done since last time.
    finished: tuple[StageKind, ...]
    #: The stage the family should now look at, and what they should do about it.
    now: StageKind | None
    action: FamilyAction
    done: int
    total: int


def guide_update(before: JourneyGuide, after: JourneyGuide) -> GuideUpdate | None:
    """None when nothing a family needs to hear has changed."""
    was_done = {s.id for s in before.stages if s.state is StageState.DONE}
    was_problem = {s.id for s in before.stages if s.state is StageState.PROBLEM}
    finished = tuple(
        s.kind for s in after.stages if s.state is StageState.DONE and s.id not in was_done
    )
    now = next((s for s in after.stages if s.id == after.now_stage_id), None)
    new_problem = now is not None and now.state is StageState.PROBLEM and now.id not in was_problem
    moved_on = after.now_stage_id != before.now_stage_id
    if not finished and not new_problem and not moved_on:
        return None
    return GuideUpdate(
        finished=finished,
        now=now.kind if now else None,
        action=now.action if now else FamilyAction.NONE,
        done=after.done,
        total=after.total,
    )
