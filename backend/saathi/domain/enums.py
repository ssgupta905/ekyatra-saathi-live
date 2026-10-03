"""Closed vocabularies for the Saathi domain.

These are deliberately small. Every value that crosses a module boundary is one
of these enums, so a typo becomes an import error rather than a wrong message
sent to a family.
"""

from __future__ import annotations

from enum import StrEnum


class StepKind(StrEnum):
    """A single thing that happens at the hospital."""

    CONSULT = "consult"
    BIOPSY = "biopsy"
    BLOODS = "bloods"
    SCAN = "scan"
    #: The functional scan that follows the provisional diagnosis. Separate
    #: from SCAN because it books a different machine and, in the brief's
    #: story, is the step that can be pulled onto the MRI's day or left two
    #: days behind it — which is the entire difference between two options.
    PET_CT = "pet_ct"
    PATHOLOGY_REPORT = "pathology_report"
    RADIOLOGY_REPORT = "radiology_report"
    REVIEW_CONSULT = "review_consult"
    #: The consultants meeting where a treatment path is chosen. The visit a
    #: family's whole stay is anchored to, so moving it is what costs nights.
    JOINT_CLINIC = "joint_clinic"
    TREATMENT = "treatment"
    #: One dose of a repeating maintenance schedule (see `MaintenanceCycle`).
    MAINTENANCE_DOSE = "maintenance_dose"
    #: The echo + review bundled before every fourth maintenance dose.
    ECHO_REVIEW = "echo_review"


#: Steps that produce a result the family never travels for, but that later
#: steps depend on. Saathi reads only their *status*, never their content.
REPORT_STEPS = frozenset(
    {StepKind.PATHOLOGY_REPORT, StepKind.RADIOLOGY_REPORT}
)

#: Steps that require the family to physically be at the hospital.
TRAVEL_STEPS = frozenset(
    {
        StepKind.CONSULT,
        StepKind.BIOPSY,
        StepKind.BLOODS,
        StepKind.SCAN,
        StepKind.PET_CT,
        StepKind.REVIEW_CONSULT,
        StepKind.JOINT_CLINIC,
        StepKind.TREATMENT,
        StepKind.MAINTENANCE_DOSE,
        StepKind.ECHO_REVIEW,
    }
)


class StepStatus(StrEnum):
    """Status of a care step, as read from ABDM / hospital feeds.

    Never includes anything about *what* a report says.
    """

    NOT_SCHEDULED = "not_scheduled"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    PENDING_RESULT = "pending_result"
    RESULT_AVAILABLE = "result_available"
    CANCELLED = "cancelled"


class Decision(StrEnum):
    """The only three things Saathi is allowed to conclude about a visit."""

    GO = "go"
    WAIT = "wait"
    #: Prerequisites are unknowable from available data. No date is promised.
    UNCERTAIN = "uncertain"


class Language(StrEnum):
    """Languages the pilot supports end to end via Bhashini."""

    HINDI = "hi"
    BENGALI = "bn"
    ODIA = "or"
    ENGLISH = "en"


class Channel(StrEnum):
    WHATSAPP = "whatsapp"
    IVR = "ivr"


class SourceSystem(StrEnum):
    """Where a fact came from. Every ledger entry names one."""

    ABDM = "abdm"
    HOSPITAL_FEED = "hospital_feed"
    CAREGIVER_REPLY = "caregiver_reply"
    NAVIGATOR = "navigator"
    #: Produced by Saathi's own deterministic models (conformal, PELT, graph).
    DERIVED = "derived"


class AlertKind(StrEnum):
    DISENGAGEMENT = "disengagement"
    CLINICAL_QUESTION = "clinical_question"
    UNCERTAIN_PLAN = "uncertain_plan"


class ResourceKind(StrEnum):
    """What kind of thing a hospital resource is, for disruption matching."""

    MACHINE = "machine"
    STAFF = "staff"
    SUPPLY = "supply"


class DisruptionKind(StrEnum):
    """The three disruption shapes the two demo stories exercise."""

    MACHINE_DOWN = "machine_down"
    STAFF_UNAVAILABLE = "staff_unavailable"
    STOCK_DELAY = "stock_delay"


class Role(StrEnum):
    """Who is acting, for the console's role-gated screens and approvals."""

    NAVIGATOR = "navigator"
    DOCTOR = "doctor"
    DESK = "desk"
    ADMIN = "admin"
    PATIENT = "patient"
    CAREGIVER = "caregiver"


class FamilyMemberRole(StrEnum):
    """Which member of the family a message/confirmation belongs to."""

    PATIENT_SIMPLE = "patient_simple"
    CAREGIVER_PRIMARY = "caregiver_primary"
    CAREGIVER_SECONDARY = "caregiver_secondary"
