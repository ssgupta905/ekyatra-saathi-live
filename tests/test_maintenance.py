"""Maintenance: 17 doses every 21 days, with an echo + review before every
fourth dose (5, 9, 13, 17) — the repeating phase Story 2 lives in.
"""

from __future__ import annotations

from datetime import date, timedelta

from saathi.domain.models import MaintenanceCycle
from saathi.planner.tools import due_dose, next_dose_not_before, requires_echo_bundle


def test_dose_13_requires_an_echo_bundle():
    assert requires_echo_bundle(13)


def test_most_doses_do_not_require_an_echo_bundle():
    assert not requires_echo_bundle(12)
    assert not requires_echo_bundle(6)


def test_a_dose_becomes_due_on_its_anchor_date():
    cycle = MaintenanceCycle(patient_id="P0001", dose_index=1, anchor_date=date(2026, 9, 1))
    assert due_dose(cycle, date(2026, 9, 1)) == 1
    assert due_dose(cycle, date(2026, 8, 31)) is None


def test_doses_advance_every_twenty_one_days_from_the_anchor():
    cycle = MaintenanceCycle(patient_id="P0001", dose_index=13, anchor_date=date(2026, 9, 1))
    due_on = date(2026, 9, 1) + timedelta(days=cycle.interval_days * (cycle.dose_index - 1))
    assert due_dose(cycle, due_on) == 13
    assert due_dose(cycle, due_on - timedelta(days=1)) is None


def test_a_cycle_past_its_total_doses_has_nothing_due():
    cycle = MaintenanceCycle(
        patient_id="P0001", dose_index=18, total_doses=17, anchor_date=date(2026, 1, 1)
    )
    assert due_dose(cycle, date(2030, 1, 1)) is None


def test_the_dose_after_a_delayed_one_is_not_pulled_earlier():
    cycle = MaintenanceCycle(patient_id="P0001", dose_index=13, anchor_date=date(2026, 9, 1))
    # Spacing is anchor-relative, so a late dose 13 does not compress the
    # 21-day gap before dose 14 — the next dose is still anchor + 13*21 days.
    expected = date(2026, 9, 1) + timedelta(days=cycle.interval_days * 13)
    assert next_dose_not_before(cycle, completed_doses=13) == expected
