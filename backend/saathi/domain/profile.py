"""What a family tells us when they are taken on, and what a hospital adds per admission.

These models are the single source of truth for the onboarding forms: the
control centre draws each one from its JSON Schema, so a new field is a change
here and nowhere else.

The medical section is deliberately different from the rest. It is what the
family reports about themselves, kept apart, visible only to doctors and
administrators, and never read by the planner, the journey guide, any message,
any language model or any partner. `tests/test_onboarding.py` checks that no
other module refers to it.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .enums import Channel, Language


class _Form(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- stage 1: the family


class IdentitySection(_Form):
    """Who they are and how to reach them."""

    patient_name: str = Field(min_length=1, max_length=160, title="Patient's name")
    caregiver_name: str = Field(min_length=1, max_length=160, title="Caregiver's name")
    caregiver_relation: str = Field(default="", max_length=60, title="Caregiver is the patient's")
    caregiver_phone: str = Field(min_length=5, max_length=24, title="Caregiver's phone")
    caregiver_email: str | None = Field(
        default=None,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        title="Caregiver's email",
        description="Lets them sign in with a code sent by email.",
    )
    language: Language = Field(default=Language.HINDI, title="Language they are written to")
    channel: Channel = Field(default=Channel.WHATSAPP, title="Preferred channel")
    address: str = Field(default="", max_length=240, title="Address")
    district: str = Field(min_length=1, max_length=128, title="District")
    pin_code: str = Field(default="", max_length=10, title="PIN code")


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
    NOT_STATED = "not_stated"


class RationCard(StrEnum):
    NONE = "none"
    APL = "apl"
    BPL = "bpl"
    AAY = "aay"


class BackgroundSection(_Form):
    """Demographics and circumstances, used to find the right schemes and support."""

    date_of_birth: date | None = Field(default=None, title="Date of birth")
    place_of_birth: str = Field(default="", max_length=120, title="Place of birth")
    sex: Sex = Field(default=Sex.NOT_STATED, title="Sex")
    marital_status: str = Field(default="", max_length=40, title="Marital status")
    household_size: int | None = Field(default=None, ge=1, le=40, title="People in the household")
    occupation: str = Field(default="", max_length=120, title="Occupation")
    education: str = Field(default="", max_length=120, title="Education")
    income_band: str = Field(default="", max_length=60, title="Household income band")
    ration_card: RationCard = Field(default=RationCard.NONE, title="Ration card")
    category: str = Field(default="", max_length=40, title="Category (optional)")


class MedicalSection(_Form):
    """What the family reports about themselves. Restricted: doctors and administrators only."""

    known_conditions: str = Field(default="", max_length=1000, title="Known conditions")
    allergies: str = Field(default="", max_length=500, title="Allergies")
    current_medicines: str = Field(default="", max_length=1000, title="Current medicines")
    past_hospital_stays: str = Field(default="", max_length=1000, title="Past hospital stays")
    disability: str = Field(default="", max_length=300, title="Disability or support needs")
    emergency_contact_name: str = Field(default="", max_length=160, title="Emergency contact")
    emergency_contact_phone: str = Field(default="", max_length=24, title="Emergency phone")


#: Form name -> model, for `GET /forms/{name}`.
SECTIONS: dict[str, type[_Form]] = {
    "identity": IdentitySection,
    "background": BackgroundSection,
    "medical": MedicalSection,
}

#: Sections only these roles may read or write.
RESTRICTED = {"medical": ("doctor", "admin")}


# ---------------------------------------------------------------- documents


class DocumentKind(StrEnum):
    AADHAAR = "aadhaar"
    ABHA_CARD = "abha_card"
    BIRTH_CERTIFICATE = "birth_certificate"
    RATION_CARD = "ration_card"
    SCHEME_CARD = "scheme_card"
    INSURANCE_POLICY = "insurance_policy"
    INCOME_CERTIFICATE = "income_certificate"
    REFERRAL_LETTER = "referral_letter"


DOCUMENT_LABELS: dict[DocumentKind, str] = {
    DocumentKind.AADHAAR: "Aadhaar (last 4 digits only)",
    DocumentKind.ABHA_CARD: "ABHA card",
    DocumentKind.BIRTH_CERTIFICATE: "Birth certificate",
    DocumentKind.RATION_CARD: "Ration card",
    DocumentKind.SCHEME_CARD: "Scheme card (PM-JAY or state)",
    DocumentKind.INSURANCE_POLICY: "Insurance policy",
    DocumentKind.INCOME_CERTIFICATE: "Income certificate",
    DocumentKind.REFERRAL_LETTER: "Referral letter",
}

#: Without these a family cannot be activated.
REQUIRED_DOCUMENTS = frozenset({DocumentKind.AADHAAR, DocumentKind.REFERRAL_LETTER})

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024


class DocumentUpload(_Form):
    kind: DocumentKind
    #: Masked on entry: only the last four characters are kept.
    number: str = Field(default="", max_length=40)
    issuer: str = Field(default="", max_length=120)
    filename: str = Field(min_length=1, max_length=160)
    content_type: str = Field(default="application/pdf", max_length=80)
    data_base64: str = Field(min_length=1)


class DocumentRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    patient_id: str
    kind: DocumentKind
    number_masked: str = ""
    issuer: str = ""
    filename: str
    content_type: str
    size: int
    uploaded_by: str = ""
    verified_by: str | None = None
    #: True for made-up demonstration data.
    synthetic: bool = False


def mask_number(number: str) -> str:
    """Keep the last four characters; nobody downstream needs more."""
    cleaned = "".join(ch for ch in number if ch.isalnum())
    if not cleaned:
        return ""
    return "•" * max(len(cleaned) - 4, 0) + cleaned[-4:]


# ---------------------------------------------------------------- stage 2: the hospital


class AdmissionType(StrEnum):
    OPD = "opd"
    DAY_CARE = "day_care"
    INPATIENT = "inpatient"


class AdmissionStatus(StrEnum):
    PLANNED = "planned"
    ADMITTED = "admitted"
    DISCHARGED = "discharged"


class AdmissionForm(_Form):
    """One visit or stay at a hospital. A family can have several over time."""

    hospital_id: str = Field(min_length=1, max_length=32, title="Hospital")
    department: str = Field(default="", max_length=80, title="Department")
    clinician_id: str | None = Field(default=None, max_length=64, title="Treating doctor")
    pathway_id: str = Field(default="oncology", max_length=32, title="Care pathway")
    type: AdmissionType = Field(default=AdmissionType.OPD, title="Kind of visit")
    referral_source: str = Field(default="", max_length=160, title="Referred by")
    expected_on: date | None = Field(default=None, title="Expected on")
    ward: str = Field(default="", max_length=40, title="Ward")
    bed: str = Field(default="", max_length=20, title="Bed")
    status: AdmissionStatus = Field(default=AdmissionStatus.PLANNED, title="Status")


class Admission(AdmissionForm):
    id: str
    patient_id: str
    synthetic: bool = False


# ---------------------------------------------------------------- the stages


class StageState(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    done: bool
    #: In plain words, what is still missing. Empty when done.
    missing: tuple[str, ...] = ()
    #: Who fills this stage in.
    owner: str = "family"


STAGES = ("identity", "background", "documents", "medical", "consent", "admission")


def stage_states(
    *,
    saved: frozenset[str],
    documents: tuple[DocumentRecord, ...],
    admissions: tuple[Admission, ...],
    consented: bool,
    care_steps: int,
) -> tuple[StageState, ...]:
    """Where a family is in onboarding, and what is missing from each stage."""
    have = {d.kind for d in documents}
    missing_docs = tuple(
        f"{DOCUMENT_LABELS[k]} not uploaded"
        for k in DocumentKind
        if k in REQUIRED_DOCUMENTS and k not in have
    )
    unverified = tuple(
        f"{DOCUMENT_LABELS[d.kind]} not yet checked" for d in documents if d.verified_by is None
    )
    admission_missing: list[str] = []
    if not admissions:
        admission_missing.append("no admission or visit recorded")
    if care_steps == 0:
        admission_missing.append("no care steps entered")
    return (
        StageState(
            id="identity", title="Who they are", done="identity" in saved,
            missing=() if "identity" in saved else ("details not entered",),
        ),
        StageState(
            id="background", title="Background", done="background" in saved,
            missing=() if "background" in saved else ("details not entered",),
        ),
        StageState(
            id="documents", title="Documents",
            done=not missing_docs and not unverified,
            missing=missing_docs + unverified,
        ),
        StageState(
            id="medical", title="Medical background", done="medical" in saved,
            missing=() if "medical" in saved else ("not yet recorded by a doctor",),
            owner="doctor",
        ),
        StageState(
            id="consent", title="Agreement to share", done=consented,
            missing=() if consented else ("the family has not agreed yet",),
        ),
        StageState(
            id="admission", title="Hospital admission", done=not admission_missing,
            missing=tuple(admission_missing), owner="hospital",
        ),
    )
