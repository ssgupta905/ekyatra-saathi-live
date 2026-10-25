"""Report status, timing and provenance, across one family or the whole hospital.

"Report details" here means what a desk and a navigator need to plan around:
which report, which lab queue, when the sample was taken, whether it has landed,
the calibrated window it should land in, and who said it landed. Never what it
says. There is no field anywhere in this system that could hold that, and this
module does not add one.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from ..domain.enums import REPORT_STEPS, StepStatus
from ..domain.models import CareStep, ReadinessWindow
from ..planner.tools import readiness_for
from .access import AnyStaff
from .deps import ContainerDep

router = APIRouter()


def _state(step: CareStep, window: ReadinessWindow | None, today: date) -> str:
    """Where a report stands against its window, in one word a desk can sort by."""
    if step.status is StepStatus.RESULT_AVAILABLE:
        return "released"
    if step.status is StepStatus.CANCELLED:
        return "cancelled"
    if window is None:
        return "no_window"
    if not window.calibrated:
        return "no_forecast"
    if today > window.latest:
        return "overdue"
    if today >= window.earliest:
        return "due"
    return "waiting"


def _release_entries(state: ContainerDep, patient_id: str) -> dict[str, dict]:
    """step id -> the ledger row that recorded its release, newest wins."""
    found: dict[str, dict] = {}
    for entry in state.ledger.for_patient(patient_id):
        if entry.claim.endswith("is result_available"):
            found[entry.source_record_id] = {
                "ledger_id": entry.id,
                "by": entry.metadata.get("confirmed_by"),
                "recorded_at": entry.recorded_at.isoformat(),
            }
    return found


def report_rows(state: ContainerDep, patient_ids: list[str] | None = None) -> list[dict]:
    predictor = state.planner.predictor
    today = state.world.today
    rows: list[dict] = []
    for patient in state.world.patients():
        if patient_ids is not None and patient.id not in patient_ids:
            continue
        releases = _release_entries(state, patient.id)
        for step in state.world.steps_for(patient.id):
            if step.kind not in REPORT_STEPS:
                continue
            window = readiness_for(step, predictor)
            rows.append(
                {
                    "step_id": step.id,
                    "patient_id": patient.id,
                    "patient_name": patient.name,
                    "district": patient.home_district,
                    "hospital_id": patient.hospital_id,
                    "kind": step.kind.value,
                    "queue": step.queue,
                    "status": step.status.value,
                    "sample_taken_on": (
                        step.completed_on.isoformat() if step.completed_on else None
                    ),
                    "released_on": (
                        step.result_available_on.isoformat() if step.result_available_on else None
                    ),
                    "turnaround_days": (
                        (step.result_available_on - step.completed_on).days
                        if step.result_available_on and step.completed_on
                        else None
                    ),
                    "window": window.model_dump(mode="json") if window else None,
                    "state": _state(step, window, today),
                    "release": releases.get(step.id),
                }
            )
    return rows


@router.get("/reports", dependencies=[AnyStaff])
async def reports(
    state: ContainerDep,
    status: str | None = None,
    queue: str | None = None,
    hospital: str | None = None,
    patient_id: str | None = None,
    report_state: str | None = None,
) -> dict:
    """Every report step, with where it stands against its window."""
    rows = report_rows(state, [patient_id] if patient_id else None)
    if status:
        rows = [r for r in rows if r["status"] == status]
    if queue:
        rows = [r for r in rows if r["queue"] == queue]
    if hospital:
        rows = [r for r in rows if r["hospital_id"] == hospital]
    if report_state:
        rows = [r for r in rows if r["state"] == report_state]
    order = {"overdue": 0, "due": 1, "no_forecast": 2, "no_window": 3, "waiting": 4,
             "released": 5, "cancelled": 6}  # fmt: skip
    rows.sort(key=lambda r: (order.get(r["state"], 9), r["window"]["latest"] if r["window"] else "",
                             r["patient_id"]))  # fmt: skip
    counts: dict[str, int] = {}
    for row in report_rows(state, [patient_id] if patient_id else None):
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return {"today": state.world.today.isoformat(), "counts": counts, "reports": rows}


@router.get("/readiness/queues", dependencies=[AnyStaff])
async def readiness_queues(state: ContainerDep) -> dict:
    """What the forecast knows about each lab queue, and how well it has done.

    `observed_coverage` is the share of reports already released that landed
    inside the interval: the check that the promised coverage is being kept.
    """
    predictor = state.planner.predictor
    rows = report_rows(state)
    queues = sorted(set(predictor.queues()) | {r["queue"] for r in rows if r["queue"]})
    out = []
    for queue in queues:
        low, high, calibrated, n = predictor.interval_days(queue)
        mine = [r for r in rows if r["queue"] == queue]
        landed = [r["turnaround_days"] for r in mine if r["turnaround_days"] is not None]
        inside = sum(1 for days in landed if low <= days <= high)
        out.append(
            {
                "queue": queue,
                "observations": n,
                "calibrated": calibrated,
                "interval_days": [low, high] if n else None,
                "pending": sum(1 for r in mine if r["status"] == StepStatus.PENDING_RESULT.value),
                "released": len(landed),
                "observed_coverage": (inside / len(landed)) if landed and calibrated else None,
            }
        )
    return {
        "alpha": predictor.alpha,
        "coverage_target": 1 - predictor.alpha,
        "min_calibration": predictor.min_calibration,
        "queues": out,
    }
