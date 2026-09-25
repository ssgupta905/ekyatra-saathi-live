"""Readiness windows via split conformal prediction.

The question: "the biopsy was taken on the 4th — by when will the report be
ready?" Point predictions are useless here, because being wrong by two days
costs a family a 500 km round trip. We want an interval with a coverage
guarantee, and split conformal gives one that is distribution-free: it assumes
only that turnaround times are exchangeable, not that they are normal.

Method
------
Given calibration turnarounds y_1..y_n for a queue and a point predictor mu:

    residual_i = |y_i - mu|
    q          = the ceil((n + 1)(1 - alpha))-th smallest residual
    interval   = [mu - q, mu + q]

Coverage is then at least 1 - alpha for an exchangeable new draw. When
ceil((n + 1)(1 - alpha)) > n the quantile does not exist, which is the honest
answer that n is too small for the requested confidence: we mark the window
`calibrated=False` and the planner converts that into Decision.UNCERTAIN rather
than promising a date.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from ..domain.models import ReadinessWindow

#: Below this many observations, no interval is trustworthy regardless of alpha.
MIN_CALIBRATION = 10


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


@dataclass(frozen=True)
class TurnaroundSample:
    """One historical observation: days from procedure to result available."""

    queue: str
    days: float


class ConformalReadinessPredictor:
    """Split conformal predictor over per-queue turnaround history.

    One predictor holds calibration sets for every queue (pathology, radiology,
    per hospital). Queues are kept separate because their turnaround
    distributions differ by more than their spread.
    """

    def __init__(self, alpha: float = 0.1, min_calibration: int = MIN_CALIBRATION) -> None:
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        self.alpha = alpha
        self.min_calibration = min_calibration
        self._calibration: dict[str, list[float]] = {}

    def fit(self, samples: Sequence[TurnaroundSample]) -> ConformalReadinessPredictor:
        for sample in samples:
            self._calibration.setdefault(sample.queue, []).append(sample.days)
        return self

    def n_calibration(self, queue: str) -> int:
        return len(self._calibration.get(queue, ()))

    def _quantile_index(self, n: int) -> int | None:
        """Index (1-based) of the conformal quantile, or None if unattainable."""
        k = math.ceil((n + 1) * (1 - self.alpha))
        return k if k <= n else None

    def interval_days(self, queue: str) -> tuple[float, float, bool, int]:
        """Return (low, high, calibrated, n) in days for `queue`."""
        history = self._calibration.get(queue, [])
        n = len(history)
        if n == 0:
            return (0.0, 0.0, False, 0)

        mu = _median(history)
        residuals = sorted(abs(y - mu) for y in history)
        k = self._quantile_index(n)
        if k is None or n < self.min_calibration:
            # Not enough data for the requested coverage. Report the observed
            # range so a navigator can still see it, but flag it uncalibrated.
            return (min(history), max(history), False, n)

        q = residuals[k - 1]
        return (max(0.0, mu - q), mu + q, True, n)

    def window(self, step_id: str, queue: str, anchor: date) -> ReadinessWindow:
        """Readiness window for a report, anchored on the procedure date."""
        low, high, calibrated, n = self.interval_days(queue)
        return ReadinessWindow(
            step_id=step_id,
            earliest=anchor + timedelta(days=math.floor(low)),
            latest=anchor + timedelta(days=math.ceil(high)),
            alpha=self.alpha,
            calibrated=calibrated,
            n_calibration=n,
        )


def empirical_coverage(
    predictor: ConformalReadinessPredictor, queue: str, holdout: Sequence[float]
) -> float:
    """Fraction of held-out turnarounds falling inside the predicted interval.

    Used by tests and by the pilot's weekly calibration report: if this drifts
    below 1 - alpha the queue's distribution has shifted and the predictor needs
    refitting on recent data.
    """
    if not holdout:
        return 0.0
    low, high, _, _ = predictor.interval_days(queue)
    inside = sum(1 for y in holdout if low <= y <= high)
    return inside / len(holdout)
