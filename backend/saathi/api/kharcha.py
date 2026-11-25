"""Kharcha: a family's own view of what the journey is costing them.

Family-only (`FamilyOnly`). Nothing here is shown to staff, and every amount
returned carries where it came from: the family's own words, a provider's
quote or payment, or arithmetic over those with the entries it was worked
from. See `live/kharcha.py` for the desk behind it.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.spends import MOST_ONE_SPEND_PAISE, SpendCategory, SpendStatus
from ..live.kharcha import NotReadable
from ..live.network import NotBookable
from ..live.payments import NotPayable
from ..ports.network import NetworkUnavailable
from ..ports.payments import PaymentUnavailable
from .access import FamilyOnly
from .deps import ContainerDep

router = APIRouter(tags=["kharcha"])


def _desk(state, patient_id: str):
    if state.world.patient(patient_id) is None:
        raise HTTPException(404, "unknown patient")
    desk = state.runner.kharcha
    if desk is None:
        raise HTTPException(409, "no books are kept here")
    return desk


def _entry(e) -> dict:
    return e.model_dump(mode="json")


@router.get("/patients/{patient_id}/kharcha", dependencies=[FamilyOnly])
async def kharcha(state: ContainerDep, patient_id: str) -> dict:
    """This month and next: spent, booked, still to come, and what might help."""
    desk = _desk(state, patient_id)
    this_month, following = desk.months(patient_id)
    limit = desk.store.limit(patient_id)
    entries = desk.store.entries(patient_id)
    return {
        "patient_id": patient_id,
        "months": [this_month.model_dump(mode="json"), following.model_dump(mode="json")],
        "limit": limit.model_dump(mode="json") if limit else None,
        "over_limit": desk.over_limit(patient_id, this_month),
        "nudges": [n.model_dump(mode="json") for n in desk.suggestions(patient_id, this_month)],
        #: Waiting for the family to say "yes, that's right".
        "to_confirm": [_entry(e) for e in entries if e.status is SpendStatus.PROPOSED],
        #: A seller's firm price for a ride, waiting for the family's Book.
        "bookable": state.runner.network.bookable(patient_id) if state.runner.network else [],
        #: Vendors' quotes the family can pay through the vendor's own link.
        "payable": [
            _entry(e)
            for e in entries
            if state.runner.payments is not None and state.runner.payments.payable(e)
        ],
    }


@router.get("/patients/{patient_id}/kharcha/entries", dependencies=[FamilyOnly])
async def entries(state: ContainerDep, patient_id: str, month: date | None = None) -> dict:
    desk = _desk(state, patient_id)
    found = desk.store.entries(patient_id)
    if month is not None:
        found = tuple(e for e in found if (e.on.year, e.on.month) == (month.year, month.month))
    return {"entries": [_entry(e) for e in found]}


class SpendIn(BaseModel):
    """What the family said or typed. Either words, or an amount with a kind, or both."""

    text: str = Field(default="", max_length=400)
    #: Whole rupees, as a family types them.
    amount: int | None = Field(default=None, ge=1, le=MOST_ONE_SPEND_PAISE // 100)
    category: SpendCategory | None = None
    on: date | None = None


@router.post("/patients/{patient_id}/kharcha/entries", dependencies=[FamilyOnly])
async def add_entry(state: ContainerDep, patient_id: str, body: SpendIn) -> dict:
    """Read it into a proposed entry. It counts once the family confirms it."""
    desk = _desk(state, patient_id)
    try:
        entry = desk.note_from_family(
            patient_id,
            text=body.text,
            amount_paise=body.amount * 100 if body.amount else None,
            category=body.category,
            on=body.on,
        )
    except NotReadable as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"entry": _entry(entry)}


@router.post("/patients/{patient_id}/kharcha/entries/{entry_id}/confirm", dependencies=[FamilyOnly])
async def confirm_entry(state: ContainerDep, patient_id: str, entry_id: str) -> dict:
    entry = _desk(state, patient_id).confirm(patient_id, entry_id)
    if entry is None:
        raise HTTPException(404, "no such entry")
    return {"entry": _entry(entry)}


@router.post("/patients/{patient_id}/kharcha/entries/{entry_id}/void", dependencies=[FamilyOnly])
async def void_entry(state: ContainerDep, patient_id: str, entry_id: str) -> dict:
    entry = _desk(state, patient_id).void(patient_id, entry_id)
    if entry is None:
        raise HTTPException(404, "no such entry")
    return {"entry": _entry(entry)}


class LimitIn(BaseModel):
    #: Whole rupees a month, as the family said it.
    amount: int = Field(ge=1, le=MOST_ONE_SPEND_PAISE // 100)
    said: str = Field(default="", max_length=400)


@router.put("/patients/{patient_id}/kharcha/limit", dependencies=[FamilyOnly])
async def set_limit(state: ContainerDep, patient_id: str, body: LimitIn) -> dict:
    """What the family says they can manage in a month, kept with their words."""
    said = body.said.strip() or f"{body.amount} a month"
    limit = _desk(state, patient_id).set_limit(patient_id, body.amount * 100, said)
    return {"limit": limit.model_dump(mode="json")}


# ---------------------------------------------------------------- the family's taps


@router.post("/patients/{patient_id}/kharcha/entries/{entry_id}/pay", dependencies=[FamilyOnly])
async def pay(state: ContainerDep, patient_id: str, entry_id: str) -> dict:
    """The vendor's own pay link for this quote. The money goes to the vendor, not Saathi."""
    _desk(state, patient_id)
    payments = state.runner.payments
    if payments is None:
        raise HTTPException(409, "no vendor here takes payment by link")
    try:
        entry = payments.pay_link(patient_id, entry_id)
    except NotPayable as exc:
        raise HTTPException(409, str(exc)) from exc
    except PaymentUnavailable as exc:
        raise HTTPException(
            503, "the vendor's payment page could not be reached; try again"
        ) from exc
    return {"entry": _entry(entry), "pay_url": entry.pay_url}


class BookIn(BaseModel):
    #: The family agrees the seller may have their first name and phone, so a
    #: driver can find them. Without it nothing is booked.
    share_contact: bool = False


@router.post("/patients/{patient_id}/book/{item_id}", dependencies=[FamilyOnly])
async def book(state: ContainerDep, patient_id: str, item_id: str, body: BookIn) -> dict:
    """The family's tap: book the ride the seller quoted. Nobody else's tap does this."""
    _desk(state, patient_id)
    network = state.runner.network
    if network is None:
        raise HTTPException(409, "nothing here is booked over a network")
    if not body.share_contact:
        raise HTTPException(409, "say yes to sharing your first name and phone with the driver")
    try:
        item = await network.book(patient_id, item_id)
    except NotBookable as exc:
        raise HTTPException(409, str(exc)) from exc
    except NetworkUnavailable as exc:
        raise HTTPException(503, "could not reach the cab network; nothing was booked") from exc
    await state.runner.plan_patient(patient_id, allow_render=True)
    return {"item": item.model_dump(mode="json")}
