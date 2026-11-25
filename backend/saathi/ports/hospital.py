"""What a hospital management system can tell us, and what we may ask it to do.

Saathi does not run the hospital. The HMS does. This port is the whole of the
seam between them, and it is deliberately narrow: read the appointments, read
the services they can be booked into, book one, cancel one. Nothing clinical
passes through here, and nothing here decides anything.

**There is no "machine down" in this port, because there is none in a real HMS.**
A radiology desk does not publish "MRI-1 is broken"; it blocks the modality's
schedule and cancels the slots that were booked into it. So availability stays
where it already lives — desk-entered `Disruption` records, read by
`tools/hospital.py` — and what this port contributes is the appointment stream
those effects show up in. An adapter that invented a status field would be
inventing a fact the hospital never asserted.

Two adapters satisfy it. `adapters/hospital/bahmni.py` talks to Bahmni's
appointments REST API over HTTP. `adapters/hospital/desk.py` is what runs
without one: the appointments the hospital's own staff entered in our console,
which is the pilot's stated starting point. The connector never learns which it
has.

A note on vocabulary, learned the hard way against a running Bahmni: its
appointments are **not** FHIR. OpenMRS's FHIR R4 endpoint exposes Patient,
Encounter, Observation, DiagnosticReport and a dozen more, and no `Appointment`
resource at all. Appointment statuses are Bahmni's own words — `Scheduled`,
`CheckedIn`, `Completed`, `Cancelled`, `Missed` — so `AppointmentState` below is
the normalised form every adapter maps into, and the FHIR status map in
`ingest/abdm.py` does not apply to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable


class HospitalUnavailable(RuntimeError):
    """The HMS could not be reached, or answered with something unreadable.

    Raised by an adapter, never swallowed inside one. Callers in the tools layer
    translate it to `ToolUnavailable`, which becomes `None`, which the planner
    reads as "unknown" and answers UNCERTAIN. A connector that guessed instead
    would be asserting a hospital fact nobody at the hospital stated.
    """


class AppointmentState(StrEnum):
    """Bahmni's appointment vocabulary, normalised.

    `UNKNOWN` is deliberate and is not an error: a status this code has never
    seen must not silently read as `SCHEDULED`, because that is the one value
    that would make a cancelled slot look bookable.
    """

    SCHEDULED = "scheduled"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"
    UNKNOWN = "unknown"

    @property
    def is_open(self) -> bool:
        """Whether this appointment still expects the patient to turn up."""
        return self in (AppointmentState.SCHEDULED, AppointmentState.CHECKED_IN)

    @property
    def is_lost(self) -> bool:
        """Whether a booked slot has gone away. This is the disruption signal."""
        return self in (AppointmentState.CANCELLED, AppointmentState.MISSED)


@dataclass(frozen=True)
class HospitalService:
    """A thing that can be booked: a scanner, a clinic, a dialysis station.

    `ref` is the HMS's own identifier and is what we quote back when booking, so
    it is never generated here. `duration_minutes` and `max_per_day` come from
    the HMS when it states them; both are optional because a real Bahmni
    frequently leaves them null, and a default invented here would be a
    scheduling rule nobody at the hospital set.
    """

    ref: str
    name: str
    speciality: str = ""
    location: str = ""
    duration_minutes: int | None = None
    max_per_day: int | None = None

    def to_json(self) -> dict:
        return {
            "ref": self.ref,
            "name": self.name,
            "speciality": self.speciality,
            "location": self.location,
            "duration_minutes": self.duration_minutes,
            "max_per_day": self.max_per_day,
        }


@dataclass(frozen=True)
class HospitalAppointment:
    """One booked slot, as the HMS holds it.

    Status and timing only. There is no field here for a finding, a note's
    clinical content, or anything a report said — the same boundary
    `ingest/abdm.py` draws when it projects a FHIR resource.

    `patient_ref` is the HMS's patient identifier and `patient_display` the name
    it shows; both are needed because the connector matches on the first and the
    console shows the second.
    """

    ref: str
    patient_ref: str
    service_ref: str
    starts_at: datetime
    ends_at: datetime
    state: AppointmentState
    patient_display: str = ""
    patient_identifier: str = ""
    service_name: str = ""
    provider: str = ""
    #: The HMS's own reference for that provider, when it gives one.
    #:
    #: Needed because a display name is not an identity. Matching a provider's
    #: published leave against the appointments it collides with on name alone
    #: failed against a real OpenEMR: its provider events carry a reference and
    #: no display, so the comparison was a reference against a name and matched
    #: nobody — which reads as "this leave affects no families" rather than as a
    #: failure. Empty when the HMS does not say.
    provider_ref: str = ""
    location: str = ""
    #: The HMS's own free-text comment. Carried so a cancellation can say why,
    #: never parsed for clinical meaning.
    note: str = ""

    @property
    def day(self) -> date:
        return self.starts_at.date()

    def to_json(self) -> dict:
        return {
            "ref": self.ref,
            "patient_ref": self.patient_ref,
            "patient_display": self.patient_display,
            "patient_identifier": self.patient_identifier,
            "service_ref": self.service_ref,
            "service_name": self.service_name,
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "state": self.state.value,
            "provider": self.provider,
            "location": self.location,
            "note": self.note,
        }

    def differs_from(self, other: HospitalAppointment) -> bool:
        """Whether anything the journey depends on has moved.

        This is the whole of change detection, and it exists because Bahmni's
        appointment objects carry `dateCreated` but **no `dateChanged`**. There
        is no "what changed since" query to ask, so the poller diffs full
        snapshots and this decides what counts as different. Comments and
        display names are ignored on purpose: a desk retyping a note is not a
        change to the family's plan, and treating it as one would put a holding
        message on four phones.
        """
        return (
            self.state is not other.state
            or self.starts_at != other.starts_at
            or self.ends_at != other.ends_at
            or self.service_ref != other.service_ref
        )


@dataclass(frozen=True)
class AppointmentChange:
    """What one poll found: an appointment that appeared, moved or went away.

    `before` is `None` for one newly seen in the HMS. `after` is never `None` —
    a Bahmni appointment is cancelled, not deleted, so a slot that goes away
    arrives here as an `after` whose state `is_lost`.
    """

    after: HospitalAppointment
    before: HospitalAppointment | None = None

    @property
    def is_new(self) -> bool:
        return self.before is None

    @property
    def became_lost(self) -> bool:
        """A slot the family was counting on has gone. The disruption signal."""
        return self.after.state.is_lost and (self.before is None or not self.before.state.is_lost)

    @property
    def moved(self) -> bool:
        return self.before is not None and self.before.starts_at != self.after.starts_at

    def describe(self) -> str:
        """One sentence an auditor reads. Becomes the ledger claim."""
        who = self.after.patient_display or self.after.patient_identifier or self.after.patient_ref
        what = self.after.service_name or self.after.service_ref
        when = f"{self.after.starts_at:%d %b %H:%M}"
        if self.is_new:
            return f"{what} booked for {who} on {when}"
        if self.became_lost:
            return f"{what} for {who} on {when} was {self.after.state.value}"
        if self.moved and self.before is not None:
            return (
                f"{what} for {who} moved from {self.before.starts_at:%d %b %H:%M} to {when}"
            )
        return f"{what} for {who} on {when} is now {self.after.state.value}"


@dataclass
class AppointmentSnapshot:
    """The last full read, kept so the next one can be diffed against it.

    Mutable by design: the poller owns exactly one of these and replaces its
    contents in place each cycle.
    """

    by_ref: dict[str, HospitalAppointment] = field(default_factory=dict)
    #: False until the first successful read. The first poll must not report
    #: every existing appointment as new — that would raise a disruption per
    #: patient the moment the process starts.
    primed: bool = False

    def diff(self, latest: tuple[HospitalAppointment, ...]) -> tuple[AppointmentChange, ...]:
        """What changed since the last read, and adopt the new state."""
        changes: list[AppointmentChange] = []
        for appointment in latest:
            before = self.by_ref.get(appointment.ref)
            if before is None:
                if self.primed:
                    changes.append(AppointmentChange(after=appointment))
            elif appointment.differs_from(before):
                changes.append(AppointmentChange(after=appointment, before=before))

        self.by_ref = {a.ref: a for a in latest}
        self.primed = True
        return tuple(changes)


#: Appointment-type codes that mean "nobody is seeing patients", rather than
#: "a patient is booked". OpenEMR files provider leave as an ordinary calendar
#: event with one of these on it and no patient attached, which is how leave
#: becomes readable at all without a `Schedule` resource — it has none.
#:
#: These are OpenEMR's own `pc_constant_id` values, not invented ones, and they
#: are matched on rather than the numeric category id because that id is
#: auto-increment and differs between installations.
AWAY_CODES: frozenset[str] = frozenset(
    {"vacation", "out_of_office", "holidays", "closed"}
)


@dataclass(frozen=True)
class ProviderAway:
    """A provider or a facility marked unavailable in the hospital's calendar.

    This is a *fact the hospital published*, in the same spirit as the rest of
    this port: somebody at the hospital opened their calendar and marked
    themselves away. Saathi does not infer it from an empty schedule, because
    an empty schedule and an unpublished leave look identical and only one of
    them means anything.

    **`end_is_known` is not decoration.** OpenEMR stores a leave's end date and
    does not project it over FHIR — `FhirAppointmentService` reads
    `pc_endDate`, and the search that feeds it never selects the column. So a
    week's leave arrives looking like one day. An adapter that filled in a
    plausible end would be inventing the other six days; this one says it does
    not know, and a caller that needs the range reads it from somewhere that
    has it. Being wrong about when a doctor comes back is how a family is sent
    to an empty clinic twice.
    """

    ref: str
    #: `Practitioner/N`, or `Person/N` when the provider has no NPI — OpenEMR
    #: degrades the reference rather than omitting the participant, so an
    #: unexpected prefix here is a configuration fact, not a parse failure.
    provider_ref: str
    provider_display: str
    #: One of `AWAY_CODES`.
    kind: str
    starts_at: datetime
    ends_at: datetime
    #: Whether the HMS told us when this leave ends. False means `ends_at` is
    #: the end of `starts_at`'s day and nothing more.
    end_is_known: bool = True
    #: True for an all-day event, which is what leave usually is.
    whole_day: bool = False

    def covers(self, moment: datetime) -> bool:
        """Whether this leave is in force at a given moment.

        Only ever answered for the range the HMS actually gave us. A caller
        asking about a day beyond an unknown end gets False, which is the
        answer that leads to asking a person rather than to a wasted journey.
        """
        return self.starts_at <= moment < self.ends_at

    @property
    def is_facility_wide(self) -> bool:
        """A holiday or a closure, affecting everyone rather than one provider."""
        return self.kind in {"holidays", "closed"}


class OrderState(StrEnum):
    """Where a lab or imaging order has got to.

    Narrower than either vocabulary it is built from, on purpose. OpenEMR has
    an order status, a report status and a result status, and FHIR projects
    them inconsistently — `DiagnosticReport.status` is hardcoded `final`
    whatever the underlying report says. So this holds the only distinction a
    logistics system needs: can the family's next step happen yet, or not.
    """

    #: Ordered, nothing back. The visit that depends on it cannot happen.
    OPEN = "open"
    #: Something came back but is not final — OpenEMR's `prelim`. Deliberately
    #: not `DONE`: a preliminary report is not what a review consult needs.
    PRELIMINARY = "preliminary"
    #: Finished, and the dependent step may be planned.
    DONE = "done"
    #: Withdrawn. Not a failure; somebody decided against it.
    REVOKED = "revoked"
    #: Read as something this does not recognise. Never treated as done.
    UNKNOWN = "unknown"

    @property
    def blocks_dependents(self) -> bool:
        """Whether a step waiting on this order still has to wait."""
        return self is not OrderState.DONE


@dataclass(frozen=True)
class HospitalOrder:
    """A lab or imaging order, as a logistics fact and nothing more.

    No result, no value, no reference range, no interpretation — the same rule
    as `HospitalAppointment`. Whether a report is *ready* is a scheduling
    fact; what it *says* is a clinical one, and this system is not entitled to
    it. See `ports/fhir.py` for why the projection happens at the boundary.
    """

    ref: str
    patient_ref: str
    patient_identifier: str = ""
    #: The hospital's own name for what was ordered, for a navigator to read.
    name: str = ""
    state: OrderState = OrderState.UNKNOWN
    ordered_at: datetime | None = None

    def differs_from(self, other: HospitalOrder) -> bool:
        return self.state is not other.state


@dataclass(frozen=True)
class OrderSnapshot:
    """Every open order at one moment, so the next read can be compared to it.

    **Why a snapshot rather than a cursor.** `Appointment` can be polled on
    `_lastUpdated`, because OpenEMR's calendar editor stamps `pc_time` on
    every save. `ServiceRequest` cannot: its `_lastUpdated` maps to
    `date_ordered`, which is set once when the order is written and never
    touched again when its status changes. A watermark poller over orders
    would run forever and never see a single pending report become final.

    That is the whole reason this type exists. It is the same shape as
    `AppointmentSnapshot` deliberately — one mechanism to understand, and the
    appointment case proves it works.
    """

    orders: dict[str, HospitalOrder] = field(default_factory=dict)

    @classmethod
    def of(cls, orders: tuple[HospitalOrder, ...]) -> OrderSnapshot:
        return cls(orders={order.ref: order for order in orders})

    def diff(self, previous: OrderSnapshot) -> tuple[HospitalOrder, ...]:
        """Orders whose state changed since `previous`, plus ones newly seen.

        An order that *disappeared* is not reported. A hospital dropping a
        resource from a search answer is far more often a paging artefact or a
        permissions change than a withdrawn order, and acting on it would
        cancel a family's step because of a query result.
        """
        changed = []
        for ref, order in self.orders.items():
            before = previous.orders.get(ref)
            if before is None or order.differs_from(before):
                changed.append(order)
        return tuple(changed)


@runtime_checkable
class HospitalCalendar(Protocol):
    """An HMS that publishes when its providers are away.

    Separate from `HospitalSystem` because it is genuinely optional: Bahmni's
    appointment API has no such concept, and an adapter that had to fake one
    would be worse than an adapter that says it cannot answer. Checked with
    `isinstance` at the call site, which for a `runtime_checkable` Protocol
    asks exactly the right question — does this adapter have the method.
    """

    def providers_away(self, *, start: date, end: date) -> tuple[ProviderAway, ...]:
        """Leave, holidays and closures overlapping the window."""
        ...


@runtime_checkable
class HospitalOrders(Protocol):
    """An HMS that publishes the status of its lab and imaging orders."""

    def open_orders(self, *, patient_refs: tuple[str, ...] = ()) -> tuple[HospitalOrder, ...]:
        """Every order not yet finished, optionally narrowed to some patients."""
        ...


class HospitalSystem(Protocol):
    """The seam. Four questions and two requests, and nothing else.

    Two optional capabilities sit alongside it — `HospitalCalendar` and
    `HospitalOrders` — for the things only some HMSs publish. They are not
    folded in here because a required method an adapter cannot honestly
    implement is how a seam starts lying.
    """

    #: Shown in `GET /api/live` so the console can say which HMS answered.
    name: str

    @property
    def live(self) -> bool:
        """Whether this adapter is actually talking to an HMS over the wire."""
        ...

    def services(self) -> tuple[HospitalService, ...]:
        """Everything bookable, so a slot search knows what it may offer."""
        ...

    def appointments(self, *, start: date, end: date) -> tuple[HospitalAppointment, ...]:
        """Every appointment in the window, whatever its status.

        Cancelled ones are included and must be: they are how a lost slot is
        discovered at all.
        """
        ...

    def book(
        self,
        *,
        patient_ref: str,
        service_ref: str,
        starts_at: datetime,
        ends_at: datetime,
        note: str = "",
    ) -> HospitalAppointment:
        """Hold a slot. Raises `HospitalUnavailable` rather than returning None.

        A booking is the one thing here that changes the hospital's own records,
        so it fails loudly: a caller that cannot tell a refusal from a success
        would tell a family to travel on a date the hospital never agreed to.
        """
        ...

    def cancel(self, appointment_ref: str, *, note: str = "") -> HospitalAppointment:
        """Release a slot we hold, and return it in its new state."""
        ...
