"""The register, in memory. What the demo and the tests run on."""

from __future__ import annotations

from collections import defaultdict

from ...domain.molecular import MolecularReport


class InMemoryMolecularRegister:
    def __init__(self) -> None:
        self._by_patient: dict[str, list[MolecularReport]] = defaultdict(list)

    def save(self, report: MolecularReport) -> MolecularReport:
        rows = self._by_patient[report.patient_id]
        for i, existing in enumerate(rows):
            if existing.id == report.id:
                rows[i] = report
                return report
        rows.append(report)
        return report

    def get(self, patient_id: str, report_id: str) -> MolecularReport | None:
        return next(
            (r for r in self._by_patient.get(patient_id, []) if r.id == report_id), None
        )

    def for_patient(self, patient_id: str) -> tuple[MolecularReport, ...]:
        # By when the test was *taken*, not when its report came back. A
        # panel ordered in March and reported three weeks later happened
        # before a FISH ordered the day before that report landed, and a
        # doctor reading the list is reconstructing what was done, in order.
        # An undated report falls back to when somebody typed it in.
        rows = sorted(
            self._by_patient.get(patient_id, []),
            key=lambda r: (r.ordered_on or r.reported_on or r.recorded_at.date()),
        )
        return tuple(rows)

    def forget(self, patient_id: str) -> int:
        return len(self._by_patient.pop(patient_id, ()))
