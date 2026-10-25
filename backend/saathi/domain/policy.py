"""The hospital's own rules, as data the hospital owns.

Some of what the planner needs is a fact about the world — how far Gaya is from
Mumbai — and that is fetched (`tools/`). The rest is a fact about *this
hospital*: how many days the consultants want scans reported before they meet,
which days that meeting happens, what time the MRI has slots. Those are not
facts anybody can look up, and they are emphatically not for a developer to pick.

They were, briefly, constants in `planner/care_rules.py` with values chosen to
make a demo land on a nice number — which is the exact failure this file exists
to prevent. A constant that was tuned until the output looked right is not a
rule; it is the answer, wearing a rule's clothes. Changing it should change the
plan, and if nobody can change it, nothing was ever computed.

So: policy is stored per hospital, editable from the admin console the brief
already calls for ("Admin · Readiness rules per step"), and every default below
is marked as a default. `confirmed` stays False until a clinician has actually
said yes, and the console shows unconfirmed policy as provisional — the brief's
own "Questions for our advising doctor" page is the list of things sitting in
here waiting for an answer.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field

from .enums import StepKind

#: Monday is 0, matching `date.weekday()`.
WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class StepPolicy(BaseModel):
    """What this hospital does about one kind of step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: StepKind
    #: Days this step must follow each named prerequisite by, when the two
    #: cannot share a visit. Keyed by the prerequisite's `StepKind` value.
    lead_days: dict[str, int] = Field(default_factory=dict)
    #: Days of the week this step can happen at all, `date.weekday()` numbering.
    #: Empty means any day — most steps run whenever there is capacity, but a
    #: standing consultants' meeting does not.
    weekdays: tuple[int, ...] = ()
    #: Clock times this step is bookable at, as "HH:MM". Used for the time of
    #: day on a plan; empty means the desk assigns one.
    slot_times: tuple[str, ...] = ()
    #: How far either way this step may be moved from its booked date before it
    #: stops being the same step. For a maintenance dose this is the interval's
    #: tolerance — the reason a family asking to delay ten days gets offered
    #: three days *earlier* instead. None means the hospital has not said, and
    #: the planner then offers nothing it would have to justify.
    shift_tolerance_days: int | None = None
    #: False until a clinician has confirmed these values. The console marks
    #: anything unconfirmed as provisional rather than quietly showing it as
    #: settled fact.
    confirmed: bool = False
    #: Who said so, when they are confirmed.
    confirmed_by: str | None = None


#: Documents a hospital can ask a family to bring, by id. The vocabulary a
#: hospital's `requirements` are written in; labels are what the family reads.
ENTITLEMENTS: dict[str, str] = {
    "ayushman": "Ayushman Bharat card",
    "state_scheme": "State health scheme card",
    "rail_concession": "Railway concession certificate",
    "hospital_file": "Hospital file / patient ID card",
    "demand_draft": "Demand draft for the pathology fee",
    "blocks_slides": "Outside biopsy blocks or slides",
}


