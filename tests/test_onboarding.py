"""Taking a family on: forms, the restricted medical section, documents, admissions, activation."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import Role
from saathi.domain.profile import mask_number
from saathi.main import create_app

PASSWORD = "correct horse battery"
PDF = base64.b64encode(b"%PDF-1.1 tiny").decode()
IDENTITY = {
    "patient_name": "Ravi Kumar",
    "caregiver_name": "Sita Kumar",
    "caregiver_relation": "wife",
    "caregiver_phone": "+91 98000 11122",
    "caregiver_email": "Sita.Kumar@Example.com",
    "language": "hi",
    "channel": "whatsapp",
    "district": "Patna",
}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/onb.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        identity = client.app.state.container.identity
        for name, role in (
            ("imran", Role.DESK),
            ("amrita", Role.DOCTOR),
            ("neha", Role.ADMIN),
        ):
            identity.add_user(name, name.title(), role, PASSWORD)

        def sign_in(who: str) -> None:
            token = client.post(
                "/api/auth/login", json={"username": who, "password": PASSWORD}
            ).json()["token"]
            client.headers["authorization"] = f"Bearer {token}"

        client.sign_in = sign_in
        client.sign_in("imran")
        yield client
    get_settings.cache_clear()


def _new_family(api, pid="P-NEW", **extra):
    body = {
        "id": pid, "name": "Ravi Kumar", "home_district": "Patna", "home_distance_km": 600,
        "language": "hi", "caregiver_phone": "+919800011122", "hospital_id": "TMH-MUM", **extra,
    }
    assert api.post("/api/patients", json=body).status_code == 201
    return pid


# ---------------------------------------------------------------- the forms


def test_each_form_is_served_as_a_schema_and_the_medical_one_is_restricted(api):
    identity = api.get("/api/forms/identity").json()
    email = identity["properties"]["caregiver_email"]
    assert any("pattern" in option for option in email["anyOf"])
    assert "patient_name" in identity["required"]
    assert api.get("/api/forms/admission").status_code == 200
    assert api.get("/api/forms/nonsense").status_code == 404

    assert api.get("/api/forms/medical").status_code == 403, "a desk may not see it"
    assert "medical" not in api.get("/api/forms").json()["sections"]
    api.sign_in("amrita")
    assert api.get("/api/forms/medical").status_code == 200
    assert "medical" in api.get("/api/forms").json()["sections"]


def test_the_medical_section_is_for_doctors_and_administrators_only(api):
    pid = _new_family(api)
    note = {"known_conditions": "x", "emergency_contact_name": "Sita"}

    assert api.put(f"/api/patients/{pid}/profile/medical", json=note).status_code == 403
    assert api.get(f"/api/patients/{pid}/profile/medical").status_code == 403
    api.sign_in("amrita")
    assert api.put(f"/api/patients/{pid}/profile/medical", json=note).status_code == 200
    assert api.get(f"/api/patients/{pid}/profile/medical").json()["data"]["known_conditions"] == "x"


def test_no_other_module_reads_the_medical_section():
    root = Path(__file__).resolve().parent.parent / "backend" / "saathi"
    allowed = {
        "domain/profile.py",
        "api/onboarding.py",
        "bootstrap/demo_profiles.py",
        "adapters/onboarding/sql.py",
        "adapters/onboarding/memory.py",
        "ports/onboarding.py",
    }
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if str(path.relative_to(root)) not in allowed
        and ("MedicalSection" in path.read_text() or "profile/medical" in path.read_text())
    ]

    assert offenders == [], f"the medical section must stay out of: {offenders}"


# ---------------------------------------------------------------- stage 1: the family


def test_saving_who_they_are_updates_their_contact_details_and_audits_without_content(api):
    pid = _new_family(api)

    saved = api.put(f"/api/patients/{pid}/profile/identity", json=IDENTITY)

    assert saved.status_code == 200
    patient = next(p for p in api.get("/api/patients").json() if p["id"] == pid)
    assert patient["caregiver_email"] == "sita.kumar@example.com"
    assert patient["home_district"] == "Patna"
    claims = [e["claim"] for e in api.get(f"/api/ledger/{pid}").json()["entries"]]
    assert "identity details saved" in claims
    assert not any("Sita" in c or "Ravi" in c for c in claims), "the ledger never holds the content"


def test_a_bad_form_names_the_field_that_is_wrong(api):
    pid = _new_family(api)

    response = api.put(
        f"/api/patients/{pid}/profile/identity",
        json={**IDENTITY, "caregiver_email": "not-an-address"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "caregiver_email"


def test_a_unknown_field_is_refused_rather_than_silently_dropped(api):
    pid = _new_family(api)

    response = api.put(f"/api/patients/{pid}/profile/background", json={"hair_colour": "black"})

    assert response.status_code == 422


# ---------------------------------------------------------------- documents


def test_a_document_is_masked_checked_and_can_be_opened_again(api):
    pid = _new_family(api)

    uploaded = api.post(
        f"/api/patients/{pid}/documents",
        json={
            "kind": "aadhaar", "number": "1234 5678 9012", "filename": "a.pdf", "data_base64": PDF,
        },
    ).json()

    assert uploaded["number_masked"].endswith("9012") and "1234" not in uploaded["number_masked"]
    assert uploaded["verified_by"] is None
    checked = api.post(f"/api/patients/{pid}/documents/{uploaded['id']}/verify").json()
    assert checked["verified_by"] == "Imran"
    assert api.get(f"/api/patients/{pid}/documents/{uploaded['id']}").content == b"%PDF-1.1 tiny"


def test_a_document_that_is_too_big_or_not_a_file_is_refused(api):
    pid = _new_family(api)
    big = base64.b64encode(b"0" * (5 * 1024 * 1024 + 1)).decode()

    too_big = api.post(
        f"/api/patients/{pid}/documents",
        json={"kind": "aadhaar", "filename": "a.pdf", "data_base64": big},
    )
    broken = api.post(
        f"/api/patients/{pid}/documents",
        json={"kind": "aadhaar", "filename": "a.pdf", "data_base64": "!!!"},
    )

    assert too_big.status_code == 413
    assert broken.status_code == 422


def test_masking_keeps_only_the_last_four():
    assert mask_number("1234 5678 9012") == "••••••••9012"
    assert mask_number("") == ""


# ---------------------------------------------------------------- stage 2: the hospital


def test_an_admission_needs_a_real_hospital_and_pathway(api):
    pid = _new_family(api)

    unknown = api.post(f"/api/patients/{pid}/admissions", json={"hospital_id": "NOPE"})
    assert unknown.status_code == 422
    assert (
        api.post(
            f"/api/patients/{pid}/admissions",
            json={"hospital_id": "TMH-MUM", "pathway_id": "nonsense"},
        ).status_code
        == 422
    )


def test_an_admission_puts_the_family_on_its_pathway_and_a_family_can_have_several(api):
    pid = _new_family(api)

    first = api.post(
        f"/api/patients/{pid}/admissions",
        json={"hospital_id": "TMH-MUM", "pathway_id": "dialysis", "type": "day_care"},
    )
    api.post(f"/api/patients/{pid}/admissions", json={"hospital_id": "TMH-MUM"})

    assert first.status_code == 201
    assert len(api.get(f"/api/patients/{pid}/admissions").json()) == 2
    patient = next(p for p in api.get("/api/patients").json() if p["id"] == pid)
    assert patient["pathway_id"] == "oncology", "the latest admission's pathway is the family's"


# ---------------------------------------------------------------- activation


def test_a_family_cannot_be_activated_until_every_stage_is_done_and_it_says_what_is_missing(api):
    pid = _new_family(api)

    refused = api.post(f"/api/patients/{pid}/activate")

    assert refused.status_code == 409
    missing = refused.json()["detail"]["missing"]
    assert "details not entered" in missing
    assert any("Referral letter" in m for m in missing)
    assert "the family has not agreed yet" in missing


def test_a_family_that_has_done_every_stage_can_be_activated(api):
    pid = _new_family(api, abha_number="91-1000-0000-4242")
    api.put(f"/api/patients/{pid}/profile/identity", json=IDENTITY)
    api.put(f"/api/patients/{pid}/profile/background", json={"occupation": "driver"})
    for kind in ("aadhaar", "referral_letter"):
        doc = api.post(
            f"/api/patients/{pid}/documents",
            json={"kind": kind, "filename": f"{kind}.pdf", "data_base64": PDF},
        ).json()
        api.post(f"/api/patients/{pid}/documents/{doc['id']}/verify")
    api.sign_in("amrita")
    api.put(f"/api/patients/{pid}/profile/medical", json={"known_conditions": "none"})
    api.sign_in("imran")
    request = api.post(
        f"/api/patients/{pid}/consent/requests",
        json={
            "purpose": "care_coordination", "requester_id": "saathi", "requester_name": "Saathi",
            "categories": ["visit status"],
        },
    ).json()
    api.post(
        f"/api/patients/{pid}/consent/requests/{request['id']}/grant",
        json={"granted_by": "Sita Kumar", "capacity": "self", "channel": "whatsapp"},
    )
    api.post(f"/api/patients/{pid}/admissions", json={"hospital_id": "TMH-MUM"})
    step = api.post(
        f"/api/patients/{pid}/steps",
        json={"kind": "consult", "status": "scheduled", "scheduled_for": "2026-12-01"},
    )
    assert step.status_code == 201, step.text

    before = api.get(f"/api/patients/{pid}/onboarding").json()
    assert before["ready"], before["stages"]
    done = api.post(f"/api/patients/{pid}/activate")

    assert done.status_code == 200
    assert done.json()["activated"]["by"] == "Imran"


def test_the_list_shows_least_finished_families_first(api):
    _new_family(api)

    rows = api.get("/api/onboarding").json()

    assert rows[0]["patient_id"] == "P-NEW" and rows[0]["done"] == 0
    assert all(r["activated"] for r in rows[1:]), "the seeded families come already activated"


def test_the_seeded_families_have_made_up_details_and_documents(api):
    status = api.get("/api/patients/P0000/onboarding").json()
    docs = api.get("/api/patients/P0000/documents").json()
    identity = api.get("/api/patients/P0000/profile/identity").json()

    assert status["activated"] is not None
    assert [s["done"] for s in status["stages"]][:3] == [True, True, True]
    assert {d["kind"] for d in docs} == {"aadhaar", "referral_letter", "scheme_card"}
    assert all(d["synthetic"] for d in docs)
    assert identity["by"] == "synthetic data"
