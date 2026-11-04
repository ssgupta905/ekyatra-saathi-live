"""Made-up onboarding details for the seeded families, so every form has something in it.

Invented for the demonstration and marked `synthetic`. Nothing here describes a
real person. The forms themselves work exactly as they will for real families.
"""

from __future__ import annotations

import logging
from datetime import date

from ..domain.models import Patient
from ..domain.profile import (
    Admission,
    AdmissionStatus,
    AdmissionType,
    DocumentKind,
    DocumentRecord,
    mask_number,
)
from ..ports.onboarding import OnboardingStore
from ..ports.registry import RegistryStore

logger = logging.getLogger(__name__)

#: A real, if empty, one-page PDF: enough for a viewer to open it.
PLACEHOLDER_PDF = (
    b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)

_CAREGIVERS = (
    "Sunita Devi", "Ramesh Yadav", "Geeta Kumari", "Mohan Lal", "Kavita Das", "Anil Raut",
)  # fmt: skip
_RELATIONS = ("wife", "son", "daughter", "husband", "brother", "mother")
_OCCUPATIONS = (
    "farm labourer", "small farmer", "daily-wage worker", "tailor", "driver", "shopkeeper",
)  # fmt: skip
_EDUCATION = ("none", "primary", "middle school", "secondary", "higher secondary")
_INCOME = ("below 1 lakh a year", "1 to 2 lakh a year", "2 to 3 lakh a year")
_RATION = ("bpl", "aay", "apl", "bpl")
_PLACES = ("Gaya", "Siwan", "Hajipur", "Purnia", "Nadia", "Cuttack")


def _index(patient_id: str) -> int:
    return sum(ord(c) for c in patient_id)


def seed_demo_onboarding(
    store: OnboardingStore, patients: tuple[Patient, ...], registry: RegistryStore | None
) -> int:
    """Fill in every family that has nothing saved yet. Returns how many it filled."""
    clinicians = registry.clinicians() if registry is not None else ()
    filled = 0
    for patient in patients:
        if store.saved_sections(patient.id) or store.documents(patient.id):
            continue
        i = _index(patient.id)
        caregiver = _CAREGIVERS[i % len(_CAREGIVERS)]
        by = "synthetic data"
        store.save_section(
            patient.id,
            "identity",
            {
                "patient_name": patient.name or f"Patient {patient.id}",
                "caregiver_name": caregiver,
                "caregiver_relation": _RELATIONS[i % len(_RELATIONS)],
                "caregiver_phone": patient.caregiver_phone,
                "caregiver_email": patient.caregiver_email,
                "language": patient.language.value,
                "channel": "whatsapp",
                "address": f"Village {_PLACES[i % len(_PLACES)]}, near the market",
                "district": patient.home_district,
                "pin_code": f"{800000 + i % 99999:06d}"[:6],
            },
            by,
        )
        store.save_section(
            patient.id,
            "background",
            {
                "date_of_birth": date(1950 + i % 40, 1 + i % 12, 1 + i % 27).isoformat(),
                "place_of_birth": patient.home_district,
                "sex": ("female", "male")[i % 2],
                "marital_status": "married",
                "household_size": 3 + i % 5,
                "occupation": _OCCUPATIONS[i % len(_OCCUPATIONS)],
                "education": _EDUCATION[i % len(_EDUCATION)],
                "income_band": _INCOME[i % len(_INCOME)],
                "ration_card": _RATION[i % len(_RATION)],
                "category": "",
            },
            by,
        )
        store.save_section(
            patient.id,
            "medical",
            {
                "known_conditions": "none reported",
                "allergies": "none reported",
                "current_medicines": "none reported",
                "past_hospital_stays": "none reported",
                "disability": "",
                "emergency_contact_name": caregiver,
                "emergency_contact_phone": patient.caregiver_phone,
            },
            by,
        )
        for n, kind in enumerate(
            (DocumentKind.AADHAAR, DocumentKind.REFERRAL_LETTER, DocumentKind.SCHEME_CARD)
        ):
            store.save_document(
                DocumentRecord(
                    id=f"doc-{patient.id}-{kind.value}",
                    patient_id=patient.id,
                    kind=kind,
                    number_masked=mask_number(f"{i * 7919 + n:012d}") if n != 1 else "",
                    issuer=("UIDAI", "District hospital", "PM-JAY")[n],
                    filename=f"{kind.value}.pdf",
                    content_type="application/pdf",
                    size=len(PLACEHOLDER_PDF),
                    uploaded_by=by,
                    verified_by=by,
                    synthetic=True,
                ),
                PLACEHOLDER_PDF,
            )
        doctor = next((c for c in clinicians if c.hospital_id == patient.hospital_id), None)
        store.save_admission(
            Admission(
                id=f"adm-{patient.id}-1",
                patient_id=patient.id,
                hospital_id=patient.hospital_id,
                department=doctor.department if doctor else "",
                clinician_id=doctor.id if doctor else None,
                pathway_id=patient.pathway_id,
                type=AdmissionType.OPD,
                referral_source="District hospital",
                status=AdmissionStatus.PLANNED,
                synthetic=True,
            )
        )
        store.activate(patient.id, by)
        filled += 1
    if filled:
        logger.info("filled in made-up onboarding details for %d families", filled)
    return filled
