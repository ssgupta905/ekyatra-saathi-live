"""How the application announces that something happened."""

from __future__ import annotations

from typing import Any, Protocol


class EventPublisher(Protocol):
    def publish(
        self,
        kind: str,
        sim_date: str,
        *,
        patient_id: str | None = None,
        summary: str = "",
        duration_ms: float | None = None,
        **payload: Any,
    ) -> Any:
        """Announce an event. Safe to call from any thread."""
        ...
