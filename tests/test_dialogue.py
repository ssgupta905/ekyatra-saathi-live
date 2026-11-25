"""Asking a family something and knowing what they said back.

Four things here are easy to build wrong, and each one fails quietly rather
than loudly:

* a reply that answers nothing being recorded as an answer — the family is
  then never asked again, and the facts are simply absent;
* a stray remark filling a field the question did not ask about — a mention of
  a date becomes a travel constraint nobody stated;
* a stale reply answering a question about a world that has moved on;
* a figure recorded without the sentence it came from, which is
  indistinguishable from a figure this system invented.

The readings fed in here are the ones Groq actually returned for the three
stories, kept verbatim so these tests exercise real extractor output rather
than a shape I found convenient.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from saathi.domain.enums import Language
from saathi.language.questions import AskReason, AskTopic
from saathi.live.dialogue import QUESTION_LIFETIME, Conversation, read_answer

DAY = "2026-11-27"

#: What `extract_request` returned for "Amar sathe ami jabo. Trainer tickets
#: 900 taka hobe. 1 tarikher age noy, salary tokhon ase."
RINA = {
    "intent": "move_visit", "step_kind": None,
    "not_before": "2026-12-01", "not_after": None, "excluded_dates": (),
    "reason": "salary arrives on the 1st", "confidence": "high",
    "companions": 1, "single_day_trip": None, "stated_cost_inr": 900, "refundable": None,
}

#: "Hum do log aa rahe hain. Bus ka ticket 1400 ka le liya hai, wo wapas nahi hoga."
IMRAN = {
    "intent": "unclear", "step_kind": None,
    "not_before": None, "not_after": None, "excluded_dates": (),
    "reason": "non-refundable night bus already bought", "confidence": "high",
    "companions": 2, "single_day_trip": False, "stated_cost_inr": 1400, "refundable": False,
}

#: An unrelated process question — "Kya ho raha hai?"
STRAY = {
    "intent": "ask_status", "step_kind": None,
    "not_before": "2026-12-05", "not_after": None, "excluded_dates": (),
    "reason": "wants to know what is happening", "confidence": "high",
    "companions": None, "single_day_trip": None, "stated_cost_inr": None, "refundable": None,
}


def ask(conv: Conversation, *topics: AskTopic, patient: str = "p1", now=None):
    return conv.open_question(
        patient_id=patient, reason=AskReason.DOCTOR_AWAY, topics=topics,
        asked_text="(the composed question)", language=Language.BENGALI,
        about_day=DAY, disruption_id="d1", now=now,
    )


class TestAnAnswerThatAnswers:
    def test_a_reply_fills_only_what_was_asked(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.COMPANIONS, AskTopic.COST, AskTopic.TIMING)
        answered, answer = conv.record_answer("p1", RINA, "…900 taka… 1 tarikher age noy")

        assert not answer.answers_nothing
        assert answer.constraint.not_before is not None
        assert answer.travel.companions == 1
        assert answer.travel.stated_cost_inr == 900
        assert set(answer.filled) == {"not_before", "companions", "stated_cost_inr"}
        assert answered.answered_at is not None

    def test_a_topic_is_satisfied_by_any_of_its_fields(self) -> None:
        """"Nothing before the 1st" answers the timing question completely.

        It fills `not_before` and leaves `not_after` and `excluded_dates`
        empty. A system reading those two as unanswered would ask a family who
        had just told it everything to tell it again.
        """
        conv = Conversation()
        ask(conv, AskTopic.COMPANIONS, AskTopic.COST, AskTopic.TIMING)
        answered, _ = conv.record_answer("p1", RINA, "…")

        assert answered.topics_unanswered == ()
        # The field-level view still shows what was not said.
        assert set(answered.still_missing) == {"not_after", "excluded_dates"}

    def test_a_partial_answer_names_the_topic_still_open(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.COMPANIONS, AskTopic.COST)
        only_companions = {**RINA, "stated_cost_inr": None}
        answered, _ = conv.record_answer("p1", only_companions, "do log")

        assert answered.topics_unanswered == (AskTopic.COST,)

    def test_an_answered_question_is_no_longer_open(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.COST)
        conv.record_answer("p1", RINA, "…")
        assert conv.pending("p1") is None
        assert conv.waiting() == ()

    def test_refundability_is_captured_as_a_no(self) -> None:
        """`False` must survive, and must not be read as "not answered".

        This is the field that changes Imran's decision: a refundable ticket
        moves the visit, a non-refundable one keeps it. A `False` collapsed
        into `None` would silently turn the second case into the first.
        """
        conv = Conversation()
        ask(conv, AskTopic.BOOKING)
        _, answer = conv.record_answer("p1", IMRAN, "wo wapas nahi hoga")

        assert answer.travel.refundable is False
        assert "refundable" in answer.filled


class TestAReplyThatAnswersNothing:
    def test_a_stray_reply_leaves_the_question_open(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.COMPANIONS)
        question, answer = conv.record_answer("p1", STRAY, "Kya ho raha hai?")

        assert answer.answers_nothing
        assert conv.pending("p1") is not None, "the family has still not answered"
        assert question.answered_at is None

    def test_a_field_the_question_did_not_ask_about_does_not_answer_it(self) -> None:
        """STRAY carries a date. The question asked about companions.

        The date is recorded — the family said it — but it is `volunteered`,
        not `filled`, so it does not close a question about who is coming and
        does not stop Saathi asking again.
        """
        conv = Conversation()
        ask(conv, AskTopic.COMPANIONS)
        _, answer = conv.record_answer("p1", STRAY, "Kya ho raha hai?")

        assert answer.filled == ()
        assert answer.answers_nothing
        assert "not_before" in answer.volunteered


class TestWhatAFamilyVolunteers:
    """Recorded, and never counted as an answer.

    This distinction was a real bug: asked about dates, a family replied with
    two people, 1400 rupees and a ticket that cannot be changed, and the
    refundability — the one fact that decides whether the visit moves at all
    — was discarded because nobody had asked about it.
    """

    def test_a_volunteered_fact_is_kept(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.TIMING)  # nobody asked about the booking
        _, answer = conv.record_answer("p1", IMRAN, "wo wapas nahi hoga")

        assert answer.travel.refundable is False
        assert "refundable" in answer.volunteered
        assert "refundable" not in answer.filled

    def test_volunteering_alone_does_not_close_the_question(self) -> None:
        """They still have not said which days they can travel."""
        conv = Conversation()
        ask(conv, AskTopic.TIMING)
        question, answer = conv.record_answer("p1", IMRAN, "wo wapas nahi hoga")

        assert answer.answers_nothing
        assert conv.pending("p1") is not None
        assert question.answered_at is None

    def test_a_volunteered_figure_is_still_attributed(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.TIMING)
        said = "Bus ka ticket 1400 ka le liya hai"
        _, answer = conv.record_answer("p1", IMRAN, said)

        assert answer.travel.stated_cost_inr == 1400
        assert answer.travel.stated_in == said


class TestStaleness:
    def test_a_question_past_its_lifetime_is_not_answerable(self) -> None:
        conv = Conversation()
        long_ago = datetime.now(UTC) - QUESTION_LIFETIME - timedelta(hours=1)
        ask(conv, AskTopic.COST, now=long_ago)

        assert conv.pending("p1") is None
        assert conv.record_answer("p1", RINA, "too late") is None

    def test_an_expired_question_is_still_on_the_record(self) -> None:
        """A family nobody has heard from must be visible, not forgotten."""
        conv = Conversation()
        long_ago = datetime.now(UTC) - QUESTION_LIFETIME - timedelta(hours=1)
        ask(conv, AskTopic.COST, now=long_ago)
        conv.pending("p1")

        assert len(conv.history) == 1
        assert conv.history[0].closed_unanswered_at is not None
        assert "no reply" in conv.history[0].summary()

    def test_expired_reports_the_question_once(self) -> None:
        conv = Conversation()
        long_ago = datetime.now(UTC) - QUESTION_LIFETIME - timedelta(hours=1)
        ask(conv, AskTopic.COST, now=long_ago)

        assert conv.expired("p1") is not None
        assert conv.expired("p1") is None, "an expiry must not be reported twice"

    def test_a_question_inside_its_lifetime_is_fine(self) -> None:
        conv = Conversation()
        recent = datetime.now(UTC) - QUESTION_LIFETIME + timedelta(hours=1)
        ask(conv, AskTopic.COST, now=recent)
        assert conv.pending("p1") is not None


class TestSupersedingAQuestion:
    def test_asking_again_replaces_the_question_and_keeps_the_record(self) -> None:
        """If the situation changed enough to re-ask, a stale reply must not
        fill in facts about the world that no longer exists."""
        conv = Conversation()
        first = ask(conv, AskTopic.COST)
        second = ask(conv, AskTopic.TIMING)

        assert conv.pending("p1") is not None
        assert conv.pending("p1").id == second.id
        superseded = next(q for q in conv.history if q.id == first.id)
        assert superseded.closed_unanswered_at is not None

    def test_questions_are_per_patient(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.COST, patient="p1")
        ask(conv, AskTopic.TIMING, patient="p2")

        assert conv.pending("p1") is not None
        assert conv.pending("p2") is not None
        assert len(conv.waiting()) == 2
        conv.record_answer("p1", RINA, "…")
        assert conv.pending("p2") is not None, "answering for one family is not the other"


class TestAttribution:
    def test_a_figure_carries_the_sentence_it_came_from(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.COST)
        said = "Trainer tickets 900 taka hobe"
        _, answer = conv.record_answer("p1", RINA, said)

        assert answer.travel.stated_cost_inr == 900
        assert answer.travel.stated_in == said

    def test_no_sentence_is_attached_when_nothing_was_said(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.COMPANIONS)
        _, answer = conv.record_answer("p1", STRAY, "Kya ho raha hai?")
        assert answer.travel.stated_in == ""
        assert not answer.travel.anything_said

    def test_a_long_utterance_is_truncated_not_dropped(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.COST)
        _, answer = conv.record_answer("p1", RINA, "x" * 900)
        assert len(answer.travel.stated_in) == 400


class TestReadAnswerDirectly:
    def test_reading_is_pure(self) -> None:
        """`read_answer` holds no state, so the same reply reads the same twice."""
        conv = Conversation()
        question = ask(conv, AskTopic.COST, AskTopic.TIMING)
        one = read_answer(question, RINA, "said")
        other = read_answer(question, RINA, "said")
        assert one == other

    def test_empty_values_do_not_count_as_filled(self) -> None:
        conv = Conversation()
        question = ask(conv, AskTopic.TIMING)
        blank = {**RINA, "not_before": None, "not_after": None, "excluded_dates": ()}
        answer = read_answer(question, blank, "said")
        assert answer.answers_nothing
        assert answer.filled == ()


class TestReset:
    def test_reset_clears_everything(self) -> None:
        conv = Conversation()
        ask(conv, AskTopic.COST)
        conv.reset()
        assert conv.pending("p1") is None
        assert conv.history == []
