"""Asking a family something, and knowing what they said back.

Until now every inbound message was handled on its own. `receive_inbound`
screened it, stored it, and that was the end — there was no record anywhere
that Saathi had asked anything, so a reply arrived as a message from nobody in
particular, answering nothing in particular. The only pose-and-wait mechanism
in the system was the IVR "press 1", which confirms receipt of a message and
carries no question.

That gap is why the hard cases could not work. "Nothing before the 1st, my
salary comes then" is a complete answer to "which days can you travel?" and
meaningless on its own. A system with no memory of its own question cannot use
the second sentence, and a family who is asked the same thing twice stops
replying.

So one question is open per patient at a time, and this module holds it.

**One, deliberately.** A family on a phone, often read aloud by a neighbour,
cannot be expected to track which of three outstanding questions a reply
belongs to — and neither can this code, honestly. When Saathi needs three
facts it asks for them in one message (`language/questions.py` joins the
sentences) and reads whatever comes back. Anything still missing is asked
again, once.

**A question stays open until it is actually answered.** If a reply fills none
of the fields the question asked about, the reply is not an answer: it is an
ordinary message, handled as one, and the question is still waiting. This is
the behaviour that stops a family's unrelated "where do I go first?" from
being recorded as their travel constraints.

**Questions go stale.** A reply three weeks after the question is not an
answer to it; the circumstances it described have moved on. After
`QUESTION_LIFETIME` the question is closed unanswered and a person is told,
because a family who never replied is a family nobody has heard from — which
is a different and more worrying thing than a family who said no.

Nothing here decides anything. It records that a question was asked, matches a
reply to it, and reports what was filled. The planner is called by the runner,
after a person has agreed with the reading — see `domain/requests.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import Field

from ..domain.enums import Language
from ..domain.models import Base
from ..domain.requests import RequestConstraint, TravelFacts
from ..language.questions import TOPIC_FILLS, AskReason, AskTopic, fills_for

#: How long a question is worth an answer. Long enough for a family to reach
#: whoever reads their messages, short enough that a reply is still about the
#: thing that was asked. A judge trying the demo will answer in seconds; a real
#: family may take a day.
QUESTION_LIFETIME = timedelta(hours=36)


class OpenQuestion(Base):
    """A question Saathi asked and has not had an answer to."""

    id: str
    patient_id: str
    reason: AskReason
    topics: tuple[AskTopic, ...]
    #: Exactly what was sent, in the family's own language. Kept so a navigator
    #: reading the reply can see the question it answers, and so the Console
    #: can show both halves of the exchange rather than a reply alone.
    asked_text: str
    language: Language
    #: The day the disruption is about — the only date the question may name.
    about_day: str
    #: What prompted the question, when it was a recorded disruption. A
    #: question Saathi asked on its own initiative has none, and saying so is
    #: better than pointing at a record that does not explain it.
    disruption_id: str | None = None
    asked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    #: Set when a reply filled at least one field this question asked about.
    answered_at: datetime | None = None
    answer_text: str = ""
    #: Fields this reply actually supplied, of those it asked for.
    filled: tuple[str, ...] = ()
    #: Set when the question timed out without an answer.
    closed_unanswered_at: datetime | None = None

    @property
    def wants(self) -> tuple[str, ...]:
        """Every field this question is trying to fill."""
        return fills_for(self.topics)

    @property
    def still_missing(self) -> tuple[str, ...]:
        """Fields asked about that no reply has supplied.

        Field-level detail, for a navigator reading the exchange. It is the
        wrong thing to drive "ask again" off — see `topics_unanswered`.
        """
        return tuple(field for field in self.wants if field not in self.filled)

    @property
    def topics_unanswered(self) -> tuple[AskTopic, ...]:
        """Topics no part of which has been answered.

        A topic is satisfied by **any** of its fields, which is the difference
        that matters when deciding whether to ask again. "Nothing before the
        1st" answers the timing question completely; it fills `not_before` and
        leaves `not_after` and `excluded_dates` empty, and a system reading
        those two empty fields as unanswered would ask a family who had just
        told it everything to tell it again.
        """
        answered = set(self.filled)
        return tuple(
            topic
            for topic in self.topics
            if not answered.intersection(TOPIC_FILLS[topic])
        )

    @property
    def is_open(self) -> bool:
        return self.answered_at is None and self.closed_unanswered_at is None

    def is_stale(self, now: datetime | None = None) -> bool:
        """Whether this has waited longer than a reply is worth."""
        moment = now or datetime.now(UTC)
        return self.is_open and moment - self.asked_at > QUESTION_LIFETIME

    def summary(self) -> str:
        """One line for a navigator's queue."""
        topics = ", ".join(topic.value for topic in self.topics)
        if self.answered_at is not None:
            got = ", ".join(self.filled) or "nothing usable"
            return f"asked about {topics} — answered with {got}"
        if self.closed_unanswered_at is not None:
            return f"asked about {topics} — no reply"
        return f"asked about {topics} — waiting"


