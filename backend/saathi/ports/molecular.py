"""Where the molecular register is kept. Read by doctors, nobody else.

Deliberately the narrowest port in this codebase. There is no search, no
query by test kind, no aggregate: everything here is "this patient's reports",
because the only question the register answers is the one a doctor at the next
centre asks before ordering a repeat.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.molecular import MolecularReport


class MolecularRegister(Protocol):
    def save(self, report: MolecularReport) -> MolecularReport: ...

    def get(self, patient_id: str, report_id: str) -> MolecularReport | None: ...

    def for_patient(self, patient_id: str) -> tuple[MolecularReport, ...]:
        """Oldest first, because it is read as a history."""
        ...

    def forget(self, patient_id: str) -> int:
        """Everything for one patient, for a consent withdrawal.

        Returns how many rows went, so the deletion can be written into the
        ledger as a fact rather than an intention.

        Withdrawal has to actually remove it. A register that kept the rows
        and set a flag would be keeping what somebody asked it to stop
        keeping.
        """
        ...
