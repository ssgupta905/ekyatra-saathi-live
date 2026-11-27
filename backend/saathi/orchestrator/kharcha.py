"""A family's month: what is spent, what is booked, and what is still to come.

Pure arithmetic over entries somebody gave us (`domain/spends.py`). There is no
rate table in this file and there must never be one: a projection is the
family's own last visits repeated, or a provider's quote, or an honest "we
cannot say yet" (`tests/test_kharcha.py` scans for a constant rupee figure).

The repeat uses the *median-low* of the last three visits rather than the mean,
for a reason a family would recognise: one trip where the train was missed and
a second night was needed should not make every trip after it look dearer, and
median-low always lands on a figure that actually happened.
"""

from __future__ import annotations

import re
import statistics
from calendar import monthrange
from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from ..domain.spends import (
    MOST_ONE_SPEND_PAISE,
    Basis,
    MonthOutlook,
    Nudge,
    NudgeKind,
    ProjectionLine,
    SpendCategory,
    SpendEntry,
    SpendSource,
    SpendStatus,
)

#: How many past visits a repeat is worked from.
VISITS_REMEMBERED = 3


def month_of(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    return first, first.replace(day=monthrange(first.year, first.month)[1])


def next_month(day: date) -> date:
    _, last = month_of(day)
    return last + timedelta(days=1)


# ---------------------------------------------------------------- reading a family's words

_DIGITS = str.maketrans(
    "०१२३४५६७८९০১২৩৪৫৬৭৮৯୦୧୨୩୪୫୬୭୮୯௦௧௨௩௪௫௬௭௮௯",
    "0123456789" * 4,
)

_CURRENCY = r"(?:₹|rs\.?|inr|रु\.?|रुपये|रुपए|টাকা|ଟଙ୍କା|ரூ\.?|ரூபாய்)"
_NUMBER = re.compile(rf"({_CURRENCY})?\s*(\d[\d,]*(?:\.\d{{1,2}})?)\s*({_CURRENCY})?", re.I)

#: Words a family uses for each kind of spend, in the five languages the apps speak.
#: Latin words match on word boundaries, plural allowed ("ola" must not match "Kolkata").
_WORDS: dict[SpendCategory, tuple[str, ...]] = {
    SpendCategory.TRAVEL: (
        "auto",
        "rickshaw",
        "cab",
        "taxi",
        "uber",
        "ola",
        "train",
        "bus",
        "ticket",
        "fare",
        "metro",
        "petrol",
        "ऑटो",
        "रिक्शा",
        "टैक्सी",
        "ट्रेन",
        "रेल",
        "बस",
        "टिकट",
        "किराया",
        "गाड़ी",
        "অটো",
        "ট্রেন",
        "বাস",
        "টিকিট",
        "ভাড়া",
        "ଅଟୋ",
        "ଟ୍ରେନ",
        "ବସ",
        "ଟିକେଟ",
        "ஆட்டோ",
        "ரயில்",
        "பஸ்",
        "டிக்கெட்",
    ),
    SpendCategory.STAY: (
        "hotel",
        "lodge",
        "room",
        "dharamshala",
        "stay",
        "होटल",
        "कमरा",
        "धर्मशाला",
        "लॉज",
        "হোটেল",
        "ঘর",
        "ধর্মশালা",
        "ହୋଟେଲ",
        "ଧର୍ମଶାଳା",
        "ஹோட்டல்",
        "அறை",
        "விடுதி",
    ),
    SpendCategory.FOOD: (
        "food",
        "khana",
        "meal",
        "tea",
        "chai",
        "breakfast",
        "lunch",
        "dinner",
        "खाना",
        "भोजन",
        "चाय",
        "নাস্তা",
        "খাবার",
        "ଖାଦ୍ୟ",
        "ଖାଇବା",
        "சாப்பாடு",
        "உணவு",
        "டீ",
    ),
    SpendCategory.MEDICINE: (
        "medicine",
        "dawa",
        "dawai",
        "pharmacy",
        "chemist",
        "दवा",
        "दवाई",
        "ওষুধ",
        "ঔষধ",
        "ଔଷଧ",
        "மருந்து",
    ),
    SpendCategory.HOSPITAL: (
        "hospital",
        "opd",
        "fee",
        "bill",
        "अस्पताल",
        "बिल",
        "फीस",
        "হাসপাতাল",
        "বিল",
        "ଡାକ୍ତରଖାନା",
        "ବିଲ୍",
        "மருத்துவமனை",
        "பில்",
    ),
}

_RAIL_WORDS = ("train", "rail", "ट्रेन", "रेल", "ট্রেন", "ଟ୍ରେନ", "ரயில்")


def _mentions(text: str, words: Iterable[str]) -> bool:
    lowered = text.lower()
    for word in words:
        if word.isascii():
            if re.search(rf"\b{re.escape(word)}s?\b", lowered):
                return True
        elif word in lowered:
            return True
    return False


def read_spend(text: str) -> tuple[int | None, SpendCategory | None]:
    """The amount and kind of spend in a family's own words, when it can be read for sure.

    Returns `(None, ...)` rather than guessing when there are two numbers and
    neither is marked as money ("2 autos 300" could be either), or when the
    figure is not plausible for one spend. The family is then asked to type it.
    """
    plain = text.translate(_DIGITS)
    found = [(bool(m.group(1) or m.group(3)), m.group(2)) for m in _NUMBER.finditer(plain)]
    marked = [n for is_money, n in found if is_money]
    candidates = marked if marked else [n for _, n in found]
    amount: int | None = None
    if len(set(candidates)) == 1:
        rupees = float(candidates[0].replace(",", ""))
        paise = round(rupees * 100)
        if 1 <= paise <= MOST_ONE_SPEND_PAISE:
            amount = paise
    category = next((c for c, words in _WORDS.items() if _mentions(plain, words)), None)
    return amount, category


def mentions_rail(text: str | None) -> bool:
    return bool(text) and _mentions(text, _RAIL_WORDS)


# ---------------------------------------------------------------- visits ahead


def visits_ahead(
    *,
    scheduled: Iterable[date],
    last_visit: date | None,
    interval_days: int | None,
    remaining: int | None,
    start: date,
    end: date,
) -> tuple[date, ...]:
    """The visits between `start` and `end`: those booked, then the regimen's rhythm.

    A recurring pathway (chemo every 21 days, dialysis every 2) is extended from
    its latest known visit, never past the number of visits the regimen has
    left. A one-off visit is only ever the date the hospital booked.
    """
    days = {d for d in scheduled if start <= d <= end}
    if interval_days and interval_days > 0:
        anchor = max([d for d in scheduled] + ([last_visit] if last_visit else []), default=None)
        left = remaining
        day = anchor
        while day is not None and (left is None or left > 0):
            day = day + timedelta(days=interval_days)
            if day > end:
                break
            if day >= start:
                days.add(day)
            if left is not None:
                left -= 1
    return tuple(sorted(days))


# ---------------------------------------------------------------- the month


def _in(entry: SpendEntry, first: date, last: date) -> bool:
    return first <= entry.on <= last


#: A room offered to the family but not yet booked by them. It is a price
#: they may take or leave, so it is not money they have committed to.
_OFFER_REFS = ("stay-quote:", "stay-deal:")


def _is_booking(entry: SpendEntry) -> bool:
    return (
        entry.status is SpendStatus.QUOTED
        and entry.source is not SpendSource.PROVIDER_ESTIMATE
        and entry.out_of_pocket
        and not (entry.source_ref or "").startswith(_OFFER_REFS)
    )


def outlook(
    entries: Sequence[SpendEntry],
    *,
    month: date,
    today: date,
    visits: Sequence[date],
) -> MonthOutlook:
    """One month for one family, every figure traceable to the entries it came from."""
    first, last = month_of(month)
    spent = [e for e in entries if e.counts and e.out_of_pocket and _in(e, first, last)]
    booked = [e for e in entries if _is_booking(e) and _in(e, first, last)]

    by_category: dict[str, int] = {}
    for e in spent:
        by_category[e.category.value] = by_category.get(e.category.value, 0) + e.amount_paise

    paid_visits = {e.visit_on for e in spent if e.visit_on}
    ahead = tuple(v for v in visits if first <= v <= last and v >= today and v not in paid_visits)

    lines, expected = _expected(entries, ahead, today)
    return MonthOutlook(
        month=first,
        spent_paise=sum(e.amount_paise for e in spent),
        booked_paise=sum(e.amount_paise for e in booked),
        expected_paise=expected,
        visits_ahead=ahead,
        lines=lines,
        by_category=by_category,
    )


def _expected(
    entries: Sequence[SpendEntry], ahead: Sequence[date], today: date
) -> tuple[tuple[ProjectionLine, ...], int | None]:
    if not ahead:
        return (), 0

    history = [
        e for e in entries if e.counts and e.out_of_pocket and e.visit_on and e.visit_on < today
    ]
    past_visits = sorted({e.visit_on for e in history if e.visit_on})[-VISITS_REMEMBERED:]
    quoted = {(e.visit_on, e.category) for e in entries if _is_booking(e) and e.visit_on}

    if not past_visits:
        unquoted = [v for v in ahead if not any(q[0] == v for q in quoted)]
        if not unquoted:
            return (), 0
        return (ProjectionLine(category=SpendCategory.OTHER, amount_paise=None,
                               basis=Basis.NOTHING_TO_GO_ON),), None  # fmt: skip

    used = [e for e in history if e.visit_on in past_visits]
    categories = sorted({e.category for e in used}, key=lambda c: c.value)
    lines: list[ProjectionLine] = []
    total = 0
    for category in categories:
        per_visit = statistics.median_low(
            sum(e.amount_paise for e in used if e.visit_on == v and e.category is category)
            for v in past_visits
        )
        count = sum(1 for v in ahead if (v, category) not in quoted)
        if count == 0 or per_visit == 0:
            continue
        amount = per_visit * count
        total += amount
        lines.append(
            ProjectionLine(
                category=category,
                amount_paise=amount,
                basis=Basis.REPEAT_OF_VISITS,
                visits_used=len(past_visits),
                based_on=tuple(e.id for e in used if e.category is category),
            )
        )
    return tuple(lines), total


# ---------------------------------------------------------------- suggestions


def nudges(
    entries: Sequence[SpendEntry],
    *,
    today: date,
    subsidised_stay: tuple[str, str] | None,
    has_scheme_card: bool,
    on_cancer_pathway: bool,
    over_limit: bool,
) -> tuple[Nudge, ...]:
    """What the family might do about it. Each is a rule over their own entries; none guesses."""
    recent = [e for e in entries if e.counts and e.on >= today - timedelta(days=62)]

    def total(category: SpendCategory) -> int:
        return sum(e.amount_paise for e in recent if e.category is category)

    found: list[Nudge] = []
    if over_limit:
        found.append(Nudge(kind=NudgeKind.OVER_WHAT_YOU_SAID))
    if subsidised_stay and total(SpendCategory.STAY) > total(SpendCategory.TRAVEL) > 0:
        already = {e.organisation_id for e in recent if e.category is SpendCategory.STAY}
        if subsidised_stay[0] not in already:
            found.append(
                Nudge(
                    kind=NudgeKind.STAY_COSTS_MORE,
                    organisation_id=subsidised_stay[0],
                    organisation_name=subsidised_stay[1],
                )
            )
    if not has_scheme_card and total(SpendCategory.HOSPITAL) + total(SpendCategory.MEDICINE) > 0:
        found.append(Nudge(kind=NudgeKind.SCHEME_MAY_COVER))
    if on_cancer_pathway and any(
        e.category is SpendCategory.TRAVEL and mentions_rail(e.stated_in) for e in recent
    ):
        found.append(Nudge(kind=NudgeKind.RAIL_CONCESSION))
    return tuple(found)


__all__ = [
    "VISITS_REMEMBERED",
    "mentions_rail",
    "month_of",
    "next_month",
    "nudges",
    "outlook",
    "read_spend",
    "visits_ahead",
]