class AnswerReading(Base):
    """What a reply to an open question turned out to contain.

    Separate from `PatientRequest` on purpose. A request is a *proposal to
    change a plan* and needs a navigator to confirm it before the planner sees
    it. This is narrower: the facts a family supplied in answer to something
    they were asked. The constraint and the travel facts are carried through to
    the request that gets raised, and the same confirmation rule applies there.
    """

    question_id: str
    constraint: RequestConstraint = Field(default_factory=RequestConstraint)
    travel: TravelFacts = Field(default_factory=TravelFacts)
    #: Fields the reply supplied, **of those the question asked for**. This is
    #: what decides whether a question has been answered.
    filled: tuple[str, ...] = ()
    #: Facts the family gave that nobody asked for. Recorded, and deliberately
    #: not counted as answering anything — see `read_answer`.
    volunteered: tuple[str, ...] = ()
    #: True when the reply contained nothing the question was asking about, in
    #: which case it is not an answer and the question stays open.
    answers_nothing: bool = True


def read_answer(question: OpenQuestion, reading: dict, text: str) -> AnswerReading:
    """Turn an extractor's reading into the answer to one question.

    `reading` is what `live/actors.py:extract_request` returned.

    **Everything the family said is recorded; only what was asked counts as an
    answer.** Those are two different questions and conflating them was a real
    bug, found by running the thing: asked about dates, a family replied "two
    of us are coming, the bus ticket is 1400 and it cannot be changed", and
    the refundability — the single fact that decides whether the visit moves
    at all — was thrown away because nobody had asked about it. A system that
    discards what a family volunteers is not being careful, it is being deaf.

    So `filled` stays restricted to the fields the question asked for, because
    that is what decides whether the question has been answered and whether to
    ask again. Anything else the family said is recorded too and listed in
    `volunteered`, so a navigator can see it was offered rather than elicited.

    The protection this used to provide is not lost. It lives where it should:
    nothing here reaches the planner until a person has read the family's own
    words and agreed with the reading, and every figure carries the sentence it
    came from (`TravelFacts.stated_in`) or is refused by the Console.
    """
    wanted = set(question.wants)
    filled: list[str] = []
    volunteered: list[str] = []

    def taken(field: str) -> object | None:
        value = reading.get(field)
        if value is None or value == () or value == "":
            return None
        (filled if field in wanted else volunteered).append(field)
        return value

    not_before = taken("not_before")
    not_after = taken("not_after")
    excluded = taken("excluded_dates")
    constraint = RequestConstraint(
        not_before=not_before,  # type: ignore[arg-type]
        not_after=not_after,  # type: ignore[arg-type]
        excluded_dates=tuple(excluded or ()),  # type: ignore[arg-type]
        # The family's reason belongs to the navigator, never to a decision.
        # Already screened for clinical content by the extractor.
        reason=str(reading.get("reason") or ""),
    )

    companions = taken("companions")
    single_day = taken("single_day_trip")
    cost = taken("stated_cost_inr")
    refundable = taken("refundable")
    travel = TravelFacts(
        companions=companions,  # type: ignore[arg-type]
        single_day_trip=single_day,  # type: ignore[arg-type]
        stated_cost_inr=cost,  # type: ignore[arg-type]
        refundable=refundable,  # type: ignore[arg-type]
    )
    if travel.anything_said:
        # Attribution is not optional; a figure without its sentence is refused
        # downstream, so it is attached here where the sentence is in hand.
        travel = travel.model_copy(update={"stated_in": text[:400]})

    return AnswerReading(
        question_id=question.id,
        constraint=constraint,
        travel=travel,
        filled=tuple(filled),
        volunteered=tuple(volunteered),
        # Only what was *asked* closes a question. A reply that volunteers
        # something and answers nothing leaves the question open, which is
        # right: the family still has not told us the thing we need.
        answers_nothing=not filled,
    )


