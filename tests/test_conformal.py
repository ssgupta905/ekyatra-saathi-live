"""The coverage guarantee is the product claim. Test it as one."""

from __future__ import annotations

import random
from datetime import date

from saathi.readiness.conformal import (
    ConformalReadinessPredictor,
    TurnaroundSample,
    empirical_coverage,
)


def _samples(rng, queue, n, median=7.0, tail_p=0.2):
    out = []
    for _ in range(n):
        days = max(1.0, rng.gauss(median, 2.0))
        if rng.random() < tail_p:
            days += abs(rng.gauss(8.0, 3.0))
        out.append(TurnaroundSample(queue=queue, days=round(days)))
    return out


def test_empirical_coverage_meets_guarantee():
    rng = random.Random(7)
    calibration = _samples(rng, "pathology", 400)
    holdout = [s.days for s in _samples(rng, "pathology", 400)]

    predictor = ConformalReadinessPredictor(alpha=0.1).fit(calibration)
    coverage = empirical_coverage(predictor, "pathology", holdout)

    # Split conformal guarantees >= 1 - alpha in expectation; allow finite-sample slack.
    assert coverage >= 0.85, f"coverage {coverage:.3f} below guarantee"


def test_tighter_alpha_gives_wider_interval():
    rng = random.Random(11)
    calibration = _samples(rng, "pathology", 300)

    loose = ConformalReadinessPredictor(alpha=0.2).fit(calibration).interval_days("pathology")
    tight = ConformalReadinessPredictor(alpha=0.02).fit(calibration).interval_days("pathology")

    assert (tight[1] - tight[0]) >= (loose[1] - loose[0])


def test_small_calibration_set_is_flagged_uncalibrated():
    """The case that must never silently produce a confident date."""
    predictor = ConformalReadinessPredictor(alpha=0.1).fit(
        [TurnaroundSample("pathology", 7.0), TurnaroundSample("pathology", 9.0)]
    )
    _, _, calibrated, n = predictor.interval_days("pathology")
    assert calibrated is False
    assert n == 2


def test_unknown_queue_is_uncalibrated():
    predictor = ConformalReadinessPredictor()
    window = predictor.window("step-1", "queue-we-have-never-seen", date(2026, 3, 1))
    assert window.calibrated is False
    assert window.n_calibration == 0


def test_window_is_anchored_on_the_procedure_date():
    rng = random.Random(3)
    samples = _samples(rng, "radiology", 200, median=3.0)
    predictor = ConformalReadinessPredictor(alpha=0.1).fit(samples)
    anchor = date(2026, 3, 1)
    window = predictor.window("step-1", "radiology", anchor)
    assert window.earliest >= anchor
    assert window.latest > window.earliest
