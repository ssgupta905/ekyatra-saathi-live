"""Kharcha's arithmetic: every figure has an owner, and nothing is a made-up rate."""

from __future__ import annotations

import ast
from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from saathi.domain.spends import (
    Basis,
    CoveredBy,
    NudgeKind,
    SpendCategory,
    SpendEntry,
    SpendSource,
    SpendStatus,
)
from saathi.orchestrator.kharcha import nudges, outlook, read_spend, visits_ahead

TODAY = date(2026, 11, 10)
TRAVEL, STAY, FOOD = SpendCategory.TRAVEL, SpendCategory.STAY, SpendCategory.FOOD
_n = iter(range(10_000))


def said(rupees, category=TRAVEL, *, on, visit_on=None, status=SpendStatus.PAID, **extra):
    return SpendEntry(
        id=f"sp-{next(_n)}", patient_id="P", category=category, amount_paise=rupees * 100,
        status=status, source=SpendSource.FAMILY_STATED, stated_in=f"{rupees}",
        on=on, visit_on=visit_on if visit_on is not None else on, **extra,
    )  # fmt: skip


def quote(rupees, category=TRAVEL, *, on, visit_on=None, ref="q"):
    return SpendEntry(
        id=f"sp-{next(_n)}", patient_id="P", category=category, amount_paise=rupees * 100,
        status=SpendStatus.QUOTED, source=SpendSource.PROVIDER_QUOTE,
        source_ref=f"{ref}-{next(_n)}", on=on, visit_on=visit_on or on,
    )  # fmt: skip


# ---------------------------------------------------------------- every amount has an owner


def test_a_family_figure_without_their_words_is_refused():
    with pytest.raises(ValidationError):
        SpendEntry(id="x", patient_id="P", category=TRAVEL, amount_paise=100,
                   status=SpendStatus.PAID, source=SpendSource.FAMILY_STATED, on=TODAY)  # fmt: skip


def test_a_provider_figure_without_the_provider_s_reference_is_refused():
    with pytest.raises(ValidationError):
        SpendEntry(id="x", patient_id="P", category=TRAVEL, amount_paise=100,
                   status=SpendStatus.QUOTED, source=SpendSource.PROVIDER_QUOTE,
                   on=TODAY)  # fmt: skip


def test_an_estimate_is_a_range_and_never_spent():
    with pytest.raises(ValidationError):
        SpendEntry(id="x", patient_id="P", category=TRAVEL, amount_paise=100,
                   amount_high_paise=200, status=SpendStatus.PAID,
                   source=SpendSource.PROVIDER_ESTIMATE, source_ref="uber-1", on=TODAY)  # fmt: skip


# ---------------------------------------------------------------- reading a family's words


@pytest.mark.parametrize(
    ("text", "paise", "category"),
    [
        ("₹450 auto", 45_000, TRAVEL),
        ("auto 450 rupees", 45_000, TRAVEL),
        ("ऑटो ४५०", 45_000, TRAVEL),
        ("lodge near Parel 2,400", 2_40_000, STAY),
        ("food in Kolkata 200", 20_000, FOOD),
        ("2 autos ₹300", 30_000, TRAVEL),
    ],
)
def test_a_family_s_own_words_are_read(text, paise, category):
    assert read_spend(text) == (paise, category)


def test_two_unmarked_numbers_are_not_guessed_between():
    assert read_spend("2 autos 300")[0] is None


def test_a_number_too_big_for_one_spend_is_not_believed():
    assert read_spend("call me on 9876543210")[0] is None


# ---------------------------------------------------------------- visits ahead


def test_dialysis_every_two_days_from_the_next_booked_session():
    days = visits_ahead(
        scheduled=[TODAY + timedelta(days=1)], last_visit=TODAY - timedelta(days=1),
        interval_days=2, remaining=None, start=TODAY, end=date(2026, 11, 30),
    )  # fmt: skip
    assert days[0] == TODAY + timedelta(days=1)
    assert all((b - a).days == 2 for a, b in zip(days, days[1:], strict=False))
    assert days[-1] <= date(2026, 11, 30)


def test_chemo_every_21_days_stops_when_the_regimen_does():
    days = visits_ahead(
        scheduled=[], last_visit=TODAY, interval_days=21, remaining=1,
        start=TODAY, end=TODAY + timedelta(days=120),
    )  # fmt: skip
    assert days == (TODAY + timedelta(days=21),)