class Centre(BaseModel):
    """A place a step can happen, as the network configures it.

    Deliberately configuration and not a table in the code. Which centres exist,
    and which steps each can handle, is something a health system knows and a
    developer does not — and the whole value of the "nearer centre" option is
    that it is answered from the real network, not from a list somebody typed
    while writing a demo. An empty directory offers no alternatives, which is
    the correct behaviour before anyone has filled it in.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    #: The place name the geo tool resolves — a district or city, so the
    #: distance to it is fetched rather than stored.
    place: str
    #: "hub" or "day_care". Day-care centres handle a narrower set of steps.
    kind: str = "day_care"
    #: `StepKind` values this centre is equipped for.
    handles: tuple[str, ...] = ()

    def can_handle(self, kind: StepKind) -> bool:
        return kind.value in self.handles


class HospitalPolicy(BaseModel):
    """Everything the planner needs to know about how one hospital runs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hospital_id: str
    steps: dict[str, StepPolicy] = Field(default_factory=dict)
    #: A round trip longer than this, and a family stays in the city between
    #: visits rather than travelling home. Compared against the *fetched*
    #: journey duration, not against kilometres. A judgement, so it is set
    #: here and not buried in the itinerary code.
    stay_rather_than_travel_hours: float = 12.0
    #: How much notice a family needs to obtain a reserved long-distance
    #: journey. Not a scheduling constant — a reserved berth from Gaya to
    #: Mumbai cannot be had the day before, and a plan that assumes one is a
    #: plan that strands the family at the station. Varies by corridor and
    #: season, so it is configuration a hospital sets, not a number we assert.
    reservation_lead_days: int = 3
    #: Journeys at least this long need a reservation at all. Below it a family
    #: takes a bus or a local train on the day, and notice costs nothing.
    #: Compared against the *fetched* round-trip duration, like the gap above.
    reserved_journey_hours: float = 8.0
    #: Default gap used when no journey could be fetched at all. Deliberately
    #: small: without a known journey, assuming the family will happily wait a
    #: week in a strange city is the expensive assumption to get wrong.
    unknown_journey_gap_days: int = 2
    #: Centres in this network. Empty until somebody fills it in, and an empty
    #: directory simply offers no nearer-centre option.
    centres: tuple[Centre, ...] = ()
    #: What families are asked to bring, per step kind. Keyed by `StepKind`
    #: value; the ids are `ENTITLEMENTS` keys. Empty means
    #: this hospital has not said, so nothing is demanded on its behalf.
    requirements: dict[str, list[str]] = Field(default_factory=dict)

    def needs_reservation(self, round_trip_hours: float | None) -> bool:
        """Does a journey this long have to be booked in advance?

        Unknown journeys are treated as needing one. Warning a family to book
        early when they did not have to costs them nothing; staying quiet when
        they did costs them the trip.
        """
        if round_trip_hours is None:
            return True
        return round_trip_hours >= self.reserved_journey_hours

    def centre(self, centre_id: str) -> Centre | None:
        return next((c for c in self.centres if c.id == centre_id), None)

    def centres_for(self, kind: StepKind) -> tuple[Centre, ...]:
        return tuple(c for c in self.centres if c.can_handle(kind))

    # ---------------- reads ----------------

    def step(self, kind: StepKind) -> StepPolicy | None:
        return self.steps.get(kind.value)

    def lead_days(self, before: StepKind, after: StepKind) -> int:
        """Days `after` must sit beyond `before` when they cannot share a visit.

        One day when the hospital has not said otherwise: a step cannot happen
        before the thing it depends on, and that is the only claim being made
        in the absence of a stated rule.
        """
        policy = self.step(after)
        if policy is None:
            return 1
        return policy.lead_days.get(before.value, 1)

    def next_slot(self, kind: StepKind, not_before: date) -> date:
        """First day on or after `not_before` this step can actually happen."""
        policy = self.step(kind)
        if policy is None or not policy.weekdays:
            return not_before
        candidate = not_before
        for _ in range(14):
            if candidate.weekday() in policy.weekdays:
                return candidate
            candidate += timedelta(days=1)
        return not_before

    def shift_tolerance(self, kind: StepKind) -> int | None:
        """How far this step may move, per the hospital. None means unstated."""
        policy = self.step(kind)
        return policy.shift_tolerance_days if policy else None

    def slot_time(self, kind: StepKind, index: int = 0) -> str | None:
        policy = self.step(kind)
        if policy is None or not policy.slot_times:
            return None
        return policy.slot_times[min(index, len(policy.slot_times) - 1)]

    def gap_days(self, round_trip_hours: float | None) -> int:
        """How long this family waits in the city before going home instead.

        Driven by the fetched journey, so a family 20 hours from the hospital
        and one 1 hour away get different answers for the same gap — which is
        the whole reason the geo tool exists. With no journey on record this
        falls back to the cautious number rather than guessing.
        """
        if round_trip_hours is None:
            return self.unknown_journey_gap_days
        if round_trip_hours >= self.stay_rather_than_travel_hours:
            # Far enough that going home costs more than waiting. How much more
            # is proportional: the longer the journey, the longer the wait that
            # still beats making it twice.
            return max(2, round(round_trip_hours / 4))
        return self.unknown_journey_gap_days

    @property
    def unconfirmed(self) -> tuple[str, ...]:
        """Step kinds whose rules no clinician has signed off yet."""
        return tuple(
            kind for kind, policy in sorted(self.steps.items()) if not policy.confirmed
        )


def default_policy(hospital_id: str) -> HospitalPolicy:
    """A starting point, explicitly unconfirmed.

    These are not claims about how any hospital works. They are placeholders
    shaped like the real thing so the system runs before anyone has sat down
    with the admin console, and every one of them reports `confirmed=False`
    until somebody who knows says otherwise. The brief's "Questions for our
    advising doctor" is precisely this list.
    """
    return HospitalPolicy(
        hospital_id=hospital_id,
        steps={
            StepKind.PET_CT.value: StepPolicy(
                kind=StepKind.PET_CT,
                lead_days={StepKind.SCAN.value: 2},
                slot_times=("11:00", "14:00"),
            ),
            StepKind.JOINT_CLINIC.value: StepPolicy(
                kind=StepKind.JOINT_CLINIC,
                lead_days={StepKind.PET_CT.value: 3},
                # A standing meeting rather than an appointment, so a scan that
                # slips two days can cost four: the next one is not tomorrow.
                weekdays=(1, 4),
                slot_times=("10:00",),
            ),
            StepKind.SCAN.value: StepPolicy(
                kind=StepKind.SCAN, slot_times=("08:00", "11:00", "15:00")
            ),
            StepKind.ECHO_REVIEW.value: StepPolicy(
                kind=StepKind.ECHO_REVIEW, slot_times=("09:30", "12:00")
            ),
            StepKind.MAINTENANCE_DOSE.value: StepPolicy(
                kind=StepKind.MAINTENANCE_DOSE,
                lead_days={StepKind.ECHO_REVIEW.value: 0},
                slot_times=("14:30",),
                # A placeholder until an oncologist says otherwise, and the
                # console shows it as provisional. How far a dose may slide is
                # exactly the kind of number this project refuses to invent.
                shift_tolerance_days=7,
            ),
        },
    )
