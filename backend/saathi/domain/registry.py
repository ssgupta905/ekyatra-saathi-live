"""The hospital network as a registry: hospitals, their treatment centres, and clinicians.

Reference data a hospital maintains, not facts about a family. Who works where,
which centres exist and what each can do. Nothing here is clinical: a
clinician's specialty is how a desk routes a question, not a statement about
any patient.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Hospital(_Record):
    id: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    #: The place the geo tool resolves, so journeys to it can be fetched.
    place: str = Field(min_length=1, max_length=80)
    timezone: str = "Asia/Kolkata"
    departments: tuple[str, ...] = ()
    active: bool = True


class NetworkCentre(_Record):
    """A place a step can happen, in one hospital's network."""

    id: str = Field(min_length=1, max_length=64)
    hospital_id: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    place: str = Field(min_length=1, max_length=80)
    #: "hub" or "day_care".
    kind: str = Field(default="day_care", pattern="^(hub|day_care)$")
    #: StepKind values this centre is equipped for.
    handles: tuple[str, ...] = ()
    active: bool = True


class Clinician(_Record):
    """A doctor or clinical staff member, whether or not they have a login."""

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    specialty: str = Field(default="", max_length=120)
    hospital_id: str = Field(min_length=1, max_length=32)
    department: str = Field(default="", max_length=80)
    #: The staff account this person signs in with, when they have one.
    username: str | None = None
    active: bool = True
