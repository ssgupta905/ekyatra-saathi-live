"""The registry over SQLAlchemy. Same database as the records; migrated with them."""

from __future__ import annotations

import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from ...db.tables import CentreRow, ClinicianRow, HospitalPolicyRow, HospitalRow
from ...domain.registry import Clinician, Hospital, NetworkCentre


class SqlRegistryStore:
    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def close(self) -> None:
        self._engine.dispose()

    # ---------------- hospitals ----------------

    def hospitals(self) -> tuple[Hospital, ...]:
        with self._sessions() as db:
            return tuple(
                Hospital(
                    id=r.id, name=r.name, place=r.place, timezone=r.timezone,
                    departments=tuple(json.loads(r.departments_json or "[]")), active=r.active,
                )  # fmt: skip
                for r in db.scalars(select(HospitalRow).order_by(HospitalRow.id))
            )

    def save_hospital(self, hospital: Hospital) -> None:
        with self._sessions.begin() as db:
            row = db.get(HospitalRow, hospital.id) or HospitalRow(id=hospital.id)
            row.name, row.place, row.timezone = hospital.name, hospital.place, hospital.timezone
            row.departments_json = json.dumps(list(hospital.departments))
            row.active = hospital.active
            db.merge(row)

    # ---------------- centres ----------------

    def centres(self) -> tuple[NetworkCentre, ...]:
        with self._sessions() as db:
            return tuple(
                NetworkCentre(
                    id=r.id, hospital_id=r.hospital_id, name=r.name, place=r.place, kind=r.kind,
                    handles=tuple(json.loads(r.handles_json or "[]")), active=r.active,
                )  # fmt: skip
                for r in db.scalars(select(CentreRow).order_by(CentreRow.id))
            )

    def save_centre(self, centre: NetworkCentre) -> None:
        with self._sessions.begin() as db:
            row = db.get(CentreRow, centre.id) or CentreRow(id=centre.id)
            row.hospital_id, row.name, row.place = centre.hospital_id, centre.name, centre.place
            row.kind, row.active = centre.kind, centre.active
            row.handles_json = json.dumps(list(centre.handles))
            db.merge(row)

    # ---------------- clinicians ----------------

    def clinicians(self) -> tuple[Clinician, ...]:
        with self._sessions() as db:
            return tuple(
                Clinician(
                    id=r.id, name=r.name, specialty=r.specialty, hospital_id=r.hospital_id,
                    department=r.department, username=r.username, active=r.active,
                )  # fmt: skip
                for r in db.scalars(select(ClinicianRow).order_by(ClinicianRow.name))
            )

    def save_clinician(self, clinician: Clinician) -> None:
        with self._sessions.begin() as db:
            row = db.get(ClinicianRow, clinician.id) or ClinicianRow(id=clinician.id)
            row.name, row.specialty = clinician.name, clinician.specialty
            row.hospital_id, row.department = clinician.hospital_id, clinician.department
            row.username, row.active = clinician.username, clinician.active
            db.merge(row)

    # ---------------- rules ----------------

    def policy(self, hospital_id: str) -> tuple[dict, int, str] | None:
        with self._sessions() as db:
            row = db.scalar(
                select(HospitalPolicyRow)
                .where(HospitalPolicyRow.hospital_id == hospital_id)
                .order_by(HospitalPolicyRow.version.desc())
                .limit(1)
            )
            return (json.loads(row.policy_json), row.version, row.saved_by) if row else None

    def save_policy(self, hospital_id: str, policy: dict, saved_by: str) -> int:
        with self._sessions.begin() as db:
            latest = db.scalar(
                select(HospitalPolicyRow.version)
                .where(HospitalPolicyRow.hospital_id == hospital_id)
                .order_by(HospitalPolicyRow.version.desc())
                .limit(1)
            )
            version = (latest or 0) + 1
            db.add(
                HospitalPolicyRow(
                    hospital_id=hospital_id,
                    version=version,
                    policy_json=json.dumps(policy, sort_keys=True),
                    saved_by=saved_by,
                )
            )
            return version
