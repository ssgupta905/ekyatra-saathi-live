"""Build the journey guide. Pure: no I/O, no clock, no model."""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.enums import (
    REPORT_STEPS,
    Decision,
    ReadinessKind,
    ReadinessStatus,
    StepKind,
    StepStatus,
)
from ..domain.guide import (
    FamilyAction,
    GuideStage,
    JourneyGuide,
    StageKind,
    StageState,
    StageStep,
)
from ..domain.models import CareStep, EvidenceRef, ReadinessItem, VisitPlan
from ..domain.pathway import Pathway

_DONE = frozenset({StepStatus.COMPLETED, StepStatus.RESULT_AVAILABLE})

#: Partner kinds in the order a family meets them, and the stage each becomes.
_PARTNER_STAGES: tuple[tuple[ReadinessKind, StageKind], ...] = (
    (ReadinessKind.INSURANCE, StageKind.INSURANCE),
    (ReadinessKind.MEDICINE, StageKind.PHARMACY),
    (ReadinessKind.TRANSPORT, StageKind.RIDE),
    (ReadinessKind.STAY, StageKind.STAY),
)


def _ancestors(pathway: Pathway, kind: StepKind) -> set[StepKind]:
    """Every step the target depends on, directly or through others."""
    found: set[StepKind] = set()
    frontier = [kind]
    while frontier:
        current = frontier.pop()
        for parent, child in pathway.edges:
            if child is current and parent not in found:
                found.add(parent)
                frontier.append(parent)
    return found


def _evidence(plan: VisitPlan | None, *record_ids: str) -> tuple[EvidenceRef, ...]:
    if plan is None:
        return ()
    wanted = set(record_ids)
    return tuple(ref for ref in plan.evidence if ref.source_record_id in wanted)


def _step_row(step: CareStep) -> StageStep:
    return StageStep(kind=step.kind, done=step.status in _DONE, on=step.scheduled_for)


def _partner_stage(
    kind: ReadinessKind,
    stage: StageKind,
    items: dict[ReadinessKind, ReadinessItem],
    plan: VisitPlan | None,
    go: bool,
) -> GuideStage:
    item = items.get(kind)
    if item is None:
        return GuideStage(
            id=stage.value, kind=stage, state=StageState.UPCOMING, action=FamilyAction.NOTHING_YET
        )
    evidence = _evidence(plan, item.id)
    if item.status is ReadinessStatus.READY:
        pickup = stage is StageKind.RIDE and go
        return GuideStage(
            id=stage.value, kind=stage, state=StageState.DONE, party=item.party,
            detail=item.detail,
            action=FamilyAction.BE_READY_FOR_PICKUP if pickup else FamilyAction.NONE,
            evidence=evidence,
        )  # fmt: skip
    if item.status is ReadinessStatus.BLOCKED:
        return GuideStage(
            id=stage.value, kind=stage, state=StageState.PROBLEM, party=item.party,
            detail=item.detail, action=FamilyAction.WAIT_FOR_TEAM, evidence=evidence,
        )  # fmt: skip
    # Pending, or nobody has said: the family has nothing to do either way.
    return GuideStage(
        id=stage.value, kind=stage, state=StageState.WAITING, party=item.party,
        detail=item.detail, action=FamilyAction.NOTHING_YET, evidence=evidence,
    )  # fmt: skip


