"""A family asking to move a visit, and the system doing better than asked.

The two hospital stories start with a machine breaking. This one starts with a
wedding, which is the far commoner reason a plan actually changes. What it has
to get right is subtler than a disruption:

* the reading of the message is a *proposal*, not an instruction;
* a date the family ruled out is never offered back to them;
* a date outside the tolerance a clinician set never reaches the doctor;
* and the option the family did not think of — moving the visit *earlier* — is
  offered, because doing what was asked is not the same as helping.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from saathi.domain.enums import StepKind
from saathi.domain.policy import default_policy
from saathi.domain.requests import (
    PatientRequest,
    RequestConstraint,
    RequestIntent,
)
from saathi.graph.dependencies import InMemoryDependencyGraph
from saathi.planner.options import candidates_for_request
from saathi.planner.search import Search, Verdict
from saathi.readiness.conformal import ConformalReadinessPredictor
from saathi.synthetic.generate import generate_cohort
from saathi.synthetic.scripted import seed_anita_devi

TODAY = date(2026, 12, 1)
#: Seeded so Anita's next dose lands on Friday 11 December.
SEED_DAY = date(2026, 12, 9)


@pytest.fixture
def anita():
    patient, steps, _truth, cycle = seed_anita_devi(SEED_DAY)
    dose = next(s for s in steps if s.kind is StepKind.MAINTENANCE_DOSE)
    predictor = ConformalReadinessPredictor()
    predictor.fit(generate_cohort(today=TODAY).turnaround)
    return patient, steps, cycle, dose, predictor


def _request(dose, **constraint) -> PatientRequest:
    return PatientRequest(
        id="r1",
        patient_id="P-ANITA",
        raw_text="11 tareekh ko nahi aa sakte, ghar mein shaadi hai, 20 ke baad aayenge",
        intent=RequestIntent.MOVE_VISIT,
        step_kind=StepKind.MAINTENANCE_DOSE,
        constraint=RequestConstraint(excluded_dates=(dose.scheduled_for,), **constraint),
        confirmed_by="Kavita Kumari",
    )


def _options(anita, request, policy=None):
    patient, steps, cycle, _dose, predictor = anita
    return candidates_for_request(
        patient, steps, request, StepKind.MAINTENANCE_DOSE,
        InMemoryDependencyGraph(), predictor, TODAY,
        policy or default_policy("HBCH-MZP"),
        cycle=cycle, round_trip_hours=2.4,
    )


# ---------------------------------------------------------------- the reading


def test_a_request_is_not_actionable_until_a_person_confirms_it():
    """Mishearing 'after the 20th' as 'on the 20th' is a wasted journey."""
    unconfirmed = PatientRequest(
        id="r", patient_id="P", raw_text="...", intent=RequestIntent.MOVE_VISIT
    )
    assert unconfirmed.actionable is False
    assert unconfirmed.confirmed_by is None

    confirmed = unconfirmed.model_copy(update={"confirmed_by": "Kavita"})
    assert confirmed.actionable is True


def test_a_rejected_reading_stays_unactionable():
    request = PatientRequest(
        id="r", patient_id="P", raw_text="...", intent=RequestIntent.MOVE_VISIT,
        confirmed_by="Kavita", rejected_reason="she meant the echo, not the dose",
    )
    assert request.actionable is False


def test_money_and_unclear_messages_go_to_a_person_not_the_planner():
    for intent in (RequestIntent.NEEDS_HELP, RequestIntent.UNCLEAR):
        request = PatientRequest(
            id="r", patient_id="P", raw_text="...", intent=intent, confirmed_by="Kavita"
        )
        assert request.needs_a_person is True
        assert request.actionable is False


# ---------------------------------------------------------------- the options


def test_a_date_the_family_ruled_out_is_never_offered_back(anita):
    _p, _s, _c, dose, _pred = anita
    options = _options(anita, _request(dose, not_before=date(2026, 12, 20)))
    assert options
    assert all(o.target_on != dose.scheduled_for for o in options)


def test_what_the_family_proposed_is_dropped_when_it_breaks_the_schedule(anita):
    """They asked for after the 20th. That is +10 days on a +/-7 tolerance."""
    _p, _s, _c, dose, _pred = anita
    options = _options(anita, _request(dose, not_before=date(2026, 12, 20)))

    assert all(o.target_on < date(2026, 12, 20) for o in options), (
        "an option outside the clinician's tolerance reached the doctor's list"
    )


def test_earlier_is_offered_even_though_nobody_asked_for_it(anita):
    """The point of the story: moving forward clears the wedding and keeps the schedule."""
    _p, _s, _c, dose, _pred = anita
    options = _options(anita, _request(dose, not_before=date(2026, 12, 20)))

    earlier = [o for o in options if o.target_on < dose.scheduled_for]
    assert earlier, "the planner only echoed the family's own idea back at them"
    assert earlier[0].target_on == dose.scheduled_for - timedelta(days=7)


def test_every_option_stays_inside_the_hospitals_tolerance(anita):
    _p, _s, _c, dose, _pred = anita
    policy = default_policy("HBCH-MZP")
    tolerance = policy.shift_tolerance(StepKind.MAINTENANCE_DOSE)
    options = _options(anita, _request(dose, not_before=date(2026, 12, 20)), policy)

    for option in options:
        assert abs((option.target_on - dose.scheduled_for).days) <= tolerance


def test_an_unstated_tolerance_filters_nothing(anita):
    """With no number from the hospital there is no basis to remove an option."""
    _p, _s, _c, dose, _pred = anita
    base = default_policy("HBCH-MZP")
    dose_policy = base.steps[StepKind.MAINTENANCE_DOSE.value]
    silent = base.model_copy(
        update={
            "steps": {
                **base.steps,
                StepKind.MAINTENANCE_DOSE.value: dose_policy.model_copy(
                    update={"shift_tolerance_days": None}
                ),
            }
        }
    )
    options = _options(anita, _request(dose, not_before=date(2026, 12, 20)), silent)
    assert any(o.target_on >= date(2026, 12, 20) for o in options), (
        "an unstated tolerance should not silently become a strict one"
    )


def test_no_option_lands_in_the_past_or_today(anita):
    """A family cannot travel overnight on a message sent this afternoon."""
    _p, _s, _c, dose, _pred = anita
    options = _options(anita, _request(dose, not_before=date(2026, 12, 20)))
    assert all(o.target_on > TODAY for o in options)


def test_every_option_carries_the_date_the_step_actually_moves_to(anita):
    """`travel_on` answers a different question and checking it compares the wrong dates."""
    _p, _s, _c, dose, _pred = anita
    options = _options(anita, _request(dose, not_before=date(2026, 12, 20)))
    assert options
    assert all(o.target_on is not None for o in options)


# --------------------------------------------------- what the search records
#
# The three rejections below used to happen before `filter_options` ever saw
# the candidate, so a search that tried four dates reported one. That made the
# Console's "what the planner considered" read as a far narrower search than
# actually ran — which is worse than showing nothing, because it understates
# the work in a screen whose whole purpose is to show it.


def _search_for(anita, request, policy=None):
    from saathi.planner.search import Search

    patient, steps, cycle, _dose, predictor = anita
    search = Search(patient_id=patient.id, step_kind=StepKind.MAINTENANCE_DOSE.value)
    candidates_for_request(
        patient, steps, request, StepKind.MAINTENANCE_DOSE,
        InMemoryDependencyGraph(), predictor, TODAY,
        policy or default_policy("HBCH-MZP"),
        cycle=cycle, round_trip_hours=2.4, search=search,
    )
    return search


class TestTheSearchRecordsWhatItDropped:
    def test_a_day_the_family_ruled_out_is_recorded_not_skipped(self, anita) -> None:
        """"They cannot come then" is a finding, not an absence."""
        from saathi.planner.search import Verdict

        _patient, _steps, _cycle, dose, _predictor = anita
        # Asking for the very day they excluded: the only way the excluded
        # branch is reached is if `not_before` lands back on it.
        request = _request(dose, not_before=dose.scheduled_for)
        search = _search_for(anita, request)

        ruled_out = [c for c in search.considered if c.verdict is Verdict.FAMILY_CANNOT]
        assert ruled_out, "the day they ruled out was not recorded at all"
        assert ruled_out[0].on == dose.scheduled_for
        assert "themselves" in ruled_out[0].detail

    def test_a_date_outside_tolerance_is_recorded_with_the_rule(self, anita) -> None:
        from saathi.planner.search import Verdict

        _patient, _steps, _cycle, dose, _predictor = anita
        # Far outside any tolerance a clinician would set.
        request = _request(dose, not_before=dose.scheduled_for + timedelta(days=120))
        search = _search_for(anita, request)

        refused = [c for c in search.considered if c.verdict is Verdict.OUTSIDE_TOLERANCE]
        assert refused, "a date outside the window was dropped without a record"
        assert any(c.detail for c in refused), (
            "the rule's own objection should be recorded, not just the verdict"
        )

    def test_recording_still_changes_nothing(self, anita) -> None:
        """The decisive one: a recorder that altered the result would be worse
        than no recorder, because the log would then be part of the decision."""
        from saathi.planner.search import Search

        patient, steps, cycle, dose, predictor = anita
        request = _request(dose, not_before=dose.scheduled_for + timedelta(days=9))

        def run(search):
            return candidates_for_request(
                patient, steps, request, StepKind.MAINTENANCE_DOSE,
                InMemoryDependencyGraph(), predictor, TODAY,
                default_policy("HBCH-MZP"),
                cycle=cycle, round_trip_hours=2.4, search=search,
            )

        without = run(None)
        recorded = run(Search(patient_id=patient.id))
        assert [o.target_on for o in recorded] == [o.target_on for o in without]
        assert without, "the fixture should produce at least one option to compare"

    def test_every_offered_date_is_in_the_record(self, anita) -> None:
        _patient, _steps, _cycle, dose, _predictor = anita
        request = _request(dose, not_before=dose.scheduled_for + timedelta(days=9))

        offered = _options(anita, request)
        search = _search_for(anita, request)

        assert {c.on for c in search.offered} == {o.target_on for o in offered}, (
            "the search and the options must describe the same offer"
        )


def test_a_day_the_clinician_is_away_is_never_offered_back(anita):
    """The re-plan exists because nobody is there to see them.

    A leave the hospital published never becomes a `Disruption` — the
    connector reads it, asks the family and stops — so the planner's resource
    calendar cannot refuse those days on its own. Before `days_away` existed,
    a family who said "not before the 1st" was offered the 1st, which was the
    very day their clinician was away.
    """
    patient, steps, cycle, dose, predictor = anita
    request = _request(dose, not_before=dose.scheduled_for + timedelta(days=1))
    policy = default_policy("HBCH-MZP")

    def run(days_away):
        search = Search(patient_id=patient.id, step_kind=StepKind.MAINTENANCE_DOSE.value)
        found = candidates_for_request(
            patient, steps, request, StepKind.MAINTENANCE_DOSE,
            InMemoryDependencyGraph(), predictor, TODAY, policy,
            cycle=cycle, round_trip_hours=2.4,
            days_away=days_away, search=search,
        )
        return found, search

    offered, _ = run(frozenset())
    assert offered, "nothing was offered even with no leave; the fixture is wrong"
    shut = {o.target_on for o in offered}

    # Close every day it just offered, and it must offer none of them back.
    blocked, search = run(frozenset(shut))
    assert not ({o.target_on for o in blocked} & shut), (
        "the planner offered a day the clinician is away"
    )

    # And it says so, rather than dropping the day silently.
    refused = [c for c in search.considered if c.on in shut and not c.verdict.offered]
    assert refused, "the day was dropped without being recorded"
    assert all(c.verdict is Verdict.RESOURCE_DOWN for c in refused)