def test_a_one_off_visit_is_only_the_date_the_hospital_booked():
    review = TODAY + timedelta(days=3)
    assert visits_ahead(scheduled=[review], last_visit=None, interval_days=None, remaining=None,
                        start=TODAY, end=TODAY + timedelta(days=60)) == (review,)  # fmt: skip


# ---------------------------------------------------------------- the month


def test_what_is_ahead_repeats_the_family_s_own_last_visits_median_low():
    v1, v2, v3 = (TODAY - timedelta(days=d) for d in (21, 14, 7))
    entries = [said(180, on=v1), said(200, on=v2), said(900, on=v3), said(40, FOOD, on=v3)]
    ahead = [TODAY + timedelta(days=2), TODAY + timedelta(days=9)]

    month = outlook(entries, month=TODAY, today=TODAY, visits=ahead)

    travel = next(line for line in month.lines if line.category is TRAVEL)
    assert travel.basis is Basis.REPEAT_OF_VISITS and travel.visits_used == 3
    assert travel.amount_paise == 2 * 200_00, "median-low of 180/200/900 is a trip that happened"
    assert set(travel.based_on) <= {e.id for e in entries}
    # Tea on one trip in three is not what a trip costs.
    assert FOOD not in {line.category for line in month.lines}


def test_a_provider_quote_for_a_visit_is_used_instead_of_the_repeat():
    past = TODAY - timedelta(days=7)
    visit = TODAY + timedelta(days=2)
    entries = [said(180, on=past), quote(250, on=visit)]

    month = outlook(entries, month=TODAY, today=TODAY, visits=[visit])

    assert month.booked_paise == 250_00
    assert month.expected_paise == 0, "the quoted visit is booked, not expected twice"


def test_nothing_to_go_on_says_so_and_gives_no_figure():
    month = outlook([], month=TODAY, today=TODAY, visits=[TODAY + timedelta(days=3)])

    assert month.expected_paise is None
    assert month.lines[0].basis is Basis.NOTHING_TO_GO_ON


def test_unconfirmed_and_scheme_covered_money_is_not_counted_as_the_family_s():
    entries = [
        said(500, on=TODAY, status=SpendStatus.PROPOSED),
        said(800, SpendCategory.HOSPITAL, on=TODAY, covered_by=CoveredBy.SCHEME),
        said(100, on=TODAY),
    ]

    assert outlook(entries, month=TODAY, today=TODAY, visits=[]).spent_paise == 100_00


def test_next_month_is_its_own_month():
    entries = [said(180, on=TODAY - timedelta(days=2))]
    visits = [date(2026, 12, 4)]

    december = outlook(entries, month=date(2026, 12, 1), today=TODAY, visits=visits)

    assert december.spent_paise == 0 and december.visits_ahead == (date(2026, 12, 4),)
    assert december.expected_paise == 180_00


# ---------------------------------------------------------------- suggestions


def test_nights_costing_more_than_getting_there_point_to_a_cheaper_stay():
    entries = [said(300, on=TODAY), said(2_400, STAY, on=TODAY)]

    found = nudges(entries, today=TODAY, subsidised_stay=("dh-1", "Dharamshala"),
                   has_scheme_card=True, on_cancer_pathway=False, over_limit=False)  # fmt: skip

    assert [n.kind for n in found] == [NudgeKind.STAY_COSTS_MORE]
    assert found[0].organisation_name == "Dharamshala"


def test_a_train_on_a_cancer_journey_mentions_the_railway_concession():
    train = SpendEntry(
        id="t", patient_id="P", category=TRAVEL, amount_paise=3_100_00, status=SpendStatus.PAID,
        source=SpendSource.FAMILY_STATED, stated_in="train Gaya to Mumbai 3100", on=TODAY,
    )

    found = nudges([train], today=TODAY, subsidised_stay=None, has_scheme_card=True,
                   on_cancer_pathway=True, over_limit=False)  # fmt: skip

    assert NudgeKind.RAIL_CONCESSION in {n.kind for n in found}


# ---------------------------------------------------------------- no made-up rates


def test_the_arithmetic_holds_no_rupee_figure_of_its_own():
    source = Path(__file__).resolve().parent.parent / "backend/saathi/orchestrator/kharcha.py"
    numbers = {
        node.value
        for node in ast.walk(ast.parse(source.read_text()))
        if isinstance(node, ast.Constant) and type(node.value) in (int, float)
    }

    # 100 turns rupees into paise; anything larger would be a rate somebody chose.
    assert {n for n in numbers if n > 100} == set(), f"a constant that looks like a rate: {numbers}"