def build_guide(
    *,
    patient_id: str,
    pathway: Pathway,
    steps: Sequence[CareStep],
    plan: VisitPlan | None,
    items: Sequence[ReadinessItem],
    needs: Sequence[ReadinessKind],
) -> JourneyGuide:
    """The ordered chain for one family.

    `needs` is which other parties this journey depends on (from the pathway and
    how far the family lives), so a stage shows as "coming" before anyone has been
    asked. A party that was asked for something not in `needs` still appears.
    """
    by_id = {s.id: s for s in steps}
    target = by_id.get(plan.target_step_id) if plan else None
    if target is None:
        target = next((s for s in steps if s.kind is pathway.default_target), None)
    go = plan is not None and plan.decision is Decision.GO
    decision = plan.decision.value if plan else None
    if target is None:
        return JourneyGuide(
            patient_id=patient_id, decision=decision, stages=(), now_stage_id=None, done=0, total=0
        )

    prerequisites = _ancestors(pathway, target.kind)
    kinds = {s.kind: s for s in steps}
    stages: list[GuideStage] = []

    # 1. The tests that have to happen first.
    test_kinds = sorted(prerequisites - REPORT_STEPS, key=lambda k: k.value)
    tests = [kinds[k] for k in test_kinds if k in kinds]
    if tests:
        everything_done = all(s.status in _DONE for s in tests)
        stages.append(
            GuideStage(
                id=StageKind.TESTS.value, kind=StageKind.TESTS,
                state=StageState.DONE if everything_done else StageState.UPCOMING,
                action=FamilyAction.NONE if everything_done else FamilyAction.NOTHING_YET,
                steps=tuple(_step_row(s) for s in tests),
                evidence=_evidence(plan, *(s.id for s in tests)),
            )
        )  # fmt: skip

    # 2. The reports, which the lab holds.
    report_kinds = sorted(prerequisites & REPORT_STEPS, key=lambda k: k.value)
    reports = [kinds[k] for k in report_kinds if k in kinds]
    if reports:
        ready = all(s.status in _DONE for s in reports)
        windows = [
            b.expected_ready for b in (plan.blocked_by if plan else ())
            if b.expected_ready is not None and b.step_id in {s.id for s in reports}
        ]  # fmt: skip
        stages.append(
            GuideStage(
                id=StageKind.REPORTS.value, kind=StageKind.REPORTS,
                state=StageState.DONE if ready else StageState.WAITING,
                action=FamilyAction.NONE if ready else FamilyAction.NOTHING_YET,
                party=None if ready else "the lab",
                steps=tuple(_step_row(s) for s in reports),
                window=(min(w.earliest for w in windows), max(w.latest for w in windows))
                if windows and not ready else None,
                evidence=_evidence(plan, *(s.id for s in reports)),
            )
        )  # fmt: skip

    # 3. Everyone else the journey depends on.
    by_kind = {i.kind: i for i in items}
    for kind, stage in _PARTNER_STAGES:
        if kind in needs or kind in by_kind:
            stages.append(_partner_stage(kind, stage, by_kind, plan, go))

    # 4. What to carry, once the family is cleared to travel.
    if go and plan is not None:
        stages.append(
            GuideStage(
                id=StageKind.DOCUMENTS.value, kind=StageKind.DOCUMENTS, state=StageState.UPCOMING,
                action=FamilyAction.KEEP_DOCUMENTS_READY, bring=plan.what_to_bring,
            )
        )  # fmt: skip
    else:
        stages.append(
            GuideStage(
                id=StageKind.DOCUMENTS.value, kind=StageKind.DOCUMENTS, state=StageState.UPCOMING,
                action=FamilyAction.NOTHING_YET,
            )
        )  # fmt: skip

    # 5. The visit: the only place a date can appear.
    visit_done = target.status in _DONE
    stages.append(
        GuideStage(
            id=StageKind.VISIT.value, kind=StageKind.VISIT,
            state=StageState.DONE if visit_done else StageState.UPCOMING,
            action=FamilyAction.NONE if visit_done
            else FamilyAction.GO_TO_FIRST_STOP if go else FamilyAction.NOTHING_YET,
            steps=(_step_row(target),),
            on=plan.travel_on if go and plan else None,
            first_stop=plan.where_to_go_first if go and plan else None,
            evidence=_evidence(plan, target.id),
        )
    )  # fmt: skip

    # 6. A repeating pathway keeps going; the next one is never dated in advance.
    if pathway.recurrence is not None and target.kind is pathway.recurrence.kind:
        stages.append(
            GuideStage(
                id=StageKind.NEXT_SESSION.value, kind=StageKind.NEXT_SESSION,
                state=StageState.UPCOMING, action=FamilyAction.NONE,
            )
        )  # fmt: skip

    now = next((s for s in stages if s.state is not StageState.DONE), None)
    if now is not None:
        stages = [s.model_copy(update={"is_now": s.id == now.id}) for s in stages]
    return JourneyGuide(
        patient_id=patient_id,
        decision=decision,
        stages=tuple(stages),
        now_stage_id=now.id if now else None,
        done=sum(1 for s in stages if s.state is StageState.DONE),
        total=len(stages),
    )
