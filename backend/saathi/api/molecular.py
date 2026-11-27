"""The molecular register: which tests a patient has had, and where the reports are.

Three rules, all enforced here rather than described in a comment somewhere.

**A doctor reads it, and nobody else.** Not a navigator, not a partner, and
not the family's own app — a register of which panels somebody has had is
sensitive in a way a bus fare is not, and the person who needs it in order to
avoid ordering a repeat is a clinician. Writing is open to the desk as well,
because the person holding the PDF at the counter is usually not a doctor.

**It holds no results.** Every free-text field is screened for words that
would turn a record of a test into a finding, and a note that reads like one
is refused naming the word that triggered it. Crude, deliberately: a false
refusal costs a rephrase, a false accept puts a clinical claim inside a
logistics system.

**Consent is its own purpose and withdrawal actually deletes.**
`ConsentPurpose.MOLECULAR_RECORDS` is never bundled with care coordination,
and revoking it removes the rows rather than hiding them.

Nothing in `planner/`, `orchestrator/` or `live/` may import this. A re-plan
that moved a visit because of something in a molecular report would be a
clinical decision in a scheduling costume; `tests/test_architecture.py` keeps
that honest.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.consent import ConsentPurpose
from ..domain.enums import Role, SourceSystem
from ..domain.molecular import (
    TEST_NAMES,
    MolecularReport,
    MolecularTest,
    ReportState,
    reads_like_a_result,
)
from .access import PrincipalDep, require
from .deps import ContainerDep
from .registry import who

logger = logging.getLogger(__name__)

router = APIRouter(tags=["molecular"])

#: A doctor, or an administrator who has to keep the thing running. Open when
#: login is off, exactly like every other route in the demo.
DoctorOnly = require(Role.DOCTOR, Role.ADMIN)
DeskOrDoctor = require(Role.DOCTOR, Role.DESK, Role.ADMIN)


class NewReport(BaseModel):
    test: MolecularTest
    state: ReportState = ReportState.AWAITED
    lab_name: str = Field(default="", max_length=200)
    ordered_by_centre: str = Field(default="", max_length=200)
    ordered_on: date | None = None
    reported_on: date | None = None
    document_ref: str = Field(default="", max_length=400)
    note: str = Field(default="", max_length=400)


def _consented(container, patient) -> bool:
    """Has this family agreed to a molecular register being kept?

    Keyed on the ABHA number like every other grant, and failing closed: a
    consent lookup that raises is a refusal, never an assumption.
    """
    registry = getattr(container, "consent", None)
    if registry is None or not getattr(patient, "abha_number", ""):
        return False
    try:
        return bool(
            registry.active_grants(patient.abha_number, ConsentPurpose.MOLECULAR_RECORDS)
        )
    except Exception:  # noqa: BLE001 - a consent lookup failing is a refusal
        logger.exception("molecular consent lookup failed; treating as no permission")
        return False


def _refuse_results(*texts: str) -> None:
    for text in texts:
        word = reads_like_a_result(text) if text else None
        if word:
            raise HTTPException(
                422,
                "this register records that a test happened, not what it found — "
                f'"{word}" reads like a result. The finding belongs in the report '
                "itself, which this only points at.",
            )


def _store(container):
    store = getattr(container, "molecular", None)
    if store is None:
        raise HTTPException(503, "no molecular register is configured")
    return store


def _patient(container, patient_id: str):
    patient = container.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    return patient


@router.get("/patients/{patient_id}/molecular", dependencies=[DoctorOnly])
async def register(container: ContainerDep, patient_id: str) -> dict:
    """Every molecular test this patient has had, oldest first."""
    patient = _patient(container, patient_id)
    store = _store(container)

    if not _consented(container, patient):
        # Not a 403. "No consent" and "no tests" are opposite conclusions, and
        # a doctor about to order a panel needs to be told which one it is.
        return {
            "patient_id": patient_id,
            "consented": False,
            "reports": [],
            "not_reachable": 0,
            "why": "this family has not agreed to a molecular register being kept",
        }

    reports = store.for_patient(patient_id)
    return {
        "patient_id": patient_id,
        "consented": True,
        "reports": [
            {
                **report.model_dump(mode="json"),
                "test_name": TEST_NAMES.get(report.test, report.test.value),
                "summary": report.summary(),
                "can_be_fetched": report.can_be_fetched,
            }
            for report in reports
        ],
        # The number that actually saves a family money: tests whose report
        # exists but cannot be reached from here, which is what causes a repeat.
        "not_reachable": sum(
            1 for r in reports if not r.can_be_fetched and not r.still_waiting
        ),
    }


@router.post(
    "/patients/{patient_id}/molecular", status_code=201, dependencies=[DeskOrDoctor]
)
async def record(
    container: ContainerDep,
    principal: PrincipalDep,
    patient_id: str,
    body: NewReport,
) -> dict:
    """Record that a test happened. Never what it found."""
    patient = _patient(container, patient_id)
    store = _store(container)
    if not _consented(container, patient):
        raise HTTPException(
            403, "this family has not agreed to a molecular register being kept"
        )

    _refuse_results(body.note, body.lab_name, body.document_ref)

    if body.state is ReportState.HELD and not body.document_ref.strip():
        raise HTTPException(
            422,
            "a report recorded as held needs somewhere to point at; record it as "
            "'elsewhere' when the document exists but cannot be reached from here",
        )

    entered_by = who(principal)
    saved = store.save(
        MolecularReport(
            id=f"mol-{uuid.uuid4().hex[:10]}",
            patient_id=patient_id,
            test=body.test,
            state=body.state,
            lab_name=body.lab_name.strip(),
            ordered_by_centre=body.ordered_by_centre.strip(),
            ordered_on=body.ordered_on,
            reported_on=body.reported_on,
            document_ref=body.document_ref.strip(),
            note=body.note.strip(),
            recorded_at=datetime.now(UTC),
            recorded_by=entered_by,
        )
    )

    # Into the evidence ledger like every other fact this system holds, so a
    # family asking what is kept about them gets a complete answer. The claim
    # names the test, never a finding — there is none to name.
    container.ledger.record(
        patient_id=patient_id,
        source=SourceSystem.NAVIGATOR,
        source_record_id=f"molecular/{saved.id}",
        claim=saved.summary(),
        metadata={"by": entered_by, "state": saved.state.value},
    )

    return {"id": saved.id, "summary": saved.summary(), "state": saved.state.value}


@router.delete("/patients/{patient_id}/molecular", dependencies=[DoctorOnly])
async def forget(
    container: ContainerDep, principal: PrincipalDep, patient_id: str
) -> dict:
    """Withdrawal. Removes the rows rather than hiding them."""
    store = _store(container)
    removed = store.forget(patient_id)
    if removed:
        container.ledger.record(
            patient_id=patient_id,
            source=SourceSystem.NAVIGATOR,
            source_record_id=f"molecular/forget/{uuid.uuid4().hex[:8]}",
            claim=f"{removed} molecular record(s) deleted at the family's request",
            metadata={"by": who(principal)},
        )
    return {"patient_id": patient_id, "removed": removed}
