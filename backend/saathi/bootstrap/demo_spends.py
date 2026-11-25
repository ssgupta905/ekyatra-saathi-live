"""A few past spends for the demo families, so their books are not an empty page.

Every one is written as the family would have said it, marked "(demo)", and
already confirmed — exactly the entries a family's own "₹350 auto" becomes.
Nothing here is a rate: the projection the family sees is worked from these
entries, the same way it would be from real ones.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..domain.spends import SpendCategory, SpendEntry, SpendSource, SpendStatus
from ..ports.spends import SpendStore

_TRAVEL, _STAY, _FOOD = SpendCategory.TRAVEL, SpendCategory.STAY, SpendCategory.FOOD


def seed_demo_spends(store: SpendStore, today: date) -> int:
    """Fill the demo families' past trips. Returns how many entries it wrote."""
    first_visit = today - timedelta(days=6)
    said = [
        # Anita: the first trip to Mumbai, for the tests.
        ("DEMO-1", first_visit, _TRAVEL, 3100, "train Gaya to Mumbai, two of us, both ways 3100"),
        ("DEMO-1", first_visit, _TRAVEL, 350, "auto from the station to the hospital 350"),
        ("DEMO-1", first_visit, _STAY, 2400, "lodge near Parel, four nights, 2400"),
        ("DEMO-1", first_visit, _FOOD, 1200, "food for the week 1200"),
    ]
    # Meena: the last three dialysis sessions, an auto each way and tea.
    for days_ago in (1, 3, 5):
        session = today - timedelta(days=days_ago)
        said.append(("DEMO-3", session, _TRAVEL, 180, "auto both ways 180"))
        said.append(("DEMO-3", session, _FOOD, 40, "tea and biscuits 40"))

    for n, (pid, on, category, rupees, words) in enumerate(said):
        store.save(
            SpendEntry(
                id=f"sp-{pid}-demo-{n}",
                patient_id=pid,
                category=category,
                amount_paise=rupees * 100,
                status=SpendStatus.PAID,
                source=SpendSource.FAMILY_STATED,
                stated_in=f"(demo) {words}",
                on=on,
                visit_on=on,
            )
        )
    return len(said)


__all__ = ["seed_demo_spends"]
