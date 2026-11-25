"""The connector: what the hospital system changed, and what that means here.

One job, in one direction most of the time. Read the HMS's appointments, work
out what moved since the last read, and push each change into the runner's
*existing* paths — `raise_disruption` for a slot that went away, `update_step`
for one that moved. Nothing here sends a message, decides a plan or writes to
the ledger directly. It could not, and that is the design: the holding message,
the re-plan, the options, the approval gate and the audit rows all already
happen downstream of `raise_disruption`, and a connector that reached past them
would be a second way for the hospital to reach a family, with none of the
checks the first way has.

Three facts about Bahmni shape everything below.

**No change feed.** An appointment has `dateCreated` and no `dateChanged`, so
there is nothing to poll a cursor against. Every cycle reads the whole window
and `AppointmentSnapshot.diff` decides what is new. That is why the window is
bounded and why the first read is primed rather than reported — otherwise
starting the process would raise a disruption for every patient at once.

**A cancellation is the signal.** Real hospitals do not publish "the MRI is
broken". The radiology desk blocks the modality and the booked slots are
cancelled, so a cancelled appointment is the most honest thing there is to
watch, and it is exactly what a judge pressing a button in Bahmni produces.

**Our own writes come back.** Approving an option books a slot in Bahmni, and
the very next poll sees it. Left alone the connector would read our own
booking as a hospital-side change and re-plan the family it was just planned
for, so every write records its reference and the next diff ignores it once.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from ..domain.enums import DisruptionKind, ResourceKind, SourceSystem, StepStatus
from ..domain.models import CareStep, Resource
from ..language.questions import AskReason, AskTopic
from ..ports.clinic_flow import ClinicFlow, ClinicFlowSource
from ..ports.hospital import (
    AppointmentChange,
    AppointmentSnapshot,
    HospitalAppointment,
    HospitalCalendar,
    HospitalOrder,
    HospitalOrders,
    HospitalSystem,
    HospitalUnavailable,
    OrderSnapshot,
    ProviderAway,
)

logger = logging.getLogger(__name__)

#: How many recent changes the situation feed keeps. A board, not a log.
_RECENT_LIMIT = 40

#: How far behind a clinic has to be before a family is told. A clinic eight
#: minutes late is a clinic running normally, and messaging about it teaches a
#: family to ignore messages — which costs them the one that mattered.
_WORTH_TELLING = timedelta(minutes=45)

#: Which kind of disruption a lost slot is, by what the resource is. A machine
#: that stops is not the same event as a clinician on leave, and the family's
#: holding message says so.
_DISRUPTION_OF: dict[ResourceKind, DisruptionKind] = {
    ResourceKind.MACHINE: DisruptionKind.MACHINE_DOWN,
    ResourceKind.STAFF: DisruptionKind.STAFF_UNAVAILABLE,
    ResourceKind.SUPPLY: DisruptionKind.STOCK_DELAY,
}


@dataclass
class HospitalLinks:
    """Which family and which machine *this hospital's* appointment is about.

    The pilot's mapping, stated plainly: **the identifier the hospital system
    holds for a patient is that patient's id here**, and an appointment service
    is named after the resource it books. Our own Bahmni seed writes both, so
    the demo is consistent by construction.

    A real pilot replaces this class and nothing else. It is deliberately the
    only place a hospital's identifier scheme is assumed, so that assumption is
    one file to find rather than a string comparison buried in the poller.

    Everything is scoped by `hospital_id`, and that is not tidiness. Two
    hospitals both run an "MRI-1" and both have patients; matching globally
    would attach a district hospital's cancellation to a cancer centre's
    machine, and the first symptom would be a family told the wrong thing.
    """

    world: object
    #: Which hospital this connector speaks for. Empty means "match anywhere",
    #: which is only correct when exactly one hospital is connected.
    hospital_id: str = ""

    def _mine(self, hospital_id: str) -> bool:
        return not self.hospital_id or hospital_id == self.hospital_id

    def patient_for(self, appointment: HospitalAppointment) -> str | None:
        """Our patient id, or None if this appointment is not one of ours.

        Most appointments in a hospital are not. Returning None for them is the
        normal case, not a failure, and it must stay silent — a log line per
        unmatched appointment per three seconds would bury everything else.
        """
        identifier = (appointment.patient_identifier or "").strip()
        if not identifier:
            return None
        for patient in self.world.patients():  # type: ignore[attr-defined]
            if not self._mine(patient.hospital_id):
                continue
            if patient.id == identifier:
                return patient.id
            if patient.abha_number and patient.abha_number == identifier:
                return patient.id
        return None

    def resource_for(self, appointment: HospitalAppointment) -> Resource | None:
        """The bookable thing this appointment holds, as we know it."""
        wanted = (appointment.service_name or "").strip().casefold()
        if not wanted:
            return None
        resources: dict = self.world.resources  # type: ignore[attr-defined]
        for resource in resources.values():
            if not self._mine(resource.hospital_id):
                continue
            if resource.id.casefold() == wanted:
                return resource
            if resource.display_name.strip().casefold() == wanted:
                return resource
        return None

    def resource_of_step(
        self, appointment: HospitalAppointment, hospital_id: str
    ) -> Resource | None:
        """Which machine this booking is for, according to our own records.

        The hospital's word is better when it gives one. When it does not,
        the step we hold for that family on that day names its resource, and
        that is a fact a desk entered rather than a guess.
        """
        patient_id = self.patient_for(appointment)
        if patient_id is None:
            return None
        step = self.step_for(patient_id, None, appointment.day)
        if step is None or not step.resource_id:
            return None
        resource = self.world.resources.get(step.resource_id)  # type: ignore[attr-defined]
        if resource is None or not self._mine(resource.hospital_id):
            return None
        return resource

    def step_for(
        self, patient_id: str, resource: Resource | None, on_day: date | None
    ) -> CareStep | None:
        """The care step this appointment is the booking for.

        By named resource first, because that is unambiguous; by the date it
        sits on only as a fallback, and only among steps that are still waiting
        to happen. A completed step is never matched: a hospital re-reading an
        old appointment must not reopen a journey that has moved on.
        """
        rows: tuple[CareStep, ...] = self.world.steps_for(patient_id)  # type: ignore[attr-defined]
        open_rows = [
            row
            for row in rows
            if row.status in (StepStatus.NOT_SCHEDULED, StepStatus.SCHEDULED)
        ]
        if resource is not None:
            for row in open_rows:
                if row.resource_id == resource.id:
                    return row
            for row in open_rows:
                if row.queue and row.queue == resource.department:
                    return row
        if on_day is not None:
            for row in open_rows:
                if row.scheduled_for == on_day:
                    return row
        return None


@dataclass
class HospitalSync:
    """Poll the HMS, and turn what changed into the runner's own events."""

    hospital: HospitalSystem
    runner: object
    #: Which hospital this connector reads. Everything it matches is scoped to
    #: it, and every row it puts on the board is labelled with it.
    hospital_id: str = ""
    window_days: int = 30
    #: The hospital's own timezone. Bahmni speaks UTC instants and the planner
    #: speaks the hospital's calendar dates; this is the only thing that can
    #: convert between them, and getting it wrong moves an evening appointment
    #: to the previous day.
    timezone: str = "Asia/Kolkata"
    #: The last full read, diffed against the next one.
    snapshot: AppointmentSnapshot = field(default_factory=AppointmentSnapshot)
    #: Appointment references this system created or cancelled itself. The next
    #: diff that sees one drops it and forgets it, so our own write-back does
    #: not read back as a change the hospital made.
    _ours: set[str] = field(default_factory=set)
    #: Counts, surfaced in `GET /api/live` so a silent connector is visible.
    counts: dict[str, int] = field(default_factory=dict)
    #: The last error, so the console can say why the pane is stale rather than
    #: simply showing nothing.
    last_error: str = ""
    last_read_at: datetime | None = None
    #: The newest changes, newest first, for the panel's "hospital right now".
    #: A ring rather than a log: this is a live situation board, and a desk
    #: scrolling back through yesterday is reading the audit trail instead.
    recent: list[dict] = field(default_factory=list)
    #: Leave this connector has already acted on, so a provider who is away
    #: for a week does not raise the same disruption on every poll.
    _seen_leave: set[str] = field(default_factory=set)
    #: Orders, compared by snapshot rather than watermark. `ServiceRequest`'s
    #: `_lastUpdated` maps to `date_ordered`, which never moves when a status
    #: does — a cursor over orders would run forever and see nothing. Same
    #: mechanism as `AppointmentSnapshot`, for exactly one reason to learn.
    orders: OrderSnapshot = field(default_factory=OrderSnapshot)
    _orders_primed: bool = False
    #: How the clinic is running today, when a source can tell us. `None`
    #: means nobody can, and the Console must then claim no delay at all.
    flow: ClinicFlow | None = None
    #: Days a family has already been told the clinic is behind, so a slow
    #: morning does not become a message every three seconds.
    _told_behind: set[str] = field(default_factory=set)

    @property
    def links(self) -> HospitalLinks:
        return HospitalLinks(
            world=self.runner.world,  # type: ignore[attr-defined]
            hospital_id=self.hospital_id,
        )

    def expect(self, appointment_ref: str) -> None:
        """Note a reference we wrote ourselves, so the next diff ignores it."""
        if appointment_ref:
            self._ours.add(appointment_ref)

    async def poll_once(self) -> tuple[AppointmentChange, ...]:
        """One cycle: read the window, diff it, act on what moved."""
        if not self.hospital.live:
            return ()

        world = self.runner.world  # type: ignore[attr-defined]
        today = world.today
        start = today - timedelta(days=self.window_days)
        end = today + timedelta(days=self.window_days)

        try:
            latest = await asyncio.to_thread(self.hospital.appointments, start=start, end=end)
        except HospitalUnavailable as exc:
            # Fail closed and stay quiet about it after the first time: an HMS
            # that is down for a minute should not write a hundred log lines,
            # and the console already shows the staleness.
            if str(exc) != self.last_error:
                logger.warning("hospital unreachable: %s", exc)
            self.last_error = str(exc)
            self._bump("unreachable")
            return ()

        self.last_error = ""
        self.last_read_at = datetime.now()
        self._bump("read")

        first_read = not self.snapshot.primed
        changes = self.snapshot.diff(latest)
        if first_read:
            logger.info(
                "hospital connector primed: %d appointments in the window", len(latest)
            )
            return ()

        acted: list[AppointmentChange] = []
        for change in changes:
            if change.after.ref in self._ours:
                # Our own write coming back. Drop it once; a later, genuine
                # change to the same appointment must still be seen.
                self._ours.discard(change.after.ref)
                self._bump("echo")
                continue
            if await self._act(change):
                acted.append(change)

        # Three signals that are not appointment changes, each from an HMS
        # that may or may not publish it. An adapter without the capability is
        # skipped silently — that is the honest outcome, and `GET /api/live`
        # already shows which adapter is connected.
        await self._poll_leave(start=start, end=end)
        await self._poll_orders()
        await self._poll_clinic_flow(today)
        return tuple(acted)

    # ---------------- who is away ----------------

    async def _poll_leave(self, *, start: date, end: date) -> None:
        """Read published leave, and act on the visits it collides with.

        Leave is not a change to an appointment, so the appointment diff never
        sees it: the slot sits there looking perfectly booked while the person
        who would have seen the family is away. That is the whole of story
        one, and nothing in the appointment stream can tell you about it.
        """
        if not isinstance(self.hospital, HospitalCalendar):
            return
        try:
            away = await asyncio.to_thread(
                self.hospital.providers_away, start=start, end=end
            )
        except HospitalUnavailable as exc:
            self._note_error(exc, "leave")
            return

        for leave in away:
            if leave.ref in self._seen_leave:
                continue
            self._seen_leave.add(leave.ref)
            self._bump("leave")
            await self._act_on_leave(leave)

    async def _act_on_leave(self, leave: ProviderAway) -> None:
        """Find the families this leave collides with, and ask them."""
        colliding = self._collisions(leave)
        if not colliding:
            logger.info(
                "hospital: %s from %s affects nobody we are tracking",
                leave.kind,
                leave.starts_at.date().isoformat(),
            )
            return

        day = leave.starts_at.date()
        for patient_id, appointment in colliding:
            self._bump("leave:collision")
            logger.info(
                "hospital: %s is away on %s and %s is booked with them",
                leave.provider_display or leave.provider_ref or "a provider",
                day.isoformat(),
                patient_id,
            )
            self._remember_signal(
                kind="leave",
                patient_id=patient_id,
                summary=(
                    f"{leave.provider_display or 'a provider'} is away on "
                    f"{day:%d %b}; {patient_id} is booked at "
                    f"{appointment.starts_at:%H:%M}"
                ),
            )
            # Ask before planning. A new date needs to fit the family's week,
            # their money and who can come with them, and none of that is in
            # the hospital's record — see `language/questions.py`.
            await self.runner.ask_family(  # type: ignore[attr-defined]
                patient_id,
                reason=AskReason.DOCTOR_AWAY,
                topics=(AskTopic.TIMING, AskTopic.COMPANIONS, AskTopic.COST),
                about_day=day,
            )

    def _collisions(
        self, leave: ProviderAway
    ) -> list[tuple[str, HospitalAppointment]]:
        """Appointments inside the leave, with the provider who is away.

        A facility-wide closure matches every appointment that day; leave for
        one provider matches only theirs. Matching is on the provider's
        display name when there is no reference to compare, because OpenEMR
        degrades a `Practitioner` reference to a `Person` one when the user
        has no NPI — so a name is sometimes all there is.
        """
        found: list[tuple[str, HospitalAppointment]] = []
        for appointment in self.snapshot.by_ref.values():
            if not appointment.state.is_open:
                continue
            if not leave.covers(appointment.starts_at):
                continue
            if not leave.is_facility_wide and not _same_provider(leave, appointment):
                continue
            patient_id = self.links.patient_for(appointment)
            if patient_id:
                found.append((patient_id, appointment))
        return found

    # ---------------- what is still outstanding ----------------

    async def _poll_orders(self) -> None:
        """Diff the open orders, and act on any whose state moved."""
        if not isinstance(self.hospital, HospitalOrders):
            return
        try:
            latest = await asyncio.to_thread(self.hospital.open_orders)
        except HospitalUnavailable as exc:
            self._note_error(exc, "orders")
            return

        snapshot = OrderSnapshot.of(latest)
        changed = snapshot.diff(self.orders)
        self.orders = snapshot
        if not self._orders_primed:
            self._orders_primed = True
            logger.info("hospital connector primed: %d open orders", len(latest))
            return

        for order in changed:
            self._bump("order")
            await self._act_on_order(order)

    async def _act_on_order(self, order: HospitalOrder) -> None:
        """An order moved. Ask about the booking if a visit depends on it.

        The question is about the *ticket*, not the date, and that is the
        point of story two: whether the family can change travel they have
        already paid for is what decides between moving the visit and keeping
        it and chasing the report. Nothing in the hospital's record knows it.
        """
        patient_id = self._patient_for_ref(order.patient_ref)
        if patient_id is None:
            return
        self._remember_signal(
            kind="order",
            patient_id=patient_id,
            summary=f"{order.name or 'an order'} is {order.state.value}",
        )
        if not order.state.blocks_dependents:
            # Finished. Re-plan: a step that was waiting on it may now move.
            await self.runner.plan_patient(patient_id)  # type: ignore[attr-defined]
            return

        day = order.ordered_at.date() if order.ordered_at else self.runner.world.today  # type: ignore[attr-defined]
        await self.runner.ask_family(  # type: ignore[attr-defined]
            patient_id,
            reason=AskReason.REPORT_PENDING,
            topics=(AskTopic.BOOKING, AskTopic.TIMING),
            about_day=day,
        )

    # ---------------- how today is going ----------------

    async def _poll_clinic_flow(self, today: date) -> None:
        """Read today's arrivals, and tell families only if it is worth it.

        This never raises a disruption. The clinic running late is not a lost
        slot: the visit will happen, later, and what the family needs is to
        leave home later rather than sit in a corridor. Treating it as a
        disruption would cancel and re-plan a visit that is going ahead.
        """
        if not isinstance(self.hospital, ClinicFlowSource):
            return
        flow = await asyncio.to_thread(self.hospital.clinic_flow, on=today)
        self.flow = flow
        if flow is None:
            # Nobody can tell us. The Console says "arrived" and no more.
            return

        if not flow.is_behind_by(_WORTH_TELLING):
            return
        key = today.isoformat()
        if key in self._told_behind:
            return
        self._told_behind.add(key)
        self._bump("behind")

        behind = flow.running_behind()
        assert behind is not None  # guaranteed by is_behind_by
        logger.info("hospital: %s", flow.summary())
        for arrival in flow.arrivals:
            patient_id = self._patient_for_ref(f"Patient/{arrival.patient_ref}")
            if patient_id is None:
                continue
            self._remember_signal(
                kind="behind",
                patient_id=patient_id,
                summary=flow.summary(),
            )

    def _patient_for_ref(self, patient_ref: str) -> str | None:
        """Our patient id for an HMS patient reference, or None.

        Resolved through the appointments already in the snapshot rather than
        by fetching the patient again: an order and an appointment for the
        same person carry the same `Patient/N` reference, and the appointment
        read has already paid for the identifier we match on. A reference we
        have never seen on an appointment is one we cannot match, which is the
        normal case for the rest of the hospital's patients.
        """
        if not patient_ref:
            return None
        for appointment in self.snapshot.by_ref.values():
            if appointment.patient_ref == patient_ref:
                return self.links.patient_for(appointment)
        return None

    def _note_error(self, exc: Exception, what: str) -> None:
        if str(exc) != self.last_error:
            logger.warning("hospital %s unreadable: %s", what, exc)
        self.last_error = str(exc)
        self._bump(f"unreachable:{what}")

    def _remember_signal(self, *, kind: str, patient_id: str, summary: str) -> None:
        """Put a non-appointment signal on the live situation board."""
        self.recent.insert(
            0,
            {
                "kind": kind,
                "hospital_id": self.hospital_id,
                "patient_id": patient_id,
                "summary": summary,
                "at": datetime.now(UTC).isoformat(),
            },
        )
        del self.recent[_RECENT_LIMIT:]

    def _remember(
        self, change: AppointmentChange, *, patient_id: str | None, resource: Resource | None
    ) -> None:
        """Keep one change for the panel's live situation feed.

        `hits_booked_patients` is what the panel sorts on: a change to a family
        who is already travelling outranks everything else on the board,
        because they are the only people who cannot simply be told later.
        """
        self.recent.insert(
            0,
            {
                "at": datetime.now().isoformat(),
                "headline": change.describe(),
                "service": change.after.service_name,
                "resource_id": resource.id if resource else None,
                "patient_id": patient_id,
                "state": change.after.state.value,
                "on": change.after.day.isoformat(),
                "kind": (
                    "slot_lost"
                    if change.became_lost
                    else "slot_booked"
                    if change.is_new
                    else "slot_moved"
                ),
                "hospital_id": self.hospital_id,
                "hits_booked_patients": bool(patient_id) and change.became_lost,
            },
        )
        del self.recent[_RECENT_LIMIT:]

    async def _act(self, change: AppointmentChange) -> bool:
        """Push one change into the runner. True when it was ours to act on."""
        patient_id = self.links.patient_for(change.after)
        resource = self.links.resource_for(change.after)
        if resource is None:
            # The hospital did not say which machine. Most cannot: OpenEMR
            # reports every appointment as "Office Visit" unless somebody has
            # configured its categories, and plenty of systems have no
            # equivalent field at all. Our own records do know — the step this
            # booking is for names its resource — so ask them rather than
            # giving up and re-planning a family without saying what broke.
            resource = self.links.resource_of_step(change.after, self.hospital_id)
        # Remembered whether or not it is one of ours. A hospital's board shows
        # the whole hospital, and the ordinary noise is what makes the one
        # change that matters stand out instead of being the only thing there.
        self._remember(change, patient_id=patient_id, resource=resource)
        if patient_id is None:
            return False

        if change.became_lost:
            await self._slot_lost(patient_id, change, resource)
            return True
        if change.is_new or change.moved:
            await self._slot_moved(patient_id, change, resource)
            return True
        return False

    async def _slot_lost(
        self, patient_id: str, change: AppointmentChange, resource: Resource | None
    ) -> None:
        """A booked slot went away. Raise it as the desk would have.

        The disruption is raised against the resource, not the patient, because
        that is what `affected_patients` matches on — one cancelled MRI slot
        means the machine is blocked, and everybody else booked onto it that
        day is affected too, which is the whole reason a hospital panel sorts
        patients rather than showing one.
        """
        if resource is None:
            logger.info(
                "hospital: %s lost a slot on %r, which maps to no resource here; "
                "re-planning the family without raising a disruption",
                patient_id,
                change.after.service_name,
            )
            self._bump("lost:unmapped")
            await self.runner.plan_patient(patient_id)  # type: ignore[attr-defined]
            return

        day = change.after.day
        self._bump("lost")
        logger.info(
            "hospital: %s on %s was %s — raising it against %s",
            change.after.service_name,
            day.isoformat(),
            change.after.state.value,
            resource.id,
        )
        await self.runner.raise_disruption(  # type: ignore[attr-defined]
            resource_id=resource.id,
            kind=_DISRUPTION_OF.get(resource.kind, DisruptionKind.MACHINE_DOWN),
            unavailable_from=day,
            unavailable_to=day,
            note=change.describe(),
            raised_by=SourceSystem.HOSPITAL_FEED,
        )

    async def _slot_moved(
        self, patient_id: str, change: AppointmentChange, resource: Resource | None
    ) -> None:
        """A slot appeared or moved. Write the new date onto the step."""
        was_on = change.before.day if change.before is not None else None
        step = self.links.step_for(patient_id, resource, was_on)
        if step is None:
            self._bump("moved:unmatched")
            return

        new_day = change.after.day
        if step.scheduled_for == new_day and step.status is StepStatus.SCHEDULED:
            return

        self._bump("moved")
        world = self.runner.world  # type: ignore[attr-defined]
        world.update_step(
            step.id,
            scheduled_for=new_day,
            status=StepStatus.SCHEDULED,
            resource_id=step.resource_id or (resource.id if resource else None),
        )
        self.runner.ledger.record_once(  # type: ignore[attr-defined]
            patient_id=patient_id,
            source=SourceSystem.HOSPITAL_FEED,
            source_record_id=f"appointment:{change.after.ref}",
            claim=change.describe(),
            metadata={
                "state": change.after.state.value,
                "service": change.after.service_name,
                "step_id": step.id,
            },
        )
        await self.runner.plan_patient(patient_id, allow_render=True)  # type: ignore[attr-defined]

    # ---------------- write-back ----------------

    async def rebook(
        self,
        *,
        patient_id: str,
        step: CareStep,
        target_on: date,
        note: str = "",
    ) -> HospitalAppointment | None:
        """Move this step's booking in the HMS to `target_on`.

        Ordering is deliberate: **book the new slot first, then release the
        old one.** The other way round has a window in which the family holds
        nothing at all, and if the booking then fails the hospital has lost a
        slot it was never asked to give up.

        Returns the new appointment, or None when there is nothing to move —
        a step the HMS holds no booking for is a normal state, not an error.
        Every other failure raises `HospitalUnavailable`, because a caller
        that cannot tell a refusal from a success will tell a family to travel
        on a date the hospital never agreed to.
        """
        if not self.hospital.live:
            return None

        previous = self.booking_for(patient_id, step)
        service_ref = previous.service_ref if previous else self._service_ref_for(step)
        if not service_ref:
            logger.info(
                "hospital: no service to rebook %s against; leaving the HMS alone", step.id
            )
            self._bump("rebook:no-service")
            return None

        patient_ref = self._patient_ref_for(patient_id, previous)
        if not patient_ref:
            logger.info(
                "hospital: no HMS patient reference for %s; leaving the HMS alone", patient_id
            )
            self._bump("rebook:no-patient")
            return None

        starts_at, ends_at = self._slot_instants(step, target_on, previous)

        booked = await asyncio.to_thread(
            self.hospital.book,
            patient_ref=patient_ref,
            service_ref=service_ref,
            starts_at=starts_at,
            ends_at=ends_at,
            note=note or "Rescheduled by Saathi after a hospital-side change",
        )
        self.expect(booked.ref)
        self._bump("booked")

        if previous is not None and previous.state.is_open and previous.ref != booked.ref:
            released = await asyncio.to_thread(
                self.hospital.cancel,
                previous.ref,
                note="Replaced by the rescheduled appointment",
            )
            self.expect(released.ref)
            self.snapshot.by_ref[released.ref] = released
            self._bump("released")

        # Adopt both immediately so the very next poll does not see them as
        # news even if the echo guard is consumed by something else first.
        self.snapshot.by_ref[booked.ref] = booked
        logger.info(
            "hospital: booked %s for %s at %s",
            booked.service_name or booked.service_ref,
            patient_id,
            booked.starts_at.isoformat(),
        )
        return booked

    def booking_for(self, patient_id: str, step: CareStep) -> HospitalAppointment | None:
        """The appointment the HMS holds for this step, from the last read.

        Prefers one that is still open; falls back to the most recent lost one,
        because the slot a judge just cancelled is exactly the one whose
        service and time we want to rebook against.
        """
        links = self.links
        candidates = [
            appointment
            for appointment in self.snapshot.by_ref.values()
            if links.patient_for(appointment) == patient_id
        ]
        if not candidates:
            return None

        resource = self.runner.world.resources.get(step.resource_id or "")  # type: ignore[attr-defined]
        if resource is not None:
            named = [
                a
                for a in candidates
                if (a.service_name or "").strip().casefold()
                in (resource.id.casefold(), resource.display_name.strip().casefold())
            ]
            if named:
                candidates = named

        open_ones = [a for a in candidates if a.state.is_open]
        if open_ones:
            return min(open_ones, key=lambda a: a.starts_at)
        return max(candidates, key=lambda a: a.starts_at)

    def _patient_ref_for(
        self, patient_id: str, previous: HospitalAppointment | None
    ) -> str:
        if previous is not None and previous.patient_ref:
            return previous.patient_ref
        for appointment in self.snapshot.by_ref.values():
            if self.links.patient_for(appointment) == patient_id and appointment.patient_ref:
                return appointment.patient_ref
        return ""

    def _service_ref_for(self, step: CareStep) -> str:
        """Find the service by the resource's name, when we hold no booking."""
        resource = self.runner.world.resources.get(step.resource_id or "")  # type: ignore[attr-defined]
        if resource is None:
            return ""
        wanted = {resource.id.casefold(), resource.display_name.strip().casefold()}
        try:
            services = self.hospital.services()
        except HospitalUnavailable:
            return ""
        for service in services:
            if service.name.strip().casefold() in wanted:
                return service.ref
        return ""

    def _slot_instants(
        self, step: CareStep, target_on: date, previous: HospitalAppointment | None
    ) -> tuple[datetime, datetime]:
        """What moment on `target_on` to book, and for how long.

        A `PlanOption` carries a date, not a time — the planner reasons in
        hospital days. The hospital's own rules do carry times, so those come
        first; the slot we are replacing is the next best answer, because a
        family told "same time, different day" has less to re-arrange. Only if
        neither exists does this fall back to a fixed morning hour, and that
        fallback is a guess the hospital did not make.
        """
        zone = self._zone()
        minutes = 30
        local_time: time | None = None

        policy = self._policy_for(step)
        if policy is not None:
            configured = policy.step(step.kind)
            slot_times = getattr(configured, "slot_times", ()) if configured else ()
            if slot_times:
                local_time = _parse_clock(slot_times[0])

        if local_time is None and previous is not None:
            local = previous.starts_at.astimezone(zone)
            local_time = local.time()
            minutes = max(
                5, int((previous.ends_at - previous.starts_at).total_seconds() // 60) or 30
            )

        if local_time is None:
            local_time = time(9, 0)

        starts_at = datetime.combine(target_on, local_time, tzinfo=zone)
        return starts_at, starts_at + timedelta(minutes=minutes)

    def _policy_for(self, step: CareStep):
        rules = getattr(self.runner.planner, "rules_for", None)  # type: ignore[attr-defined]
        patient = self.runner.world.patient(step.patient_id)  # type: ignore[attr-defined]
        if rules is None or patient is None:
            return None
        try:
            return rules(patient.hospital_id)
        except Exception:  # noqa: BLE001 - bad saved rules must not block a booking
            logger.exception("could not read saved rules; booking without them")
            return None

    def _zone(self) -> tzinfo:
        try:
            return ZoneInfo(self.timezone)
        except Exception:  # noqa: BLE001 - a bad tz name must not stop a booking
            logger.warning("unknown timezone %r; booking in UTC", self.timezone)
            return UTC

    def snapshot_json(self) -> dict:
        """What the console shows about the connector itself."""
        return {
            "hospital_id": self.hospital_id,
            "system": self.hospital.name,
            "live": self.hospital.live,
            "window_days": self.window_days,
            "appointments": len(self.snapshot.by_ref),
            "primed": self.snapshot.primed,
            "last_read_at": self.last_read_at.isoformat() if self.last_read_at else None,
            "last_error": self.last_error,
            "counts": dict(self.counts),
            "recent": list(self.recent),
        }

    def _bump(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1


def _same_provider(leave: ProviderAway, appointment: HospitalAppointment) -> bool:
    """Whether this appointment is with the provider who is away.

    **The reference first, and the name only as a fallback.** This was
    originally written the other way round and matched nobody against a real
    OpenEMR: its provider events carry a `Practitioner` reference and no
    display name, while its appointments carry both — so a name-first
    comparison compared an empty string to a name, declined to match, and
    reported that a doctor's leave affected no families. Silently matching
    nobody is the worst failure available here, because it is indistinguishable
    from a quiet afternoon.

    The name is still worth keeping as a fallback: OpenEMR degrades a
    `Practitioner` reference to a `Person` one when a user has no NPI, so for
    those providers the two sides can carry references of different kinds and
    a name is the only thing that lines up.

    Returns False when there is nothing comparable on either side. Claiming a
    match on no evidence would cancel visits because a calendar was vague.
    """
    if leave.provider_ref and appointment.provider_ref:
        if leave.provider_ref == appointment.provider_ref:
            return True
        # Both named a provider and they differ: that is a real answer, not a
        # reason to go looking for a name that might agree.
        return False

    name = (leave.provider_display or "").strip().casefold()
    theirs = (appointment.provider or "").strip().casefold()
    return bool(name) and name == theirs


def _parse_clock(raw: object) -> time | None:
    """"15:00" -> 15:00. Anything unreadable is None, never a guessed hour."""
    if not isinstance(raw, str):
        return None
    try:
        return time.fromisoformat(raw.strip())
    except ValueError:
        logger.warning("unreadable slot time %r in the hospital's rules; ignoring", raw)
        return None
