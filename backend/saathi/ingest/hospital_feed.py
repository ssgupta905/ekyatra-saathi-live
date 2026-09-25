"""Hospital appointment and turnaround feed.

Two things come from the hospital that ABDM does not carry: the live
appointment slate, and the turnaround history that the conformal predictor is
calibrated on. The second matters more — without it every window is
uncalibrated and every plan is UNCERTAIN.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Sequence
from datetime import date
from io import StringIO
from pathlib import Path

import httpx

from ..readiness.conformal import TurnaroundSample

logger = logging.getLogger(__name__)


def parse_turnaround_csv(text: str) -> tuple[TurnaroundSample, ...]:
    """Parse a turnaround export.

    Expected columns: `queue`, and either `days` or both `procedure_date` and
    `result_date`. Rows that cannot be read are skipped with a warning rather
    than failing the batch — a malformed row should not blind the predictor.
    """
    samples: list[TurnaroundSample] = []
    for row in csv.DictReader(StringIO(text)):
        queue = (row.get("queue") or "").strip().lower()
        if not queue:
            continue
        try:
            if row.get("days"):
                days = float(row["days"])
            else:
                start = date.fromisoformat(row["procedure_date"].strip())
                end = date.fromisoformat(row["result_date"].strip())
                days = (end - start).days
        except (KeyError, ValueError, AttributeError):
            logger.warning("skipping unreadable turnaround row: %r", row)
            continue
        if days < 0:
            continue
        samples.append(TurnaroundSample(queue=queue, days=days))
    return tuple(samples)


def load_turnaround_file(path: str | Path) -> tuple[TurnaroundSample, ...]:
    return parse_turnaround_csv(Path(path).read_text(encoding="utf-8"))


class HospitalFeedClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def turnaround_history(self, hospital_id: str) -> tuple[TurnaroundSample, ...]:
        response = await self._client.get(f"/hospitals/{hospital_id}/turnaround.csv")
        response.raise_for_status()
        return parse_turnaround_csv(response.text)

    async def aclose(self) -> None:
        await self._client.aclose()


def calibration_split(
    samples: Sequence[TurnaroundSample], holdout_fraction: float = 0.2
) -> tuple[tuple[TurnaroundSample, ...], tuple[TurnaroundSample, ...]]:
    """Split history into calibration and holdout sets.

    Split is by position, not at random: turnaround distributions drift, and a
    random split would let the predictor calibrate on the future.
    """
    if not samples:
        return ((), ())
    cut = max(1, int(len(samples) * (1 - holdout_fraction)))
    return (tuple(samples[:cut]), tuple(samples[cut:]))
