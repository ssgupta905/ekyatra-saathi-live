"""The network a journey runs through: labs, pharmacies, distributors, cabs, hotels.

Reference data an administrator maintains, like the hospital registry. An
organisation says what it does and where, never anything about a family. Which
one a journey uses is chosen by `orchestrator`, from this directory.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .affordability import CostTier


class OrgType(StrEnum):
    HOSPITAL = "hospital"
    LAB = "lab"
    PHARMACY = "pharmacy"
    MEDICINE_DISTRIBUTOR = "medicine_distributor"
    EQUIPMENT_DISTRIBUTOR = "equipment_distributor"
    SHOP = "shop"
    CAB = "cab"
    TRAVEL = "travel"
    HOTEL = "hotel"
    INSURER = "insurer"
    AMBULANCE = "ambulance"


class PartnerMode(StrEnum):
    #: Answers by itself, so a journey moves in a demonstration.
    SIMULATED = "simulated"
    #: Waits for a person at the organisation to answer.
    PEOPLE = "people"


class Organisation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    type: OrgType
    #: What it offers, in a few plain words: "MRI", "cold chain", "airport pickup".
    services: tuple[str, ...] = ()
    #: What it costs the family, as an order rather than an amount. Declared by
    #: whoever maintains the directory, never inferred: this project will not
    #: report a fare it was not given, and it will not invent a tier either.
    #: The default is `STANDARD` on purpose — an organisation nobody has looked
    #: at should never be mistaken for a cheap one and offered to a family who
    #: cannot afford to be wrong about it.
    cost_tier: CostTier = CostTier.STANDARD
    #: Districts or cities it serves. Empty means it is not tied to a place.
    districts: tuple[str, ...] = ()
    #: The hospitals it works with. Empty means any.
    hospital_ids: tuple[str, ...] = ()
    address: str = Field(default="", max_length=240)
    contact: str = Field(default="", max_length=120)
    hours: str = Field(default="", max_length=80)
    mode: PartnerMode = PartnerMode.SIMULATED
    #: For a simulated organisation: how it answers a request.
    answer: str = Field(default="ready", pattern="^(ready|cannot)$")
    delay_seconds: int = Field(default=30, ge=0, le=3600)
    #: Who to turn to when this one cannot.
    alternate_id: str | None = None
    #: Other organisations it is linked to: a distributor supplies a pharmacy.
    linked_ids: tuple[str, ...] = ()
    active: bool = True


#: Which organisation types answer which kind of need on a journey.
NEED_FOR_TYPE: dict[str, tuple[OrgType, ...]] = {
    "transport": (OrgType.CAB, OrgType.TRAVEL),
    "stay": (OrgType.HOTEL,),
    "medicine": (OrgType.PHARMACY,),
    "insurance": (OrgType.INSURER,),
    #: The hospital's own slot first; a diagnostic centre's when it has none.
    "slot": (OrgType.HOSPITAL, OrgType.LAB),
    "doctor": (OrgType.HOSPITAL,),
    "bed": (OrgType.HOSPITAL,),
}
