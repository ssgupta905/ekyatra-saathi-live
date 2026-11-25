"""What a family asked for, as something a person can check before it moves anything.

The two existing stories start at the hospital. This is the other half: the
family writes in and wants a visit moved, because there is a wedding, or the
harvest, or the fare is not there this month. Those are the ordinary reasons a
plan actually changes, and a system that only reacts to machines breaking is
only half built.

The shape here matters. An inbound message is prose; the planner needs a
constraint. Turning one into the other is a reading task, which is a legitimate
job for a language model — and precisely the kind of reading that must not be
believed on sight. So `PatientRequest` is a *proposal*: the model fills it in,
`confirmed_by` stays empty, and nothing is re-planned until a navigator has
agreed that is what the family said. Mishearing "after the 20th" as "on the
20th" is a wasted journey, and the cost of asking is one tap.

Note what the family asks for and what they get are allowed to differ. Priya
asks to move dose 14 later; the planner may find that moving it three days
*earlier* keeps the schedule and clears the wedding. Saathi offers the better
option rather than the requested one, and a person still chooses. Doing what was
asked is not the same as helping.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import Field

from .enums import StepKind
from .models import Base


class RequestIntent(StrEnum):
    """What the family is asking for. Deliberately few and deliberately logistical."""

    #: "We cannot come on the 11th" — move a booked visit.
    MOVE_VISIT = "move_visit"
    #: "Can we do the blood test in Patna?" — somewhere nearer or more convenient.
    CHANGE_CENTRE = "change_centre"
    #: "What is happening with dose 13?" — no change wanted, just told.
    ASK_STATUS = "ask_status"
    #: Money, papers, transport. Routed to the social-work desk, not the planner.
    NEEDS_HELP = "needs_help"
    #: The model could not tell. A navigator reads the message themselves.
    UNCLEAR = "unclear"


class RequestConstraint(Base):
    """The dates a family can and cannot manage.

    All optional: a message often carries only one side of it. `not_before` and
    `not_after` are what the planner can actually act on; `reason` is for the
    navigator and never enters a decision.
    """

    not_before: date | None = None
    not_after: date | None = None
    #: Specific dates the family has said they cannot travel.
    excluded_dates: tuple[date, ...] = ()
    #: In the family's own words, for the human reading it.
    reason: str = ""


class TravelFacts(Base):
    """What the family said about getting there, in their own words and figures.

    **This is the one place in the project that holds an amount of money, and
    the reason is narrow enough to state in full.** `domain/budget.py` refuses
    to hold a price because the system must never report a fare it was not
    given, and `domain/affordability.py` refuses to guess a tier for the same
    reason. Both still hold. What is recorded here is not an estimate, a quote
    or a total: it is a number the family themselves said out loud, kept
    alongside the sentence they said it in.

    That distinction is the whole of it. "The tickets will be nine hundred"
    is evidence, and a system that threw it away would ask the same family the
    same question every month. "The tickets will be about nine hundred",
    offered by Saathi, would be an invention — there is no fare source behind
    it — and nothing in this codebase may produce that. So Saathi asks, the
    family answers, and the Console shows the answer attributed to them.

    `refundable` is the field that changes a decision rather than decorating
    one. A refundable ticket means a visit can move; a non-refundable one
    means the money is already spent and moving the visit spends it twice.
    `ReadinessItem.alternative_available` is not this: it means another
    provider exists, which is a different question.
    """

    #: How many people are travelling with the patient. None when not asked
    #: or not answered — never 0 as a stand-in for "we did not ask".
    companions: int | None = None
    #: Whether they can do it in one day and go home. Changes whether a night's
    #: stay has to be arranged at all.
    single_day_trip: bool | None = None
    #: The family's own figure for the journey, in rupees. Never computed.
    stated_cost_inr: int | None = None
    #: Whether a booking they have already made can be changed.
    refundable: bool | None = None
    #: The sentence the figures were read out of, so a navigator can check the
    #: transcription against what was recorded. Required if anything above is
    #: set — see `PatientRequest.travel_is_attributable`.
    stated_in: str = Field(default="", max_length=400)

    @property
    def anything_said(self) -> bool:
        return any(
            value is not None
            for value in (
                self.companions,
                self.single_day_trip,
                self.stated_cost_inr,
                self.refundable,
            )
        )


class PatientRequest(Base):
    """A reading of what the family asked, waiting for a person to agree with it."""

    id: str
    patient_id: str
    #: The message this was read out of, verbatim.
    raw_text: str
    gloss: str | None = None
    intent: RequestIntent
    #: Which step they want moved, when they named one.
    step_kind: StepKind | None = None
    constraint: RequestConstraint = Field(default_factory=RequestConstraint)
    #: Companions, cost and refundability, when the family said them.
    travel: TravelFacts = Field(default_factory=TravelFacts)
    #: The model's own view of how clear the message was. Low confidence does
    #: not block anything by itself — a navigator confirms either way — but it
    #: tells them how hard to look.
    confidence: str = "low"
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    #: Set when a navigator agrees this is what the family meant. Until then the
    #: planner has not seen it.
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    #: Set when a navigator says the reading was wrong, with what they corrected.
    rejected_reason: str | None = None

    @property
    def actionable(self) -> bool:
        """Whether the planner may act on this yet."""
        return (
            self.confirmed_by is not None
            and self.rejected_reason is None
            and self.intent in (RequestIntent.MOVE_VISIT, RequestIntent.CHANGE_CENTRE)
        )

    @property
    def travel_is_attributable(self) -> bool:
        """Whether every travel fact recorded can be traced to an utterance.

        A figure without the sentence it came from is indistinguishable from a
        figure this system made up, which is exactly the thing it may not do.
        The Console refuses to display travel facts that fail this.
        """
        return not self.travel.anything_said or bool(self.travel.stated_in.strip())

    @property
    def needs_a_person(self) -> bool:
        """Intents the planner cannot help with, which a human must pick up."""
        return self.intent in (RequestIntent.NEEDS_HELP, RequestIntent.UNCLEAR)

    def summary(self) -> str:
        """One line for the navigator's queue."""
        if self.intent is RequestIntent.MOVE_VISIT:
            window = []
            if self.constraint.not_before:
                window.append(f"not before {self.constraint.not_before:%d %b}")
            if self.constraint.not_after:
                window.append(f"not after {self.constraint.not_after:%d %b}")
            step = self.step_kind.value.replace("_", " ") if self.step_kind else "a visit"
            return f"asks to move {step}" + (f" — {', '.join(window)}" if window else "")
        if self.intent is RequestIntent.CHANGE_CENTRE:
            return "asks whether this can happen somewhere nearer"
        if self.intent is RequestIntent.ASK_STATUS:
            return "asks what is happening"
        if self.intent is RequestIntent.NEEDS_HELP:
            return "needs help with money, papers or transport"
        return "message could not be read — please read it yourself"
