"""A registry store in dictionaries, for the demo and tests."""

from __future__ import annotations

from ...domain.registry import Clinician, Hospital, NetworkCentre


class MemoryRegistryStore:
    def __init__(self) -> None:
        self._hospitals: dict[str, Hospital] = {}
        self._centres: dict[str, NetworkCentre] = {}
        self._clinicians: dict[str, Clinician] = {}
        self._policies: dict[str, tuple[dict, int, str]] = {}

    def hospitals(self) -> tuple[Hospital, ...]:
        return tuple(self._hospitals.values())

    def save_hospital(self, hospital: Hospital) -> None:
        self._hospitals[hospital.id] = hospital

    def centres(self) -> tuple[NetworkCentre, ...]:
        return tuple(self._centres.values())

    def save_centre(self, centre: NetworkCentre) -> None:
        self._centres[centre.id] = centre

    def clinicians(self) -> tuple[Clinician, ...]:
        return tuple(self._clinicians.values())

    def save_clinician(self, clinician: Clinician) -> None:
        self._clinicians[clinician.id] = clinician

    def policy(self, hospital_id: str) -> tuple[dict, int, str] | None:
        return self._policies.get(hospital_id)

    def save_policy(self, hospital_id: str, policy: dict, saved_by: str) -> int:
        version = (self._policies.get(hospital_id, ({}, 0, ""))[1]) + 1
        self._policies[hospital_id] = (policy, version, saved_by)
        return version
