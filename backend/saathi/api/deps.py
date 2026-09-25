"""Shared application state.

Built once at startup and handed to routes. Keeping it in one object makes the
degraded modes explicit: if Anthropic credentials are absent the planner still
runs and still decides, it just returns plans without rendered text.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from ..config import Settings, get_settings
from ..graph.dependencies import InMemoryDependencyGraph
from ..language.claude import ClaudeLanguageLayer
from ..ledger.evidence import InMemoryEvidenceLedger
from ..planner.graph import VisitPlanner
from ..readiness.conformal import ConformalReadinessPredictor
from ..synthetic.generate import SyntheticCohort, generate_cohort

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    settings: Settings
    planner: VisitPlanner
    ledger: InMemoryEvidenceLedger
    cohort: SyntheticCohort
    alerts: list = field(default_factory=list)

    def steps_for(self, patient_id: str):
        return self.cohort.steps.get(patient_id, ())

    def patient(self, patient_id: str):
        for patient in self.cohort.patients:
            if patient.id == patient_id:
                return patient
        return None


def build_state(settings: Settings | None = None, today: date | None = None) -> AppState:
    settings = settings or get_settings()
    cohort = generate_cohort(today=today)

    predictor = ConformalReadinessPredictor(alpha=settings.conformal_alpha)
    predictor.fit(cohort.turnaround)

    ledger = InMemoryEvidenceLedger()

    language_layer = None
    if settings.language_layer_enabled:
        language_layer = ClaudeLanguageLayer(model=settings.claude_model)
    else:
        logger.warning(
            "ANTHROPIC_API_KEY not set — planner will decide but not compose messages"
        )

    planner = VisitPlanner(
        dependency_graph=InMemoryDependencyGraph(),
        predictor=predictor,
        ledger=ledger,
        language_layer=language_layer,
    )
    return AppState(settings=settings, planner=planner, ledger=ledger, cohort=cohort)
