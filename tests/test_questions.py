"""The questions Saathi asks, and the two ways a question can go wrong.

A question is the one kind of text this system sends that has no plan behind
it — it is asked precisely because nothing is decided yet. So the usual
protection does not apply, and these tests pin the protection that replaces
it:

* a question never states a date it was not handed, and
* every date it *does* write is one `guard.stated_dates` can read back, in all
  five languages.

The second is easy to get wrong in a way nothing would notice: a Tamil month
name spelled differently here than in `guard.MONTH_NAMES` produces a question
that reads perfectly to a family and is unverifiable by the guard. The guard
fails closed, so the result is not a wrong date — it is Tamil families never
being told anything. That is worth sixty assertions.
"""

from __future__ import annotations

from datetime import date

import pytest
from saathi.domain.enums import Language
from saathi.language.guard import check_question, stated_dates
from saathi.language.questions import (
    TOPIC_FILLS,
    AskReason,
    AskTopic,
    compose_question,
    fills_for,
    written_day,
)

ALL_TOPICS = tuple(AskTopic)


class TestEveryLanguageIsCovered:
    """A missing translation must not silently fall back for a pilot language."""

    @pytest.mark.parametrize("language", list(Language))
    @pytest.mark.parametrize("reason", list(AskReason))
    def test_every_reason_has_every_language(
        self, reason: AskReason, language: Language
    ) -> None:
        text = compose_question(
            reason=reason, topics=(AskTopic.TIMING,), language=language, on_day=date(2026, 11, 27)
        )
        assert text.strip()

    @pytest.mark.parametrize("language", list(Language))
    @pytest.mark.parametrize("topic", ALL_TOPICS)
    def test_every_topic_has_every_language(self, topic: AskTopic, language: Language) -> None:
        text = compose_question(
            reason=AskReason.DOCTOR_AWAY, topics=(topic,), language=language,
            on_day=date(2026, 11, 27),
        )
        assert text.strip()

    def test_every_topic_fills_something(self) -> None:
        # A topic that fills no field is a question that can never be answered.
        for topic in AskTopic:
            assert TOPIC_FILLS[topic], topic


class TestDatesTheGuardCanRead:
    """The contract between this module and `guard.MONTH_NAMES`."""

    @pytest.mark.parametrize("language", list(Language))
    @pytest.mark.parametrize("month", range(1, 13))
    def test_every_month_round_trips(self, month: int, language: Language) -> None:
        day = date(2026, month, 3)
        written = written_day(day, language)
        assert (3, month) in stated_dates(written), (
            f"the guard cannot read {written!r} — a question in {language.value} "
            "would be unverifiable, and the guard fails closed"
        )

    @pytest.mark.parametrize("language", list(Language))
    def test_a_composed_question_passes_its_own_guard(self, language: Language) -> None:
        day = date(2026, 12, 3)
        text = compose_question(
            reason=AskReason.DOCTOR_AWAY, topics=ALL_TOPICS, language=language, on_day=day
        )
        assert check_question(text, dates_given=(day,)).allowed

    def test_a_question_with_an_extra_date_is_refused(self) -> None:
        day = date(2026, 11, 27)
        text = compose_question(
            reason=AskReason.DOCTOR_AWAY, topics=(AskTopic.TIMING,),
            language=Language.ENGLISH, on_day=day,
        )
        verdict = check_question(text + " Please come on 2 December.", dates_given=(day,))
        assert not verdict.allowed
        assert "a date it was not given" in verdict.reason


class TestWhatAQuestionNeverContains:
    def test_no_question_offers_a_figure(self) -> None:
        """Saathi asks what a journey costs; it never suggests an amount.

        There is no fare source behind this system, so a number in a question
        would be an invention — and one the family would reasonably read as
        the hospital's estimate. See `domain/requests.py:TravelFacts`.
        """
        for language in Language:
            for reason in AskReason:
                text = compose_question(
                    reason=reason, topics=ALL_TOPICS, language=language,
                    on_day=date(2026, 11, 27),
                )
                assert "₹" not in text
                # No bare number other than the day of the month it was given.
                digits = {chunk for chunk in text.split() if chunk.isdigit()}
                assert digits <= {"27"}, (language, reason, digits)

    def test_a_question_with_no_topic_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no topic"):
            compose_question(
                reason=AskReason.DOCTOR_AWAY, topics=(), language=Language.ENGLISH,
                on_day=date(2026, 11, 27),
            )


class TestFills:
    def test_topics_are_rendered_in_a_stable_order(self) -> None:
        """A family asked twice should read the same sentence order both times."""
        day = date(2026, 11, 27)
        one = compose_question(
            reason=AskReason.DOCTOR_AWAY,
            topics=(AskTopic.COST, AskTopic.TIMING, AskTopic.COMPANIONS),
            language=Language.ENGLISH, on_day=day,
        )
        other = compose_question(
            reason=AskReason.DOCTOR_AWAY,
            topics=(AskTopic.COMPANIONS, AskTopic.COST, AskTopic.TIMING),
            language=Language.ENGLISH, on_day=day,
        )
        assert one == other

    def test_fills_are_deduplicated(self) -> None:
        assert len(set(fills_for(ALL_TOPICS))) == len(fills_for(ALL_TOPICS))

    def test_fills_covers_every_topic_asked(self) -> None:
        got = set(fills_for((AskTopic.TIMING, AskTopic.COST)))
        assert got == set(TOPIC_FILLS[AskTopic.TIMING]) | set(TOPIC_FILLS[AskTopic.COST])
