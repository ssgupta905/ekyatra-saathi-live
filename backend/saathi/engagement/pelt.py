"""Disengagement detection via PELT change-point analysis.

A family that stops replying is the signal that matters most: 9.4% of patients
in the CROCODILE cohort had an unplanned treatment interruption, and the first
visible sign is silence, not a cancellation.

Naive thresholds ("no reply in 14 days") fire constantly for families who were
always slow to reply and miss the family who replied within an hour for six
weeks and now takes four days. What we want is a *change* in that family's own
baseline. PELT (Pruned Exact Linear Time, Killick et al. 2012) finds the exact
set of change points minimising

    sum over segments of cost(segment) + beta * (number of change points)

with pruning that keeps it near-linear. We use an L2 (change-in-mean) cost on
the response-latency series.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: Penalty multiplier on the BIC-style term. Higher = fewer change points.
DEFAULT_PENALTY_SCALE = 3.0

#: A segment must have at least this many points before it can be called a
#: regime. Two late replies are noise, not disengagement.
MIN_SEGMENT = 3


@dataclass(frozen=True)
class ChangePointResult:
    change_points: tuple[int, ...]
    #: Mean of the final segment vs. the one before it.
    last_segment_mean: float
    previous_segment_mean: float
    #: True when the latest regime is materially worse than the previous one.
    disengaged: bool


class _L2Cost:
    """Change-in-mean cost with O(1) segment evaluation via prefix sums."""

    def __init__(self, series: Sequence[float]) -> None:
        self._n = len(series)
        self._prefix = [0.0] * (self._n + 1)
        self._prefix_sq = [0.0] * (self._n + 1)
        for i, value in enumerate(series):
            self._prefix[i + 1] = self._prefix[i] + value
            self._prefix_sq[i + 1] = self._prefix_sq[i] + value * value

    def __call__(self, start: int, end: int) -> float:
        """Cost of series[start:end] — the within-segment sum of squares."""
        n = end - start
        if n <= 0:
            return 0.0
        total = self._prefix[end] - self._prefix[start]
        total_sq = self._prefix_sq[end] - self._prefix_sq[start]
        return total_sq - (total * total) / n

    def mean(self, start: int, end: int) -> float:
        n = end - start
        if n <= 0:
            return 0.0
        return (self._prefix[end] - self._prefix[start]) / n


def pelt(
    series: Sequence[float],
    penalty: float | None = None,
    min_segment: int = MIN_SEGMENT,
) -> tuple[int, ...]:
    """Return the change-point indices (segment start boundaries, excluding 0)."""
    n = len(series)
    if n < 2 * min_segment:
        return ()

    cost = _L2Cost(series)
    if penalty is None:
        # BIC-flavoured default: scales with log n so longer series need
        # stronger evidence per additional change point.
        import math

        variance = cost(0, n) / n if n else 1.0
        penalty = DEFAULT_PENALTY_SCALE * max(variance, 1e-9) * math.log(n)

    # F[t] = optimal cost of series[0:t]; candidates = pruned set of last change points.
    f = [0.0] * (n + 1)
    f[0] = -penalty
    last_change: list[int] = [0] * (n + 1)
    candidates: list[int] = [0]

    for t in range(min_segment, n + 1):
        best_cost = None
        best_start = 0
        for s in candidates:
            if t - s < min_segment:
                continue
            total = f[s] + cost(s, t) + penalty
            if best_cost is None or total < best_cost:
                best_cost = total
                best_start = s
        if best_cost is None:
            f[t] = f[t - 1]
            last_change[t] = last_change[t - 1]
            continue
        f[t] = best_cost
        last_change[t] = best_start

        # Pruning: s can never be optimal later if f[s] + cost(s,t) >= f[t].
        candidates = [s for s in candidates if f[s] + cost(s, t) <= f[t]]
        candidates.append(t)

    # Walk the backpointers to recover the segmentation.
    points: list[int] = []
    t = n
    while t > 0:
        s = last_change[t]
        if s == 0:
            break
        points.append(s)
        t = s
    return tuple(reversed(points))


def detect_disengagement(
    series: Sequence[float],
    penalty: float | None = None,
    min_segment: int = MIN_SEGMENT,
    worsening_ratio: float = 2.0,
) -> ChangePointResult:
    """Flag a family whose reply latency has shifted to a materially worse regime.

    `worsening_ratio` is how much slower the current regime must be than the
    previous one before we alert. 2.0 means "replies now take at least twice as
    long as they used to" — deliberately conservative, because a false alert
    spends a navigator's scarce time.
    """
    points = pelt(series, penalty=penalty, min_segment=min_segment)
    cost = _L2Cost(series)
    n = len(series)

    if not points:
        mean_all = cost.mean(0, n)
        return ChangePointResult((), mean_all, mean_all, False)

    last_start = points[-1]
    previous_start = points[-2] if len(points) > 1 else 0
    last_mean = cost.mean(last_start, n)
    previous_mean = cost.mean(previous_start, last_start)

    disengaged = previous_mean > 0 and last_mean >= worsening_ratio * previous_mean
    return ChangePointResult(points, last_mean, previous_mean, disengaged)
