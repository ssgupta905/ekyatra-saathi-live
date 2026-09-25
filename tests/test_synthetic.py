"""The prototype's own evaluation must be honest about what it measures."""

from __future__ import annotations

from datetime import date, timedelta

from saathi.synthetic.generate import (
    evaluate,
    generate_cohort,
    would_be_wasted,
)

TODAY = date(2026, 3, 10)


def test_cohort_is_deterministic_for_a_seed():
    a = generate_cohort(n_patients=10, seed=1, today=TODAY)
    b = generate_cohort(n_patients=10, seed=1, today=TODAY)
    assert [p.id for p in a.patients] == [p.id for p in b.patients]
    assert [g.naive_return_date for g in a.ground_truth.values()] == [
        g.naive_return_date for g in b.ground_truth.values()
    ]


def test_ground_truth_covers_both_reports():
    cohort = generate_cohort(n_patients=5, seed=2, today=TODAY)
    for truth in cohort.ground_truth.values():
        assert len(truth.true_ready_on) == 2


def test_turnaround_history_is_large_enough_to_calibrate():
    cohort = generate_cohort(n_patients=5, seed=3, today=TODAY)
    queues = {s.queue for s in cohort.turnaround}
    assert queues == {"pathology_report", "radiology_report"}
    for queue in queues:
        assert sum(1 for s in cohort.turnaround if s.queue == queue) >= 100


def test_baseline_wastes_trips():
    """If the naive baseline wasted nothing, the benchmark would be vacuous."""
    cohort = generate_cohort(n_patients=80, seed=4, today=TODAY)
    scores = evaluate(cohort, {p.id: None for p in cohort.patients})
    assert scores["baseline_wasted_trips"] > 0


def test_waiting_is_never_scored_as_a_wasted_trip():
    cohort = generate_cohort(n_patients=20, seed=5, today=TODAY)
    scores = evaluate(cohort, {p.id: None for p in cohort.patients})
    assert scores["saathi_wasted_trips"] == 0


def test_travelling_after_the_last_report_lands_is_never_wasted():
    cohort = generate_cohort(n_patients=20, seed=6, today=TODAY)
    decisions = {
        pid: max(truth.true_ready_on.values()) + timedelta(days=1)
        for pid, truth in cohort.ground_truth.items()
    }
    scores = evaluate(cohort, decisions)
    assert scores["saathi_wasted_trips"] == 0


def test_travelling_too_early_is_counted_as_wasted():
    cohort = generate_cohort(n_patients=20, seed=7, today=TODAY)
    decisions = {
        pid: min(truth.true_ready_on.values()) - timedelta(days=3)
        for pid, truth in cohort.ground_truth.items()
    }
    scores = evaluate(cohort, decisions)
    assert scores["saathi_wasted_trips"] > 0


def test_would_be_wasted_uses_the_last_report_not_the_first():
    cohort = generate_cohort(n_patients=1, seed=8, today=TODAY)
    truth = next(iter(cohort.ground_truth.values()))
    earliest, latest = min(truth.true_ready_on.values()), max(truth.true_ready_on.values())
    if earliest < latest:
        assert would_be_wasted(truth, earliest) is True
    assert would_be_wasted(truth, latest) is False


def test_avoided_counts_redirected_trips_not_just_withheld_ones():
    """Moving a family to a safe date saves the same journey as telling them to wait."""
    cohort = generate_cohort(n_patients=60, seed=9, today=TODAY)
    safe = {
        pid: max(truth.true_ready_on.values()) + timedelta(days=1)
        for pid, truth in cohort.ground_truth.items()
    }
    scores = evaluate(cohort, safe)
    assert scores["saathi_wasted_trips"] == 0
    assert scores["wasted_trips_avoided"] == scores["baseline_wasted_trips"]


def test_avoided_never_exceeds_the_baseline():
    cohort = generate_cohort(n_patients=40, seed=10, today=TODAY)
    scores = evaluate(cohort, {p.id: None for p in cohort.patients})
    assert scores["wasted_trips_avoided"] <= scores["baseline_wasted_trips"]
