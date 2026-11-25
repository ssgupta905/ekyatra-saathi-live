"""FHIR R4 as the interchange format, at the edges only.

Saathi's internal model is `ports/hospital.py` — small, logistics-only
dataclasses with no field that can hold a result. This module projects those
into FHIR R4 resources and back, so the interchange format at every boundary
is a standard one while the domain model stays narrow.

That split is deliberate and worth stating, because "we speak FHIR" is often
taken to mean "FHIR is our database". FHIR is a wire format. A `Observation`
carries `valueQuantity`; an `Appointment` carries `comment` and `reason`. If
those resources were the internal model, every one of those fields would be a
place a clinical value could enter the logistics layer by accident. Projecting
at the boundary means there is exactly one direction things can flow and one
file to read to check it.

Everything here is pure: dicts in, dicts out, no transport and no clock. That
is what lets `ports/` hold it at all — this layer may import the domain and
nothing else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .hospital import AppointmentState, HospitalAppointment

#: Ours -> FHIR's appointment statuses. `UNKNOWN` deliberately projects to
#: `entered-in-error` rather than guessing a real one: a status we could not
#: read must not leave this system looking like a booked slot.
_TO_FHIR_STATUS: dict[AppointmentState, str] = {
    AppointmentState.SCHEDULED: "booked",
    AppointmentState.CHECKED_IN: "arrived",
    AppointmentState.COMPLETED: "fulfilled",
    AppointmentState.CANCELLED: "cancelled",
    AppointmentState.MISSED: "noshow",
    AppointmentState.UNKNOWN: "entered-in-error",
}

#: FHIR's own task vocabulary. A server is entitled to refuse anything else —
#: OpenEMR does, naming the seven codes it will take — and `approve` is
#: exactly what this task is asking for, so there is no reason to invent one.
TASK_CODE_SYSTEM = "http://hl7.org/fhir/CodeSystem/task-code"
TASK_CODE = "approve"

#: Our own code, for a server that accepts more than one coding. OpenEMR does
#: not — "Task.code takes one coding" — so the standard one wins and this is
#: carried in `code.text` instead, where it cannot be refused.
TASK_SYSTEM = "https://ekyatra.org/fhir/CodeSystem/saathi-task"
APPROVAL_CODE = "replan-approval"


def instant(moment: datetime) -> str:
    """A FHIR `instant`: UTC, to the second, with an explicit offset."""
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def appointment_to_fhir(appointment: HospitalAppointment) -> dict[str, Any]:
    """One of our appointments as a FHIR R4 `Appointment`.

    Status and timing only, as everywhere else. There is no `reasonCode` and
    no `comment` carrying anything clinical — the note field is the HMS's own
    logistics text and is projected as `description`.
    """
    resource: dict[str, Any] = {
        "resourceType": "Appointment",
        "id": appointment.ref,
        "status": _TO_FHIR_STATUS[appointment.state],
        "start": instant(appointment.starts_at),
        "end": instant(appointment.ends_at),
        "participant": [],
    }
    if appointment.service_name:
        resource["serviceType"] = [{"coding": [{"display": appointment.service_name}]}]
    if appointment.note:
        resource["description"] = appointment.note

    if appointment.patient_ref or appointment.patient_display:
        actor: dict[str, Any] = {}
        if appointment.patient_ref:
            actor["reference"] = _as_reference(appointment.patient_ref, "Patient")
        if appointment.patient_display:
            actor["display"] = appointment.patient_display
        if appointment.patient_identifier:
            actor["identifier"] = {"value": appointment.patient_identifier}
        resource["participant"].append({"actor": actor, "status": "accepted"})

    for display, kind in (
        (appointment.provider, "Practitioner"),
        (appointment.location, "Location"),
    ):
        if display:
            resource["participant"].append(
                {"actor": {"display": display, "type": kind}, "status": "accepted"}
            )
    return resource


def approval_task(
    *,
    patient_ref: str,
    patient_display: str,
    summary: str,
    description: str,
    requested_at: datetime,
    options: int = 0,
    requires_doctor: bool = False,
    requester_ref: str | None = None,
) -> dict[str, Any]:
    """A FHIR `Task` asking the hospital to approve a re-plan.

    Written into the hospital's own system so the request is on their record
    and not only on ours — an auditor at the hospital can see that a change
    was proposed, by whom, and what happened to it, without asking us.

    `status: requested` and `intent: proposal` are the honest pair: Saathi is
    proposing, not ordering. A system that wrote `order` here would be
    claiming an authority it does not have.

    The description says what the change costs the family in nights and trips.
    It carries no diagnosis, no result and no reason for treatment, because
    none of those is needed to decide a date and all of them would be a
    clinical claim this system has no business making.

    **No `requester` unless one is given.** FHIR wants a reference to a real
    Practitioner, Organization or Patient, and Saathi is none of them. Naming
    the hospital's own clinician or facility would put their name on a
    proposal they did not make — a false line in somebody else's record, to
    satisfy a schema. Who proposed it is said in `code.text` instead, which
    is true and refusable by nobody.

    **No `focus`.** The natural one is the appointment being replaced, and
    servers constrain `focus` to their own workflow types — OpenEMR takes
    only `ServiceRequest` and `Questionnaire`. The appointment is named in
    the description rather than claimed as a link the server would reject.
    """
    task: dict[str, Any] = {
        "resourceType": "Task",
        "status": "requested",
        "intent": "proposal",
        "priority": "urgent" if requires_doctor else "routine",
        "authoredOn": instant(requested_at),
        "lastModified": instant(requested_at),
        "code": {
            # One coding: OpenEMR refuses more, and the standard vocabulary is
            # the one a hospital's own tooling will understand.
            "coding": [{"system": TASK_CODE_SYSTEM, "code": TASK_CODE, "display": "Approve"}],
            "text": f"{summary} (proposed by Saathi)",
        },
        "description": description,
    }
    if requester_ref:
        task["requester"] = {"reference": requester_ref}
    if patient_ref:
        task["for"] = {
            "reference": _as_reference(patient_ref, "Patient"),
            "display": patient_display or patient_ref,
        }
    elif patient_display:
        task["for"] = {"display": patient_display}
    if options:
        # A string, not an integer: OpenEMR takes only valueReference,
        # valueCanonical, valueUrl, valueString, valueMarkdown or
        # valueCodeableConcept here, and a count is readable either way.
        task["input"] = [
            {
                "type": {"text": "options offered"},
                "valueString": str(options),
            }
        ]
    return task


def prioritise_task(
    *,
    patient_ref: str,
    patient_display: str,
    order_ref: str,
    what: str,
    needed_by: str,
    because: str,
    requested_at: datetime,
    requester_ref: str | None = None,
) -> dict[str, Any]:
    """A FHIR `Task` asking the hospital to bring a report forward.

    The counterpart to `approval_task`, and the one that makes a pending
    report actionable rather than merely visible. A family with travel they
    have already paid for and cannot change does not need the visit moved —
    moving it spends their money twice. What they need is the report in time,
    and asking for that is a request a hospital can act on.

    **Why this is `Task` and not a message.** OpenEMR has an internal Messages
    module and it is not reachable: there is no `Communication` resource, and
    its non-FHIR API refuses system-level credentials. `Task` is the standard
    way to ask a named party to do something, it lands in the hospital's own
    record, and it is queryable by anyone auditing later. The honest caveat,
    which belongs on a slide and not only here: OpenEMR does not surface
    `Task`s in its UI, so this is auditable rather than visible to a clerk.

    **`priority: urgent`, not `stat`.** `stat` in a hospital means something
    clinical. This is a logistics request about a family's bus ticket, and
    borrowing clinical urgency for it would be a lie told in a vocabulary
    clinicians trust.

    The reason given is the family's own circumstance — non-refundable travel,
    a date they cannot move — and never a clinical one. This system does not
    know and may not assert why a report matters medically.
    """
    task: dict[str, Any] = {
        "resourceType": "Task",
        "status": "requested",
        "intent": "proposal",
        "priority": "urgent",
        "authoredOn": instant(requested_at),
        "lastModified": instant(requested_at),
        "code": {
            "coding": [{"system": TASK_CODE_SYSTEM, "code": "fulfill", "display": "Fulfill"}],
            "text": f"Bring forward if possible: {what} (asked by Saathi)",
        },
        "description": (
            f"{what} is still outstanding and a visit on {needed_by} depends on it. "
            f"{because} Rescheduling would cost this family money they have already "
            f"spent, so the request is to prioritise the report rather than move the "
            f"visit. Logistics only: no clinical urgency is being asserted."
        ),
    }
    if requester_ref:
        task["requester"] = {"reference": requester_ref}
    if patient_ref:
        task["for"] = {
            "reference": _as_reference(patient_ref, "Patient"),
            "display": patient_display or patient_ref,
        }
    if order_ref:
        # The order this is about, named in a field the server will take. A
        # `focus` would be the natural home and OpenEMR constrains it to its
        # own workflow types, so this goes where it cannot be refused.
        task["input"] = [
            {"type": {"text": "order"}, "valueString": order_ref},
        ]
    return task


def completed_task(task: dict[str, Any], *, outcome: str, by: str, at: datetime) -> dict[str, Any]:
    """The same Task, closed, with who decided and what they decided.

    A copy rather than a mutation: the caller holds the version it read, and
    an update that silently edited it in place would make a failed write
    indistinguishable from a successful one.

    `cancelled` rather than `rejected` when every option was turned down:
    FHIR has no "refused" status for a proposal, and `failed` would say the
    task went wrong when in fact a person decided against it.
    """
    closed = dict(task)
    closed["status"] = "completed" if outcome == "approved" else "cancelled"
    closed["lastModified"] = instant(at)
    closed["output"] = [
        {"type": {"text": "decision"}, "valueString": outcome},
        {"type": {"text": "decided by"}, "valueString": by},
    ]
    return closed


def _as_reference(ref: str, kind: str) -> str:
    return ref if "/" in ref else f"{kind}/{ref}"


__all__ = [
    "APPROVAL_CODE",
    "TASK_CODE",
    "TASK_CODE_SYSTEM",
    "TASK_SYSTEM",
    "appointment_to_fhir",
    "approval_task",
    "completed_task",
    "prioritise_task",
    "instant",
]
