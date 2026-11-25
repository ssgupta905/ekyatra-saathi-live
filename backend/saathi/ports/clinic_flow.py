"""How far behind a clinic is running, from timestamps nobody types.

This port exists because of one gap, and the gap is worth stating precisely
because it is the only reason there is a second way into the hospital at all.

OpenEMR records every change of appointment status as a new row in
`patient_tracker_element`, stamped `start_datetime = NOW()`. That happens on
the ordinary calendar save a clerk already performs — nobody is asked to do
anything extra, and nobody marks the clinic as "running late", because no such
field exists. The information is there as a side effect of normal work.

**FHIR gives the state and not the clock.** `Appointment.status` does flip to
`arrived`, and that flip is pollable. But *when* they arrived is not in the
resource, and OpenEMR maps both "Arrived" and "Arrived late" onto the same
FHIR status — so over FHIR you cannot even tell that a clerk flagged somebody
late, let alone compute a wait. `Encounter` is no help: its status is
hardcoded `finished` and its period has a start and never an end.

So the minutes come from a read-only database view. That is consistent with
leaving OpenEMR unchanged — it is a `SELECT`, it writes nothing, and every
write this system makes still goes through the standard API. What it is not is
*required*: an adapter that cannot answer returns `None`, and the Console then
says a family has arrived without claiming to know how long they have waited.
A guessed delay would be worse than no delay, because a family rearranges
their day around it.

**The number that matters is not one patient's lateness.** A single patient
arriving late says nothing about the clinic. Arrived-and-not-yet-in-a-room,
counted across everyone, is what says the clinic is behind — and it is what
lets Saathi tell a family to leave at 1:30 instead of 11:30.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Arrival:
    """One patient's passage through a clinic session, as timestamps.

    Every field after `scheduled_at` is optional, because each is only known
    once somebody has saved the corresponding status. A patient who has
    arrived and not been seen has `arrived_at` and nothing else, which is
    precisely the state that makes a clinic late.
    """

    #: The hospital's own appointment id, so this can be matched to a slot.
    appointment_ref: str
    #: The hospital's own patient id.
    patient_ref: str
    scheduled_at: datetime
    arrived_at: datetime | None = None
    in_room_at: datetime | None = None
    departed_at: datetime | None = None
    #: Whether a clerk chose "Arrived late" over "Arrived". Invisible over
    #: FHIR, which maps both onto `arrived`.
    flagged_late: bool = False

    @property
    def is_waiting(self) -> bool:
        """Arrived, and not yet taken into a room or gone home."""
        return (
            self.arrived_at is not None
            and self.in_room_at is None
            and self.departed_at is None
        )

    def waited(self, until: datetime) -> timedelta | None:
        """How long this patient has been waiting, or waited.

        `None` when they have not arrived: a patient who is not there has not
        waited zero minutes, and reporting zero would pull a clinic's measured
        delay towards "on time" with every no-show.
        """
        if self.arrived_at is None:
            return None
        end = self.in_room_at or self.departed_at or until
        return max(end - self.arrived_at, timedelta())

    def waited_past_appointment(self, until: datetime) -> timedelta | None:
        """How long past their appointment time they are still waiting.

        This, rather than `waited`, is what a family feels. A patient who
        turned up two hours early and has been sitting there is not evidence
        that the clinic is late.
        """
        if self.arrived_at is None:
            return None
        end = self.in_room_at or self.departed_at or until
        return max(end - self.scheduled_at, timedelta())


@dataclass(frozen=True)
class ClinicFlow:
    """A clinic session as its own timestamps describe it."""

    #: The day this describes.
    on: date
    #: When the read happened, which is what an ongoing wait is measured to.
    observed_at: datetime
    arrivals: tuple[Arrival, ...] = ()

    @property
    def waiting(self) -> tuple[Arrival, ...]:
        return tuple(arrival for arrival in self.arrivals if arrival.is_waiting)

    @property
    def seen(self) -> tuple[Arrival, ...]:
        return tuple(arrival for arrival in self.arrivals if arrival.in_room_at is not None)

    def running_behind(self) -> timedelta | None:
        """How far behind the clinic is, or None when it cannot be said.

        The median of how long each arrived patient has waited past their own
        appointment time. Median rather than mean because one patient who
        waited four hours for a reason of their own should not become the
        number a dozen families are told.

        `None` when nobody has arrived yet. There is no such thing as a clinic
        that is zero minutes behind before it has seen anybody, and saying
        "on time" then would be a claim about the future.
        """
        waits = [
            waited
            for arrival in self.arrivals
            if (waited := arrival.waited_past_appointment(self.observed_at)) is not None
        ]
        if not waits:
            return None
        return median(sorted(waits))

    def is_behind_by(self, threshold: timedelta) -> bool:
        """Whether the delay is big enough to be worth telling a family.

        A clinic that is eight minutes late is a clinic running normally.
        Messaging a family about it would train them to ignore messages.
        """
        behind = self.running_behind()
        return behind is not None and behind >= threshold

    def summary(self) -> str:
        """One line a navigator can read without expanding anything."""
        behind = self.running_behind()
        if behind is None:
            return f"{self.on}: nobody has arrived yet"
        minutes = int(behind.total_seconds() // 60)
        return (
            f"{self.on}: running about {minutes} min behind "
            f"({len(self.waiting)} waiting, {len(self.seen)} seen)"
        )


@runtime_checkable
class ClinicFlowSource(Protocol):
    """Something that can say how a clinic session is actually running.

    Optional, like `HospitalCalendar` and `HospitalOrders`. Most HMSs cannot
    answer this, and the honest response to not having it is a Console that
    reports arrival without a delay — not an estimate.
    """

    def clinic_flow(self, *, on: date) -> ClinicFlow | None:
        """The session's arrivals, or None when this cannot be read."""
        ...


__all__ = [
    "Arrival",
    "ClinicFlow",
    "ClinicFlowSource",
]
