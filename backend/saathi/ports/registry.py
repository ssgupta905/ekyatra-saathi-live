"""Where the hospital network's reference data lives.

Hospitals, their centres, clinicians, and each hospital's rules. Memory for the
demo, SQLAlchemy for real records, like `RecordStore`.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.registry import Clinician, Hospital, NetworkCentre


class RegistryStore(Protocol):
    def hospitals(self) -> tuple[Hospital, ...]: ...

    def save_hospital(self, hospital: Hospital) -> None: ...

    def centres(self) -> tuple[NetworkCentre, ...]: ...

    def save_centre(self, centre: NetworkCentre) -> None: ...

    def clinicians(self) -> tuple[Clinician, ...]: ...

    def save_clinician(self, clinician: Clinician) -> None: ...

    def policy(self, hospital_id: str) -> tuple[dict, int, str] | None:
        """The hospital's rules as stored (a `HospitalPolicy` dict), its version, who saved it."""
        ...

    def save_policy(self, hospital_id: str, policy: dict, saved_by: str) -> int:
        """Store a new version; returns its number."""
        ...
