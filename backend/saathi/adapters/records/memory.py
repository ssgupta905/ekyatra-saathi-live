"""A record store that keeps everything in dictionaries."""

from __future__ import annotations

from ...domain.enums import StepKind
from ...domain.models import CareStep, Patient, Resource
from ...ports.records import StoredRecords, TurnaroundObservation


class MemoryRecordStore:
    def __init__(self) -> None:
        self._patients: dict[str, Patient] = {}
        self._steps: dict[str, dict[str, CareStep]] = {}
        self._resources: dict[str, Resource] = {}
        self._targets: dict[str, StepKind] = {}
        self._turnaround: list[TurnaroundObservation] = []

    def load(self) -> StoredRecords:
        return StoredRecords(
            patients=tuple(self._patients.values()),
            steps={pid: tuple(rows.values()) for pid, rows in self._steps.items()},
            resources=tuple(self._resources.values()),
            plan_targets=dict(self._targets),
            turnaround=tuple(self._turnaround),
        )

    def save_patient(self, patient: Patient, plan_target: StepKind | None = None) -> None:
        self._patients[patient.id] = patient
        self._steps.setdefault(patient.id, {})
        if plan_target is not None:
            self._targets[patient.id] = plan_target

    def save_step(self, step: CareStep) -> None:
        self._steps.setdefault(step.patient_id, {})[step.id] = step

    def save_resource(self, resource: Resource) -> None:
        self._resources[resource.id] = resource

    def add_turnaround(self, observation: TurnaroundObservation) -> None:
        self._turnaround.append(observation)
