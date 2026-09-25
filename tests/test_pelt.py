"""PELT has to find a real regime change and ignore a noisy but stable family."""

from __future__ import annotations

import random

from saathi.engagement.pelt import detect_disengagement, pelt


def test_finds_a_clear_change_point():
    #  A family replying in ~2h, then in ~30h.
    series = [2.0, 1.5, 2.5, 2.0, 1.8, 2.2, 30.0, 28.0, 33.0, 31.0, 29.0, 35.0]
    points = pelt(series)
    assert points, "expected at least one change point"
    # The shift is at index 6; allow a one-observation boundary tolerance.
    assert any(abs(p - 6) <= 1 for p in points), points


def test_stable_but_noisy_series_does_not_alert():
    rng = random.Random(5)
    series = [max(0.5, rng.gauss(6.0, 2.0)) for _ in range(40)]
    result = detect_disengagement(series)
    assert result.disengaged is False


def test_disengagement_flagged_when_latency_regime_worsens():
    series = [1.0, 1.2, 0.9, 1.1, 1.0, 1.3, 24.0, 30.0, 26.0, 28.0, 31.0]
    result = detect_disengagement(series)
    assert result.disengaged is True
    assert result.last_segment_mean > result.previous_segment_mean


def test_improving_engagement_is_not_an_alert():
    """A family that starts replying faster must never be flagged."""
    series = [30.0, 28.0, 33.0, 31.0, 29.0, 2.0, 1.5, 2.5, 2.0, 1.8]
    result = detect_disengagement(series)
    assert result.disengaged is False


def test_short_series_returns_no_change_points():
    assert pelt([1.0, 2.0, 3.0]) == ()
