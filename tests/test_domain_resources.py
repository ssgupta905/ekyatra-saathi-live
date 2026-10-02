"""Resource, Disruption and PlanOption carry logistics only, never content.

Same boundary rule as the rest of `domain/models.py`: frozen, extra-forbid,
and no field that could hold report content or a numeric ranking score.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError
from saathi.domain.enums import (
    Channel,
    Decision,
    DisruptionKind,
    FamilyMemberRole,
    Language,
    ResourceKind,
    Role,
    SourceSystem,
    StepKind,
)
from saathi.domain.models import (
    ApprovalDecision,
    Disruption,
    FamilyMember,
    MaintenanceCycle,
    PlanOption,
    Resource,
)


def test_resource_and_disruption_are_frozen():
    resource = Resource(
        id="MRI-2",
        kind=ResourceKind.MACHINE,
        display_name="MRI machine 2",
        hospital_id="H1",
        department="radiology",
    )
    disruption = Disruption(
        id="D1",
        resource_id=resource.id,
        kind=DisruptionKind.MACHINE_DOWN,
        raised_by=SourceSystem.HOSPITAL_FEED,
        raised_at=datetime(2026, 11, 12, 7, 40),
        unavailable_from=date(2026, 11, 12),
        unavailable_to=date(2026, 11, 14),
        note="MRI-2 out of service",
    )
    with pytest.raises(ValidationError):
        resource.display_name = "renamed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        disruption.note = "something else"  # type: ignore[misc]


def test_plan_option_has_tradeoffs_but_no_score_field():
    option = PlanOption(
        patient_id="P0000",
        target_step_id="P0000-scan",
        decision=Decision.GO,
        nights_added=0,
        extra_trips=0,
        dose_delay_days=0,
    )
    assert "score" not in type(option).model_fields
    assert "rank" not in type(option).model_fields
    with pytest.raises(ValidationError):
        PlanOption(**{**option.model_dump(), "score": 0.9})


def test_family_members_are_distinct_people_with_their_own_channel():
    caregiver = FamilyMember(
        id="F1",
        patient_id="P0000",
        role=FamilyMemberRole.CAREGIVER_PRIMARY,
        name="Vikash",
        phone="+91-caregiver",
        preferred_channel=Channel.WHATSAPP,
        language=Language.HINDI,
    )
    patient_voice = FamilyMember(
        id="F2",
        patient_id="P0000",
        role=FamilyMemberRole.PATIENT_SIMPLE,
        name="Shambhu",
        phone="+91-patient",
        preferred_channel=Channel.IVR,
        language=Language.HINDI,
    )
    assert caregiver.preferred_channel != patient_voice.preferred_channel


def test_approval_decision_names_who_decided_and_under_what_role():
    option = PlanOption(patient_id="P0000", target_step_id="P0000-scan", decision=Decision.GO)
    decision = ApprovalDecision(
        id="A1",
        patient_id="P0000",
        disruption_id="D1",
        option_summary=option,
        approved_by_role=Role.NAVIGATOR,
        approved_by="Seema Kamble",
        approved_at=datetime(2026, 11, 12, 9, 4),
    )
    assert decision.approved_by_role is Role.NAVIGATOR


def test_maintenance_cycle_defaults_match_the_brief():
    cycle = MaintenanceCycle(patient_id="P0001", dose_index=13, anchor_date=date(2026, 9, 1))
    assert cycle.total_doses == 17
    assert cycle.interval_days == 21


def test_care_step_resource_id_is_optional_for_non_bookable_steps():
    from saathi.domain.enums import StepStatus
    from saathi.domain.models import CareStep

    step = CareStep(id="s1", patient_id="P0000", kind=StepKind.CONSULT, status=StepStatus.SCHEDULED)
    assert step.resource_id is None
