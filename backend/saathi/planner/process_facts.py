"""The fact behind a process-only inbound answer.

Deterministic: the model never decides *what* is happening to a family, only
how to phrase it (if at all) — the same split `planner/tools.py::decide`
already enforces for the travel decision itself. Reads only the open
disruption/pending approval for one patient; never report content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ProcessFact:
    """"Who decides, and by when" — the only shape a process answer can take."""

    awaiting: str
    by: date | None
    disruption_id: str


def resolve_process_fact(patient_id: str, world) -> ProcessFact | None:
    """The open process fact for `patient_id`, if any.

    None when nothing is pending for them — the caller should not answer at
    all in that case, rather than invent a fact to report.
    """
    for disruption in world.open_disruptions():
        if patient_id not in world.affected_patients(disruption):
            continue
        pending = getattr(world, "pending_approval", {}).get(patient_id)
        if pending == disruption.id:
            return ProcessFact(
                awaiting="the doctor or navigator decides",
                by=disruption.unavailable_to,
                disruption_id=disruption.id,
            )
        return ProcessFact(
            awaiting="Saathi is working out the new plan",
            by=disruption.unavailable_to,
            disruption_id=disruption.id,
        )
    return None
