"""How the lab is running this week, measured from its own output.

`readiness/conformal.py` gives a coverage guarantee over a *calibration set* —
the turnaround history the queue has shown over months. That is the right
baseline and it is deliberately slow to move. But a family waiting this week does
not live in the long run: pathology can be three days behind because two
technicians are off, and a window built on the six-month median will quietly be
wrong for everybody in the queue right now.

So this tool measures the recent past against the baseline and reports the
difference. Both numbers come from records the system already holds — the
ledger's release rows and the calibration set — so nothing is fetched, nothing is
assumed, and a backlog only exists when the lab's own output shows one.

Nothing here reads a report. `report_status` returns a status and a date and has
no field that could carry a finding; that boundary is `domain/models.py`'s and
this module does not get to relax it.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import date

from ..domain.enums import SourceSystem, StepStatus
from ..domain.models import CareStep
from ..readiness.conformal import TurnaroundSample
from .base import PROVIDER_LOCAL, ToolResult

logger = logging.getLogger(__name__)

#: Releases needed before "recently" means anything. Below this the sample is
#: too small to call a backlog, and saying nothing is the honest answer.
MIN_RECENT_RELEASES = 3

#: How many of the most recent releases count as "this week".
RECENT_WINDOW = 12

#: Days of drift before it is worth telling anyone. Under this, a queue is just
#: a queue, and reporting noise as news trains people to ignore the signal.
BACKLOG_THRESHOLD_DAYS = 1.0


@dataclass(frozen=True)
class LabStatus:
    queue: str
    baseline_median_days: float | None
    recent_median_days: float | None
    n_recent: int
    n_baseline: int

    @property
    def drift_days(self) -> float | None:
        if self.recent_median_days is None or self.baseline_median_days is None:
            return None
        return self.recent_median_days - self.baseline_median_days

    @property
    def running_behind(self) -> bool:
        drift = self.drift_days
        return drift is not None and drift >= BACKLOG_THRESHOLD_DAYS

    def to_json(self) -> dict:
        return {
            "queue": self.queue,
            "baseline_median_days": self.baseline_median_days,
            "recent_median_days": self.recent_median_days,
            "drift_days": self.drift_days,
            "running_behind": self.running_behind,
            "n_recent": self.n_recent,
            "n_baseline": self.n_baseline,
        }


@dataclass(frozen=True)
class ReportStatus:
    """Status and timing only. There is no field here for a finding."""

    step_id: str
    queue: str | None
    status: str
    released_on: date | None

    def to_json(self) -> dict:
        return {
            "step_id": self.step_id,
            "queue": self.queue,
            "status": self.status,
            "released_on": self.released_on.isoformat() if self.released_on else None,
        }


class LabTool:
    """Queue health from the lab's own releases, and report status, never content."""

    name = "lab.queue_status"

    def __init__(self, baseline: tuple[TurnaroundSample, ...] = ()) -> None:
        self._baseline = baseline

    def queue_status(
        self,
        queue: str,
        released: tuple[tuple[date, date], ...],
    ) -> ToolResult[LabStatus] | None:
        """Compare this queue's recent turnaround against its own baseline.

        `released` is `(procedure_day, released_day)` pairs the system has
        actually observed — ledger rows, not ground truth. Returns None when
        there are too few to say anything, which is a real and frequent answer.
        """
        baseline_days = [s.days for s in self._baseline if s.queue == queue]
        recent_days = sorted(
            ((released_on - procedure_on).days for procedure_on, released_on in released),
        )[-RECENT_WINDOW:]

        if len(recent_days) < MIN_RECENT_RELEASES:
            return None

        status = LabStatus(
            queue=queue,
            baseline_median_days=(
                statistics.median(baseline_days) if baseline_days else None
            ),
            recent_median_days=statistics.median(recent_days),
            n_recent=len(recent_days),
            n_baseline=len(baseline_days),
        )

        if status.drift_days is None:
            claim = (
                f"{queue.replace('_', ' ')} has released {status.n_recent} reports "
                f"recently, median {status.recent_median_days:.0f} days; no baseline "
                f"to compare against"
            )
        elif status.running_behind:
            claim = (
                f"{queue.replace('_', ' ')} is running {status.drift_days:.0f} days "
                f"behind its usual {status.baseline_median_days:.0f}"
            )
        else:
            claim = (
                f"{queue.replace('_', ' ')} is running to its usual "
                f"{status.baseline_median_days:.0f} days"
            )

        return ToolResult(
            value=status,
            tool=self.name,
            source=SourceSystem.DERIVED,
            source_record_id=f"queue:{queue}",
            claim=claim,
            provider=PROVIDER_LOCAL,
            detail=status.to_json(),
        )

    def report_status(self, step: CareStep) -> ToolResult[ReportStatus] | None:
        """Whether a report has landed. Deliberately incapable of saying more."""
        if step.status not in (StepStatus.PENDING_RESULT, StepStatus.RESULT_AVAILABLE):
            return None
        status = ReportStatus(
            step_id=step.id,
            queue=step.queue,
            status=step.status.value,
            released_on=step.result_available_on,
        )
        landed = step.status is StepStatus.RESULT_AVAILABLE
        return ToolResult(
            value=status,
            tool="lab.report_status",
            source=SourceSystem.ABDM,
            source_record_id=step.id,
            claim=(
                f"{step.kind.value.replace('_', ' ')} "
                + (
                    f"was released on {step.result_available_on:%d %b}"
                    if landed and step.result_available_on
                    else "has not been released yet"
                )
            ),
            provider=PROVIDER_LOCAL,
            detail=status.to_json(),
        )
