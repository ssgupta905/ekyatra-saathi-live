"""Cost, and the family who has to bear it.

Not everybody can absorb an app cab and a chain hotel. These pin the three
things that follow from saying so: who gets asked, which way the
nights-versus-trips trade goes, and — the one that matters most — where cost is
not allowed to reach at all.
"""

from __future__ import annotations

import pytest
from saathi.bootstrap.demo_directory import DEMO_DIRECTORY
from saathi.domain.affordability import (
    MEANS_SENSITIVE,
    PREFERENCE,
    CostTier,
    Means,
    means_from,
    nights_hurt_more_than_trips,
    rank_of,
)
from saathi.domain.directory import NEED_FOR_TYPE
from saathi.domain.enums import Decision, ReadinessKind
from saathi.domain.models import PlanOption
from saathi.orchestrator import choose_organisation
from saathi.planner.options import _rank_key


def ask(kind: ReadinessKind, district: str, means: Means):
    org = choose_organisation(
        kind,
        district=district,
        hospital_id="TMH-MUM",
        organisations=DEMO_DIRECTORY,
        means=means,
    )
    return org.name if org else None


# ---------------- what the family told us ----------------


@pytest.mark.parametrize(
    ("card", "band", "expected"),
    [
        ("aay", "", Means.STRETCHED),
        ("bpl", "", Means.STRETCHED),
        ("apl", "", Means.MODEST),
        # The card leads over the band, even when they disagree: the card is a
        # determination made against evidence, the band is a number a family
        # said out loud at a counter.
        ("aay", "2 to 3 lakh a year", Means.STRETCHED),
        ("none", "below 1 lakh a year", Means.STRETCHED),
        ("", "", Means.NOT_STATED),
        # Unreadable free text goes quiet rather than raising. A profile that
        # will not load is a worse failure than one field saying nothing.
        ("", "about six thousand a month", Means.NOT_STATED),
    ],
)
def test_means_comes_from_the_card_first_and_never_raises(card, band, expected):
    assert means_from(ration_card=card, income_band=band) is expected


def test_a_family_who_has_not_said_is_not_presumed_poor():
    """Two harms, and this avoids both.

    Presuming poverty of a family who has not said so is patronising, and it
    takes a rationed bed from somebody who had to declare theirs.
    """
    order = PREFERENCE[Means.NOT_STATED]
    assert order[0] is CostTier.MODEST
    assert order[-1] is CostTier.SUBSIDISED
    assert PREFERENCE[Means.NOT_STATED] == PREFERENCE[Means.MODEST]


def test_only_a_declared_household_reaches_for_the_subsidised_thing_first():
    for means, order in PREFERENCE.items():
        first_is_subsidised = order[0] is CostTier.SUBSIDISED
        assert first_is_subsidised == (means is Means.STRETCHED), means


# ---------------- who gets asked ----------------


def test_a_stretched_family_is_offered_the_train_not_an_app_cab():
    assert ask(ReadinessKind.TRANSPORT, "Gaya", Means.STRETCHED) == "Railway patient quota desk"
    assert ask(ReadinessKind.STAY, "Mumbai", Means.STRETCHED) == "Patient dharamshala, Parel"
    assert ask(ReadinessKind.MEDICINE, "Mumbai", Means.STRETCHED) == "Jan Aushadhi Kendra, Parel"


def test_a_comfortable_family_still_gets_the_market_rate_option():
    assert ask(ReadinessKind.STAY, "Mumbai", Means.COMFORTABLE) == "OYO, Parel"


def test_cost_never_reorders_a_clinical_allocation():
    """The one that would be a real failure.

    A slot, a doctor and a bed are the hospital's to allocate. Ordering them by
    price would send the poorest family to a cheaper provider for their care
    rather than their travel, which is a clinical decision wearing a logistics
    hat. So the tier is ignored for every need outside `MEANS_SENSITIVE`.
    """
    clinical = [k for k in ReadinessKind if k.value in NEED_FOR_TYPE] 
    assert any(k.value not in MEANS_SENSITIVE for k in clinical)
    for kind in clinical:
        if kind.value in MEANS_SENSITIVE:
            continue
        answers = {ask(kind, "Mumbai", m) for m in Means}
        assert len(answers) == 1, f"{kind.value} changed with means: {answers}"


def test_nothing_is_filtered_out_so_a_full_dharamshala_still_falls_through():
    """Reordering, never filtering.

    Every organisation has to stay reachable: a shelter with no beds tonight
    must still fall through its `alternate_id` chain to something that has one.
    """
    reachable = {
        ask(kind, place, means)
        for kind in (ReadinessKind.TRANSPORT, ReadinessKind.STAY)
        for place in ("Mumbai", "Gaya", "Patna")
        for means in Means
    }
    assert len([r for r in reachable if r]) > 4
    stays = [o for o in DEMO_DIRECTORY if o.type.value == "hotel"]
    assert {o.cost_tier for o in stays} == set(CostTier), "every tier of stay exists to fall to"


def test_an_untiered_organisation_is_never_mistaken_for_a_cheap_one():
    """The default has to be the safe direction.

    An organisation nobody has looked at should not be offered to a family who
    cannot afford to be wrong about it.
    """
    assert rank_of(CostTier.STANDARD, Means.STRETCHED) == 2


# ---------------- the trade ----------------


def option(*, nights: int, trips: int) -> PlanOption:
    return PlanOption(
        patient_id="P1",
        target_step_id="s1",
        decision=Decision.GO,
        nights_added=nights,
        extra_trips=trips,
        short_notice_journeys=0,
        dose_delay_days=0,
    )


def test_a_daily_wage_household_is_offered_the_journey_over_the_nights():
    """Three nights in Mumbai is three days not earning; a fare is painful once."""
    stay_put = option(nights=3, trips=0)
    go_home = option(nights=0, trips=2)

    stretched = sorted([stay_put, go_home], key=lambda o: _rank_key(o, Means.STRETCHED))
    everyone_else = sorted([stay_put, go_home], key=lambda o: _rank_key(o, Means.COMFORTABLE))

    assert stretched[0] is go_home
    assert everyone_else[0] is stay_put
    assert nights_hurt_more_than_trips(Means.STRETCHED)
    assert not nights_hurt_more_than_trips(Means.NOT_STATED)


def test_an_unbookable_plan_still_loses_to_an_expensive_one_either_way():
    """Cost never promotes a plan that may not exist.

    A reserved berth that cannot be obtained in time is not a cheaper journey,
    it is an imaginary one, so short notice stays ahead of money for everybody.
    """
    imaginary = option(nights=0, trips=2).model_copy(update={"short_notice_journeys": 1})
    real_but_costly = option(nights=4, trips=0)
    for means in Means:
        ranked = sorted([imaginary, real_but_costly], key=lambda o: _rank_key(o, means))
        assert ranked[0] is real_but_costly, means


def test_a_dose_delay_is_never_traded_away_to_save_a_family_money():
    """The one cost here that is not the family's money ranks last either way."""
    for means in Means:
        assert _rank_key(option(nights=0, trips=0), means)[3] == 0