class Conversation:
    """The open questions, one per patient.

    In-memory, like the rest of the runner's working state, and cleared on
    reset. What must outlive a restart is the `PatientRequest` a confirmed
    answer produces, not the asking — a question nobody answered is not worth
    restoring, and re-asking it after a restart is the honest behaviour anyway.
    """

    def __init__(self) -> None:
        self._open: dict[str, OpenQuestion] = {}
        #: Every question ever asked, newest last, for the Console and the log.
        self.history: list[OpenQuestion] = []

    # ---------------- asking ----------------

    def open_question(
        self,
        *,
        patient_id: str,
        reason: AskReason,
        topics: tuple[AskTopic, ...],
        asked_text: str,
        language: Language,
        about_day: str,
        disruption_id: str | None = None,
        now: datetime | None = None,
    ) -> OpenQuestion:
        """Record that a question was asked, replacing any still waiting.

        Replacing rather than queueing: if the situation changed enough to ask
        again, the earlier question was about a world that no longer exists,
        and leaving it open would let a stale reply fill in facts about it. The
        superseded question is kept in `history` marked unanswered, so the
        record still shows it was asked.
        """
        moment = now or datetime.now(UTC)
        previous = self._open.pop(patient_id, None)
        if previous is not None:
            self._close(previous, moment)

        question = OpenQuestion(
            id=f"q-{patient_id}-{len(self.history)}",
            patient_id=patient_id,
            reason=reason,
            topics=topics,
            asked_text=asked_text,
            language=language,
            about_day=about_day,
            disruption_id=disruption_id,
            asked_at=moment,
        )
        self._open[patient_id] = question
        self.history.append(question)
        return question

    # ---------------- answering ----------------

    def pending(self, patient_id: str, now: datetime | None = None) -> OpenQuestion | None:
        """The question waiting for this patient, if one still is.

        Expiry is applied here rather than on a timer, so there is no
        background task whose failure would silently leave stale questions
        answerable. A caller that never asks gets no expiry, and a caller that
        asks gets the truth.
        """
        question = self._open.get(patient_id)
        if question is None:
            return None
        if question.is_stale(now):
            self._expire(patient_id, now)
            return None
        return question

    def expired(self, patient_id: str, now: datetime | None = None) -> OpenQuestion | None:
        """Close and return a question that has waited too long, if any.

        The runner calls this on its tick so a family who never replied becomes
        something a person can see, rather than a question that quietly stops
        mattering.
        """
        question = self._open.get(patient_id)
        if question is None or not question.is_stale(now):
            return None
        return self._expire(patient_id, now)

    def record_answer(
        self,
        patient_id: str,
        reading: dict,
        text: str,
        now: datetime | None = None,
    ) -> tuple[OpenQuestion, AnswerReading] | None:
        """Match a reply to the open question and say what it filled.

        Returns `None` when there was nothing to answer — no open question, or
        one that has gone stale. The caller then treats the message as the
        ordinary inbound it is.

        When the reply fills nothing the question asked about, the question is
        **left open** and the returned reading says `answers_nothing`. The
        caller should handle the message normally and may ask again. Closing it
        here would record a family as having answered when they had not.
        """
        question = self.pending(patient_id, now)
        if question is None:
            return None

        answer = read_answer(question, reading, text)
        if answer.answers_nothing:
            return question, answer

        moment = now or datetime.now(UTC)
        answered = question.model_copy(
            update={
                "answered_at": moment,
                "answer_text": text[:400],
                "filled": answer.filled,
            }
        )
        self._replace(answered)
        self._open.pop(patient_id, None)
        return answered, answer

    # ---------------- state ----------------

    def waiting(self, now: datetime | None = None) -> tuple[OpenQuestion, ...]:
        """Every question still waiting on a family, for the Console."""
        return tuple(
            question
            for patient_id in tuple(self._open)
            if (question := self.pending(patient_id, now)) is not None
        )

    def reset(self) -> None:
        self._open.clear()
        self.history.clear()

    # ---------------- internals ----------------

    def _expire(self, patient_id: str, now: datetime | None) -> OpenQuestion | None:
        question = self._open.pop(patient_id, None)
        if question is None:
            return None
        return self._close(question, now or datetime.now(UTC))

    def _close(self, question: OpenQuestion, moment: datetime) -> OpenQuestion:
        closed = question.model_copy(update={"closed_unanswered_at": moment})
        self._replace(closed)
        return closed

    def _replace(self, question: OpenQuestion) -> None:
        for index, existing in enumerate(self.history):
            if existing.id == question.id:
                self.history[index] = question
                return
        self.history.append(question)


__all__ = [
    "QUESTION_LIFETIME",
    "AnswerReading",
    "Conversation",
    "OpenQuestion",
    "read_answer",
]
