"""A hospital whose system speaks plain FHIR R4.

The second adapter behind `ports/hospital.py`, and the reason that port exists.
Bahmni's appointments are its own REST API with its own vocabulary and epoch
milliseconds; this one is standard `Appointment` resources with ISO instants
and a `meta.lastUpdated` that actually moves. Same port, same connector, same
panel — two protocols that share nothing.

Written against a running HAPI FHIR R4 server, which is what the district
hospital runs in the demo. Three things differ from Bahmni and shape the code:

**There *is* a change feed.** `_lastUpdated` is a real search parameter here,
so this adapter could poll a cursor rather than diff snapshots. It still
returns the whole window, because `AppointmentSnapshot.diff` is what decides
what changed and keeping both adapters on one mechanism means the connector
has one behaviour to reason about rather than two. The cursor is used for the
clinical track, where volume actually justifies it.

**The patient's identifier is not on the appointment.** FHIR puts the patient
in `participant[].actor.reference` — `Patient/15579` — and the identifier we
match families on lives on the `Patient` resource. So every read asks for
`_include=Appointment:patient` and resolves references from the same bundle,
which keeps it to one request rather than one per appointment.

**Times carry offsets.** `2026-12-03T10:30:00-05:00` is not UTC and must not be
truncated to a date before conversion, or an evening appointment lands on the
previous day.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import httpx

from ...ports.hospital import (
    AWAY_CODES,
    AppointmentState,
    HospitalAppointment,
    HospitalOrder,
    HospitalService,
    HospitalUnavailable,
    OrderState,
    ProviderAway,
)
from ._tasks import FhirTasks

logger = logging.getLogger(__name__)

#: FHIR's appointment statuses -> ours. `pending`, `proposed` and `waitlist`
#: are deliberately absent: none of them is a slot a family can be told to
#: travel for, so they fall through to `UNKNOWN`, which is never bookable.
_STATES: dict[str, AppointmentState] = {
    "booked": AppointmentState.SCHEDULED,
    "arrived": AppointmentState.CHECKED_IN,
    "checked-in": AppointmentState.CHECKED_IN,
    "fulfilled": AppointmentState.COMPLETED,
    "cancelled": AppointmentState.CANCELLED,
    "noshow": AppointmentState.MISSED,
}

#: Ours -> FHIR's, for writing back.
_TO_FHIR: dict[AppointmentState, str] = {
    AppointmentState.SCHEDULED: "booked",
    AppointmentState.CHECKED_IN: "arrived",
    AppointmentState.COMPLETED: "fulfilled",
    AppointmentState.CANCELLED: "cancelled",
    AppointmentState.MISSED: "noshow",
}

#: Statuses already complained about. A public FHIR server holds plenty of
#: `pending` and `proposed` appointments, and at one poll every three seconds
#: a warning per occurrence buries every other line in the log within a
#: minute. Say each unknown status once and then stop.
_COMPLAINED: set[str] = set()

#: A FHIR server will happily return thousands of resources. A journey's window
#: is days, so cap the page and say so rather than paging forever on stage.
_PAGE = 200


class FhirHospital:
    """Appointments, services, booking and cancellation over FHIR R4."""

    name = "fhir"

    def __init__(
        self,
        *,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | Callable[[], str] | None = None,
        supports_include: bool = True,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._root = base_url.rstrip("/")
        headers = {
            "Accept": "application/fhir+json",
            "Content-Type": "application/fhir+json",
        }
        # A callable rather than a string, because a SMART token lives five
        # minutes and a connector runs for an afternoon. A fixed string still
        # works and is set once here; a provider is asked on every request.
        self._token = token if callable(token) else None
        if token and not callable(token):
            headers["Authorization"] = f"Bearer {token}"
        auth = (username, password) if username and password else None
        self._client = client or httpx.Client(
            auth=auth, timeout=timeout, headers=headers
        )
        # OpenEMR's Appointment supports only `patient, _id, date, _lastUpdated`
        # — no `_include`. Asking for it there is at best ignored, so the
        # identifier has to be fetched per patient and remembered.
        self._supports_include = supports_include
        self._identifiers: dict[str, dict] = {}
        #: (practitioner, facility), resolved on the first booking.
        self._booking: tuple[str, str] | None = None
        self._tasks = FhirTasks(self._client, self._root, self._token)

    def create_task(self, task: dict) -> str:
        return self._tasks.create_task(task)

    def read_task(self, ref: str) -> dict | None:
        return self._tasks.read_task(ref)

    def update_task(self, ref: str, task: dict) -> None:
        self._tasks.update_task(ref, task)

    @property
    def live(self) -> bool:
        return True

    def close(self) -> None:
        self._client.close()

    # ---------------- reads ----------------

    def services(self) -> tuple[HospitalService, ...]:
        """What can be booked, from `Schedule`.

        A FHIR server need not have any — unlike Bahmni, where an appointment
        service is mandatory, FHIR lets an `Appointment` name its own
        `serviceType` inline. An empty tuple here is normal, not an error, and
        the connector falls back to the service named on each appointment.
        """
        bundle = self._get("/Schedule", {"_count": _PAGE})
        found = []
        for resource in _resources(bundle, "Schedule"):
            name = _service_name(resource) or resource.get("id", "")
            found.append(
                HospitalService(
                    ref=str(resource.get("id") or ""),
                    name=name,
                    speciality=_first_display(resource.get("specialty")),
                )
            )
        return tuple(found)

    def appointments(self, *, start: date, end: date) -> tuple[HospitalAppointment, ...]:
        """Every appointment in the window, cancelled ones included.

        `_include` pulls each appointment's `Patient` into the same bundle, so
        the identifier we match families on costs no extra request.
        """
        params: dict[str, object] = {
            "date": [f"ge{start.isoformat()}", f"le{end.isoformat()}"],
            "_count": _PAGE,
        }
        if self._supports_include:
            params["_include"] = "Appointment:patient"

        bundle = self._get("/Appointment", params)
        patients = {f"Patient/{r.get('id')}": r for r in _resources(bundle, "Patient")}

        appointments = [r for r in _resources(bundle, "Appointment")]
        if not self._supports_include:
            patients.update(self._patients_for(appointments))

        found = []
        for resource in appointments:
            if _is_provider_event(resource):
                # Leave and closures come back from the same search — the
                # patient join is a LEFT JOIN with no NOT NULL filter — and
                # they are not appointments. Letting one through produced an
                # UNKNOWN-state slot with no patient on it, which is a thing
                # the disruption detector should never have to think about.
                # They are read deliberately, by `providers_away`.
                continue
            appointment = _appointment(resource, patients)
            if appointment is not None:
                found.append(appointment)
        return tuple(found)

    def _patients_for(self, appointments: list[dict]) -> dict[str, dict]:
        """Resolve each appointment's patient, once ever, and remember it.

        A journey's window holds a handful of families, so this is a few reads
        the first time and none afterwards. Worth the cache: without it every
        poll would re-read every patient, which at one poll every three
        seconds is a lot of requests to learn nothing new.
        """
        wanted = {_patient_reference(a) for a in appointments}
        for reference in wanted:
            if not reference or reference in self._identifiers:
                continue
            fetched = self._get(f"/{reference}", None)
            # Remembered either way: an unresolvable reference is a fact about
            # this hospital, not a transient miss, and re-asking every poll
            # would be the same waste as not caching at all.
            self._identifiers[reference] = fetched if isinstance(fetched, dict) else {}
        return {r: self._identifiers[r] for r in wanted if r in self._identifiers}

    def appointment(self, ref: str) -> HospitalAppointment | None:
        resource = self._get(f"/Appointment/{ref}", None)
        if not isinstance(resource, dict) or resource.get("resourceType") != "Appointment":
            return None
        patient_ref = _patient_reference(resource)
        patients = {}
        if patient_ref:
            fetched = self._get(f"/{patient_ref}", None)
            if isinstance(fetched, dict):
                patients[patient_ref] = fetched
        return _appointment(resource, patients)

    # ---------------- optional: who is away ----------------

    def providers_away(self, *, start: date, end: date) -> tuple[ProviderAway, ...]:
        """Leave, holidays and closures the hospital has published.

        There is no `Schedule` and no `Slot` on OpenEMR — both routes 404 —
        so this reads the only place leave actually lives: the appointment
        stream. A provider event is an ordinary calendar row with no patient
        on it and an `appointmentType` naming the category, and the search
        that feeds `GET /Appointment` left-joins patient data without
        requiring it, which is why a patient-less event comes back at all.

        Two things are deliberately not filtered on:

        * **Status.** An all-day leave entered through the UI keeps the
          default `pc_apptstatus` of `-`, which projects to `proposed`, not
          `booked`. Filtering on a booked status would silently return no
          leave at all — which looks exactly like nobody being away.
        * **The category id.** `pc_catid` is auto-increment and differs
          between installations; the `appointmentType` code is OpenEMR's
          stable `pc_constant_id`. See `AWAY_CODES`.
        """
        bundle = self._get(
            "/Appointment",
            {
                "date": [f"ge{start.isoformat()}", f"le{end.isoformat()}"],
                "_count": _PAGE,
            },
        )
        away = []
        for resource in _resources(bundle, "Appointment"):
            parsed = _provider_away(resource)
            if parsed is not None:
                away.append(parsed)
        return tuple(away)

    # ---------------- optional: what is still outstanding ----------------

    def open_orders(
        self, *, patient_refs: tuple[str, ...] = ()
    ) -> tuple[HospitalOrder, ...]:
        """Every lab or imaging order that is not finished.

        **Read unfiltered, deliberately.** `ServiceRequest?status=` is
        declared against the raw database column, with no mapping from FHIR's
        vocabulary: `?status=pending` returns the order and `?status=active`
        returns nothing, even though the resource reads back
        `"status": "active"`. Passing the FHIR code a caller would reasonably
        pass is the quiet failure — a clean 200 with an empty bundle, which
        reads as "no orders outstanding".

        **And never with a `_lastUpdated` cursor.** For `ServiceRequest` that
        search parameter maps to `date_ordered`, which is written once and
        never touched when the status changes. Compare snapshots instead —
        `OrderSnapshot.diff`.
        """
        params: dict[str, object] = {"_count": _PAGE}
        if patient_refs:
            params["patient"] = ",".join(patient_refs)
        bundle = self._get("/ServiceRequest", params)

        orders = []
        for resource in _resources(bundle, "ServiceRequest"):
            order = _order(resource)
            if order is not None and order.state.blocks_dependents:
                orders.append(order)
        return tuple(orders)

    def results_since(self, since: datetime | None = None) -> tuple[dict, ...]:
        """Observations that have landed. Timing and identity, never a value.

        The redaction boundary `ingest/abdm.py:_text_of` draws is drawn again
        here, deliberately and in a second place: this returns the code, the
        subject and when it was issued. There is no field for what it said,
        and adding one would be the single change that turns a logistics
        system into a clinical one.
        """
        params: dict[str, object] = {"_count": _PAGE, "status": "final"}
        if since is not None:
            params["_lastUpdated"] = f"gt{_instant(since)}"
        bundle = self._get("/Observation", params)
        landed = []
        for resource in _resources(bundle, "Observation"):
            landed.append(
                {
                    "ref": str(resource.get("id") or ""),
                    "code": _first_display(resource.get("code")),
                    "patient_ref": _subject_reference(resource),
                    "patient_display": (resource.get("subject") or {}).get("display", ""),
                    "issued": resource.get("issued", ""),
                    "last_updated": (resource.get("meta") or {}).get("lastUpdated", ""),
                }
            )
        return tuple(landed)

    # ---------------- writes ----------------

    def book(
        self,
        *,
        patient_ref: str,
        service_ref: str,
        starts_at: datetime,
        ends_at: datetime,
        note: str = "",
    ) -> HospitalAppointment:
        """Create a booked appointment, unless one just like it stands.

        Same duplicate check as the Bahmni adapter and for the same reason:
        approvals get retried, and a second identical appointment is a real
        patient told to come twice.
        """
        existing = self._standing_match(
            patient_ref=patient_ref, service_ref=service_ref, starts_at=starts_at
        )
        if existing is not None:
            logger.info(
                "fhir: %s already holds %s at %s; not booking a second",
                patient_ref,
                service_ref,
                starts_at.isoformat(),
            )
            return existing

        participants: list[dict] = [
            {
                "actor": {"reference": _as_reference(patient_ref, "Patient")},
                "status": "accepted",
            }
        ]
        # Some servers require more than a patient. OpenEMR rejects an
        # appointment with no Location participant, and one with no
        # Practitioner is created, readable over FHIR, and invisible on the
        # calendar — the single most confusing outcome in this integration,
        # because everything reads back correctly and the screen is empty.
        # Discovered once, lazily: a server that needs neither pays nothing.
        practitioner, location = self._booking_context()
        if practitioner:
            participants.append(
                {
                    "actor": {"reference": _as_reference(practitioner, "Practitioner")},
                    "status": "accepted",
                }
            )
        if location:
            participants.append(
                {
                    "actor": {"reference": _as_reference(location, "Location")},
                    "status": "accepted",
                }
            )

        body: dict[str, object] = {
            "resourceType": "Appointment",
            "status": "booked",
            "start": _instant(starts_at),
            "end": _instant(ends_at),
            "participant": participants,
        }
        if service_ref:
            body["serviceType"] = [{"coding": [{"display": service_ref}]}]
        # `description` is what a standard server shows; `comment` is what
        # OpenEMR requires and refuses to default. Send both.
        text = note or service_ref or "Rescheduled by Saathi"
        body["description"] = text
        body["comment"] = text

        created = self._post("/Appointment", body)
        booked = _appointment(created, {}) if isinstance(created, dict) else None
        if booked is not None:
            return booked

        # Created, but the server did not describe what it created. OpenEMR
        # answers 201 with a body carrying neither an id nor a start, and
        # raising here would report a failure for an appointment that now
        # exists — the worst of both, because a desk would re-book it.
        # So go and look instead of guessing either way.
        found = self._standing_match(
            patient_ref=patient_ref, service_ref=service_ref, starts_at=starts_at
        )
        if found is not None:
            return found
        raise HospitalUnavailable(
            "the hospital accepted the booking and then did not report it; "
            "check the appointment before telling the family anything"
        )

    def cancel(self, appointment_ref: str, *, note: str = "") -> HospitalAppointment:
        """Set `status` to cancelled, and read it back to be sure it took."""
        standing = self._get(f"/Appointment/{appointment_ref}", None)
        if not isinstance(standing, dict):
            raise HospitalUnavailable(f"no appointment {appointment_ref}")
        if _state(standing.get("status")) is AppointmentState.CANCELLED:
            return _appointment(standing, {}) or _unreadable(appointment_ref)

        body = dict(standing)
        body["status"] = "cancelled"
        if note:
            body["cancelationReason"] = {"text": note}
        self._put(f"/Appointment/{appointment_ref}", body)

        after = self.appointment(appointment_ref)
        if after is None:
            raise HospitalUnavailable(
                f"cancelled {appointment_ref} but could not read it back"
            )
        if after.state is not AppointmentState.CANCELLED:
            raise HospitalUnavailable(
                f"asked for {appointment_ref} to be cancelled; it still reads {after.state.value}"
            )
        return after

    # ---------------- plumbing ----------------

    def _booking_context(self) -> tuple[str, str]:
        """The practitioner and facility a booking must name, if this server cares.

        Both are looked up once and remembered. The facility comes from
        `Organization` rather than `Location`: OpenEMR's Location search also
        returns every patient's home address, and the clinic's Location id is
        a *different* uuid from the facility row its appointment validator
        resolves against — so using it fails while pointing at something that
        is, visibly, a location.
        """
        if self._booking is not None:
            return self._booking

        def first(path: str) -> str:
            try:
                found = _resources(self._get(path, {"_count": 5}), path.lstrip("/"))
            except HospitalUnavailable:
                return ""
            return str(found[0].get("id") or "") if found else ""

        self._booking = (first("/Practitioner"), first("/Organization"))
        logger.info(
            "booking context: practitioner=%r facility=%r",
            self._booking[0] or "none",
            self._booking[1] or "none",
        )
        return self._booking

    def _standing_match(
        self, *, patient_ref: str, service_ref: str, starts_at: datetime
    ) -> HospitalAppointment | None:
        day = starts_at.astimezone(UTC).date()
        for appointment in self.appointments(
            start=day - timedelta(days=1), end=day + timedelta(days=1)
        ):
            if (
                appointment.patient_ref == patient_ref
                and appointment.starts_at == starts_at
                and appointment.state.is_open
            ):
                return appointment
        return None

    def _get(self, path: str, params: dict | None) -> object:
        return self._send("GET", path, params=params)

    def _post(self, path: str, body: dict) -> object:
        return self._send("POST", path, json=body)

    def _put(self, path: str, body: dict) -> object:
        return self._send("PUT", path, json=body)

    def _send(self, method: str, path: str, **kwargs: object) -> object:
        url = f"{self._root}{path}"
        if self._token is not None:
            # Asked for every request: the provider returns the cached token
            # until it is nearly expired, so this is a dict lookup almost
            # always and a token mint occasionally.
            headers = dict(kwargs.pop("headers", {}) or {})  # type: ignore[arg-type]
            headers["Authorization"] = f"Bearer {self._token()}"
            kwargs["headers"] = headers
        try:
            response = self._client.request(method, url, **kwargs)  # type: ignore[arg-type]
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # A FHIR server answers failures with an OperationOutcome whose
            # diagnostics say what was actually wrong. Losing it makes every
            # failure look identical from the console.
            raise HospitalUnavailable(
                f"fhir {method} {path} -> {exc.response.status_code}: "
                f"{_outcome(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise HospitalUnavailable(f"fhir {method} {path}: {exc}") from exc

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise HospitalUnavailable(f"fhir {method} {path}: body was not JSON") from exc


# ---------------- projection ----------------


def _resources(bundle: object, kind: str) -> list[dict]:
    """Entries of one type out of a search bundle, tolerant of a bare resource."""
    if isinstance(bundle, dict) and bundle.get("resourceType") == kind:
        return [bundle]
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        return []
    found = []
    for entry in bundle.get("entry") or []:
        resource = (entry or {}).get("resource")
        if isinstance(resource, dict) and resource.get("resourceType") == kind:
            found.append(resource)
    return found


def _appointment(resource: dict, patients: dict[str, dict]) -> HospitalAppointment | None:
    ref = str(resource.get("id") or "")
    starts = _moment(resource.get("start"))
    ends = _moment(resource.get("end"))
    if not ref or starts is None:
        logger.warning("fhir: skipping an appointment with no id or no start")
        return None
    if ends is None:
        minutes = resource.get("minutesDuration")
        ends = starts + timedelta(minutes=int(minutes) if minutes else 30)

    patient_ref = _patient_reference(resource)
    patient = patients.get(patient_ref, {})

    return HospitalAppointment(
        ref=ref,
        patient_ref=patient_ref,
        patient_display=_patient_display(resource) or _human_name(patient),
        patient_identifier=_identifier_of(patient),
        service_ref=_service_name(resource),
        service_name=_service_name(resource) or str(resource.get("description") or ""),
        starts_at=starts,
        ends_at=ends,
        state=_state(resource.get("status")),
        provider=_participant_display(resource, "Practitioner")
        or _participant_display(resource, "Person"),
        provider_ref=_participant_reference(resource, "Practitioner")
        or _participant_reference(resource, "Person"),
        location=_participant_display(resource, "Location"),
        note=str(resource.get("description") or ""),
    )


#: OpenEMR's order vocabulary, and FHIR's, mapped onto the one distinction a
#: logistics system needs. Both spellings are here because the same field is
#: read back as `pending` by its own search parameter and as `active` in the
#: resource body — see `FhirHospital.open_orders`.
_ORDER_STATES: dict[str, OrderState] = {
    "pending": OrderState.OPEN,
    "routed": OrderState.OPEN,
    "active": OrderState.OPEN,
    "draft": OrderState.OPEN,
    "on-hold": OrderState.OPEN,
    "complete": OrderState.DONE,
    "completed": OrderState.DONE,
    "revoked": OrderState.REVOKED,
    "canceled": OrderState.REVOKED,
    "cancelled": OrderState.REVOKED,
    "entered-in-error": OrderState.REVOKED,
}


def _provider_away(resource: dict) -> ProviderAway | None:
    """One `Appointment` read as leave, or None if it is a patient's booking.

    Both halves of the test matter. The appointment type says what kind of
    event it is; the absence of a patient participant says it is not somebody's
    visit. A patient booked into a slot the hospital happens to have labelled
    "Out Of Office" is a booking, and treating it as leave would cancel a
    family's appointment on the strength of a label.
    """
    if not _is_provider_event(resource):
        return None
    code = _away_code(resource)
    assert code is not None  # guaranteed by _is_provider_event

    starts = _moment(resource.get("start"))
    if starts is None:
        logger.warning("fhir: skipping a %s event with no start", code)
        return None

    # `end` is the end of the *first day*, never the end of the leave: OpenEMR
    # does not project `pc_endDate`. Say so rather than implying a range.
    ends = _moment(resource.get("end"))
    if ends is None:
        ends = starts + timedelta(days=1)

    # An all-day event arrives as 00:00:00 to 23:59:59, not as a missing end,
    # so this is read from the span. Inferring it from a missing `end` never
    # fired once against a real instance.
    whole_day = (
        starts.hour == 0
        and starts.minute == 0
        and (ends - starts) >= timedelta(hours=23, minutes=59)
    )

    return ProviderAway(
        ref=str(resource.get("id") or ""),
        provider_ref=(
            _participant_reference(resource, "Practitioner")
            or _participant_reference(resource, "Person")
        ),
        provider_display=(
            _participant_display(resource, "Practitioner")
            or _participant_display(resource, "Person")
        ),
        kind=code,
        starts_at=starts,
        ends_at=ends,
        # Always False against OpenEMR, and the field exists so that stays
        # visible rather than becoming a silent assumption. An HMS that does
        # publish an end can set it.
        end_is_known=False,
        whole_day=whole_day,
    )


def _is_provider_event(resource: dict) -> bool:
    """Whether this is leave or a closure rather than somebody's appointment.

    One definition, used by both the reader that wants these and the reader
    that must skip them — so the two can never disagree about what a provider
    event is.
    """
    return _away_code(resource) is not None and not _patient_reference(resource)


def _away_code(resource: dict) -> str | None:
    """The `appointmentType` code, when it is one that means "nobody is in"."""
    for coding in (resource.get("appointmentType") or {}).get("coding") or []:
        if not isinstance(coding, dict):
            continue
        code = str(coding.get("code") or "").strip().lower()
        if code in AWAY_CODES:
            return code
    return None


def _order(resource: dict) -> HospitalOrder | None:
    ref = str(resource.get("id") or "")
    if not ref:
        return None
    raw = str(resource.get("status") or "").strip().lower()
    state = _ORDER_STATES.get(raw)
    if state is None:
        if raw not in _COMPLAINED:
            _COMPLAINED.add(raw)
            logger.warning(
                "fhir: order status %r is not one this reads; treating every "
                "occurrence as unknown, which never counts as finished",
                raw,
            )
        state = OrderState.UNKNOWN
    return HospitalOrder(
        ref=ref,
        patient_ref=_subject_reference(resource),
        name=_first_display(resource.get("code")),
        state=state,
        ordered_at=_moment(resource.get("authoredOn")),
    )


def _state(raw: object) -> AppointmentState:
    if not isinstance(raw, str):
        return AppointmentState.UNKNOWN
    key = raw.strip().lower()
    state = _STATES.get(key)
    if state is None:
        if key not in _COMPLAINED:
            _COMPLAINED.add(key)
            logger.warning(
                "fhir: appointment status %r is not one this reads; treating every "
                "occurrence as unknown, which is never bookable",
                raw,
            )
        return AppointmentState.UNKNOWN
    return state


def _participants(resource: dict) -> list[dict]:
    return [p for p in (resource.get("participant") or []) if isinstance(p, dict)]


def _patient_reference(resource: dict) -> str:
    for participant in _participants(resource):
        reference = str((participant.get("actor") or {}).get("reference") or "")
        if reference.startswith("Patient/"):
            return reference
    subject = (resource.get("subject") or {}).get("reference")
    return str(subject or "")


def _patient_display(resource: dict) -> str:
    for participant in _participants(resource):
        actor = participant.get("actor") or {}
        if str(actor.get("reference", "")).startswith("Patient/"):
            return str(actor.get("display") or "")
    return ""


def _participant_reference(resource: dict, kind: str) -> str:
    """The reference of the first participant of a kind, if it has one."""
    for participant in _participants(resource):
        actor = participant.get("actor") or {}
        reference = str(actor.get("reference") or "")
        if reference.startswith(f"{kind}/"):
            return reference
    return ""


def _participant_display(resource: dict, kind: str) -> str:
    for participant in _participants(resource):
        actor = participant.get("actor") or {}
        if str(actor.get("reference", "")).startswith(f"{kind}/"):
            return str(actor.get("display") or "")
    return ""


def _subject_reference(resource: dict) -> str:
    return str((resource.get("subject") or {}).get("reference") or "")


def _identifier_of(patient: dict) -> str:
    """The identifier we match a family on.

    A FHIR patient often carries several — an MRN, a programme number, a demo
    id. The first is taken rather than guessing which system is authoritative,
    because the pilot's own seed decides what it writes and `HospitalLinks` is
    where that assumption belongs.
    """
    for identifier in patient.get("identifier") or []:
        value = (identifier or {}).get("value")
        if value:
            return str(value)
    return ""


def _human_name(patient: dict) -> str:
    for name in patient.get("name") or []:
        if not isinstance(name, dict):
            continue
        if name.get("text"):
            return str(name["text"])
        given = " ".join(str(g) for g in (name.get("given") or []))
        family = str(name.get("family") or "")
        if given or family:
            return f"{given} {family}".strip()
    return ""


def _service_name(resource: dict) -> str:
    """What was booked, in whatever field this server puts it.

    `serviceType` is the standard answer and what HAPI uses. OpenEMR does not
    populate it at all — the nearest thing it has is the appointment
    *category*, which it reports as `appointmentType`. So try both, and expect
    neither: an OpenEMR appointment created over FHIR lands in the default
    "Office Visit" category, because `appointmentType` is ignored on create.
    When this comes back empty the connector identifies the machine from the
    care step instead; see `HospitalLinks.resource_for`.
    """
    return _first_display(resource.get("serviceType")) or _first_display(
        resource.get("appointmentType")
    )


def _first_display(field: object) -> str:
    """A display string out of a CodeableConcept, or a list of them."""
    items = field if isinstance(field, list) else [field]
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("text"):
            return str(item["text"])
        for coding in item.get("coding") or []:
            if isinstance(coding, dict) and (coding.get("display") or coding.get("code")):
                return str(coding.get("display") or coding.get("code"))
    return ""


def _moment(raw: object) -> datetime | None:
    """An ISO instant, which FHIR writes with a real offset, not always UTC."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _instant(moment: datetime) -> str:
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _as_reference(ref: str, kind: str) -> str:
    return ref if "/" in ref else f"{kind}/{ref}"


def _outcome(response: httpx.Response) -> str:
    """What the server said, out of an OperationOutcome if there is one."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300].strip()
    if isinstance(body, dict) and body.get("resourceType") == "OperationOutcome":
        reasons = [
            str((issue or {}).get("diagnostics") or (issue or {}).get("code") or "")
            for issue in body.get("issue") or []
        ]
        joined = "; ".join(r for r in reasons if r)
        if joined:
            return joined[:300]
    return response.text[:300].strip()


def _unreadable(ref: str) -> HospitalAppointment:
    """A placeholder for an appointment the server returned but we cannot read.

    Only reachable when a cancel confirms against a resource missing its own
    start time. Carries `UNKNOWN`, which is never bookable, rather than a
    guessed time that would read as a real slot.
    """
    now = datetime.now(UTC)
    return HospitalAppointment(
        ref=ref,
        patient_ref="",
        service_ref="",
        starts_at=now,
        ends_at=now,
        state=AppointmentState.UNKNOWN,
    )


__all__ = ["FhirHospital"]
