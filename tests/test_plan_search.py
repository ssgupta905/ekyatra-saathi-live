"""What the planner considered, not only what it chose.

The planner used to produce an answer and discard its reasoning. That is
right for a family — `filter_options` drops impossible dates silently, so
nobody is offered something that is then refused — and wrong for everyone
else, because it left no way to answer the one question a clinical or
technical reviewer always asks: what else did you look at?

These pin the two halves of that. The filtering must not change, and the
discarding must be recorded with the rule that caused it.
"""

from __future__ import annotations

from datetime import date

from saathi.domain.enums import Decision
from saathi.domain.models import MaintenanceCycle, PlanOption
from saathi.planner.care_rules import filter_options
from saathi.planner.search import Considered, Search, Verdict


def _option(step_on: date, *, bundled=(), nights=0, trips=0) -> PlanOption:
    """`extra_trips` is the model's name for it; the search calls it
    `trips_added` because that is what reads to a person."""
    return PlanOption(
        patient_id="P1",
        target_step_id="P1-maintenance_dose",
        decision=Decision.GO,
        travel_on=step_on,
        target_on=step_on,
        bundled_step_ids=tuple(bundled),
        nights_added=nights,
        extra_trips=trips,
    )


class TestTheFilteringIsUnchanged:
    """The whole point is that recording changed no decision."""

    def test_no_cycle_keeps_everything(self) -> None:
        options = (_option(date(2026, 12, 1)), _option(date(2026, 12, 3)))
        assert filter_options(options, None) == options

    def test_a_rejected_option_really_is_dropped(self) -> None:
        """The recorder must not quietly become a pass-through.

        Without this, `filter_options` could stop filtering entirely and
        every test above would still pass — the search would faithfully log
        a rejection for an option that was nonetheless returned and offered
        to a family.
        """
        cycle = MaintenanceCycle(patient_id="P1", dose_index=5, anchor_date=date(2026, 9, 1))
        bad = _option(date(2026, 12, 1))
        good = _option(date(2026, 12, 3), bundled=("P1-echo_review",))
        search = Search(patient_id="P1")

        kept = filter_options((bad, good), cycle, search)

        assert kept == (good,), "the option the rule rejected was still returned"
        assert len(search.rejected) == 1

    def test_recording_does_not_change_what_survives(self) -> None:
        # Dose 5, not 4: "an echo before every fourth dose" means after four
        # have been given, so the gate is on the fifth. Getting this wrong
        # makes the test pass with nothing rejected.
        cycle = MaintenanceCycle(patient_id="P1", dose_index=5, anchor_date=date(2026, 9, 1))
        options = (
            _option(date(2026, 12, 1)),
            _option(date(2026, 12, 3), bundled=("P1-echo_review",)),
        )
        without = filter_options(options, cycle)
        with_log = filter_options(options, cycle, Search(patient_id="P1"))
        assert without == with_log


class TestTheSearchIsRecorded:
    def test_a_rejected_date_is_kept_with_its_reason(self) -> None:
        """The dose that needs an echo, offered without one."""
        cycle = MaintenanceCycle(patient_id="P1", dose_index=5, anchor_date=date(2026, 9, 1))
        search = Search(patient_id="P1", step_kind="maintenance_dose")

        filter_options(
            (
                _option(date(2026, 12, 1)),
                _option(date(2026, 12, 3), bundled=("P1-echo_review",)),
            ),
            cycle,
            search,
        )

        assert len(search.considered) == 2
        assert len(search.offered) == 1
        (rejected,) = search.rejected
        assert rejected.verdict is Verdict.CARE_RULE
        assert rejected.on == date(2026, 12, 1)
        assert "echo" in rejected.detail

    def test_the_summary_says_how_wide_the_search_was(self) -> None:
        """"We offered one" and "we looked at five and one survived" are
        very different statements about the same result."""
        cycle = MaintenanceCycle(patient_id="P1", dose_index=5, anchor_date=date(2026, 9, 1))
        search = Search(patient_id="P1", step_kind="maintenance_dose")
        filter_options(
            (_option(date(2026, 12, 1)), _option(date(2026, 12, 3), bundled=("P1-echo_review",))),
            cycle,
            search,
        )

        assert "2 date(s)" in search.summary()
        assert "1 ruled out" in search.summary()

    def test_the_date_logged_is_the_step_date_not_the_travel_date(self) -> None:
        """They are different questions and usually different days.

        `travel_on` is "when may they set out" and for an unblocked plan is
        simply tomorrow — so a log built on it shows every candidate as the
        same day and compares nothing.
        """
        option = PlanOption(
            patient_id="P1",
            target_step_id="P1-scan",
            decision=Decision.GO,
            travel_on=date(2026, 12, 1),   # set out
            target_on=date(2026, 12, 9),   # the step itself, eight days later
        )
        search = Search(patient_id="P1")

        filter_options((option,), None, search)

        (logged,) = search.considered
        assert logged.on == date(2026, 12, 9), "the log showed the travel date"
        assert "09 Dec" in logged.render()

    def test_the_cost_to_the_family_is_carried(self) -> None:
        search = Search(patient_id="P1")
        filter_options((_option(date(2026, 12, 3), nights=-5, trips=-1),), None, search)

        (kept,) = search.considered
        assert kept.nights_added == -5
        assert "-5 nights" in kept.render()

    def test_a_date_that_was_tried_is_nameable_even_when_rejected(self) -> None:
        """A rejected candidate with no id is one nobody can discuss."""
        cycle = MaintenanceCycle(patient_id="P1", dose_index=5, anchor_date=date(2026, 9, 1))
        search = Search(patient_id="P1")
        filter_options((_option(date(2026, 12, 1)),), cycle, search)

        (rejected,) = search.rejected
        assert rejected.ref
        assert "01 Dec" in rejected.render()
        assert "rejected" in rejected.render()


class TestEveryRejectionCanBeExplained:
    def test_no_verdict_is_missing_its_sentence(self) -> None:
        """A rule that rejects under an unnamed verdict is a rule nobody can
        explain to a clinician."""
        from saathi.planner.search import WHY

        missing = [v.value for v in Verdict if v not in WHY]
        assert missing == []

    def test_an_empty_search_says_so_rather_than_implying_none_existed(self) -> None:
        assert "no dates" in Search(patient_id="P1").summary()

    def test_offered_and_rejected_partition_the_search(self) -> None:
        search = Search(patient_id="P1")
        search.note(Considered(ref="a", on=None, verdict=Verdict.OFFERED))
        search.note(Considered(ref="b", on=None, verdict=Verdict.OUTSIDE_TOLERANCE))
        assert len(search.offered) + len(search.rejected) == len(search.considered)
