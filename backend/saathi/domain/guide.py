"""One journey, in order, for the people living it.

A `JourneyGuide` turns what the planner knows (the care steps, the plan, what
every other party has said) into a chain a family can follow: what is done, what
is being worked on, who has it, and what they themselves need to do now. It is
read-only and derived; nothing here is stored or decided.

Dates appear in exactly one place: the visit, and only when the plan is a GO.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .enums import StepKind
from .models import EvidenceRef


class StageKind(StrEnum):
    TESTS = "tests"
    REPORTS = "reports"
    INSURANCE = "insurance"
    PHARMACY = "pharmacy"
    #: What the hospital owes the visit: a confirmed slot, a doctor, a bed.
    APPOINTMENT = "appointment"
    DOCTOR = "doctor"
    BED = "bed"
    RIDE = "ride"
    STAY = "stay"
    DOCUMENTS = "documents"
    VISIT = "visit"
    NEXT_SESSION = "next_session"


class StageState(StrEnum):
    DONE = "done"
    #: Someone else is working on it; the family has nothing to do.
    WAITING = "waiting"
    #: Something failed and the team is arranging another way.
    PROBLEM = "problem"
    UPCOMING = "upcoming"


class FamilyAction(StrEnum):
    """What the family themselves should do about a stage."""

    NOTHING_YET = "nothing_yet"
    WAIT_FOR_TEAM = "wait_for_team"
    KEEP_DOCUMENTS_READY = "keep_documents_ready"
    BE_READY_FOR_PICKUP = "be_ready_for_pickup"
    GO_TO_FIRST_STOP = "go_to_first_stop"
    NONE = "none"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StageStep(_Frozen):
    """One care step inside a stage, so the screen can name it in the family's language."""

    kind: StepKind
    done: bool
    on: date | None = None


class GuideStage(_Frozen):
    id: str
    kind: StageKind
    state: StageState
    #: The first stage not yet done: the one a family should be looking at.
    is_now: bool = False
    action: FamilyAction = FamilyAction.NONE
    #: Who has it, in words a family would say: "Uber", "day-care pharmacy", "the lab".
    party: str | None = None
    #: One short, logistics-only line from the party: "driver confirmed for 6 am".
    detail: str = ""
    steps: tuple[StageStep, ...] = ()
    #: For a report still to come: the forecast window, never a promise.
    window: tuple[date, date] | None = None
    #: Only the visit, and only when the plan is a GO.
    on: date | None = None
    first_stop: str | None = None
    bring: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


class JourneyGuide(_Frozen):
    patient_id: str
    decision: str | None
    stages: tuple[GuideStage, ...]
    now_stage_id: str | None
    done: int
    total: int
