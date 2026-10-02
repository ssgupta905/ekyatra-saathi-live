"""What a language backend has to be.

One method, and a name for the console to show. Everything that makes the
output safe lives in `rendering.py` and is not a backend's to choose.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.enums import Channel, Language
from ..domain.models import CaregiverMessage, VisitPlan
from ..ledger.evidence import InMemoryEvidenceLedger


class LanguageLayer(Protocol):
    def render(
        self,
        plan: VisitPlan,
        language: Language,
        channel: Channel,
        ledger: InMemoryEvidenceLedger,
    ) -> CaregiverMessage:
        """Turn a decided plan into a guarded message, or divert it to a human."""
        ...

    def describe(self) -> str:
        """Provider and model, for the console's pipeline view."""
        ...
