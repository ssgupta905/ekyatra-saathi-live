"""Somewhere to sleep near the hospital: asked, bargained for, and booked on a tap.

Three moves, each one its own call so each one can be seen:

1. **Quote.** When a visit needs a night away, the travel-and-stay agent asks
   the stay partner serving that hospital for a room and puts the price in the
   family's books as that partner's quote, then tells the family and asks
   whether to look for a better rate. It asks once; it never bargains unasked.
2. **Negotiate.** Only when the family says yes. Two rounds at most, under a
   cap, sharing dates, party size and "hospital visit" — see
   `money/negotiation.py`. The result replaces the quote; nothing is booked.
3. **Book.** Only on the family's tap. The room becomes a readiness item held
   by that partner, so the Console and the partner see it like any other need.

If the hospital caused the visit to move and the desk covered the change from
the welfare fund, the room is recorded as the hospital's to pay, and the
family is told it costs them nothing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import TYPE_CHECKING

from ..domain.directory import OrgType
from ..domain.enums import Channel, ReadinessKind, ReadinessStatus, SourceSystem
from ..domain.models import ReadinessItem
from ..domain.spends import CoveredBy, SpendCategory, SpendSource, SpendStatus
from ..language import guard
from ..language import stays as words
from ..money.journey import nights_for
from ..money.negotiation import SANDBOX_TERMS, Negotiation, PartnerTerms, negotiate
from .events import EventKind

if TYPE_CHECKING:
    from .runner import LiveRunner

logger = logging.getLogger(__name__)

#: Which kind of stay the agent asks first, in order. A room for two with a
#: patient rate beats a dharamshala bed only when the family is two; both beat a
#: hotel. The ordering is the family's budget order, cheapest that fits first.
TIER_ORDER = ("modest", "subsidised", "standard")


class StayError(ValueError):
    """There is no stay quote to act on, or it is not the family's to act on."""


def _tier(org) -> str:
    return getattr(getattr(org, "cost_tier", None), "value", "standard")


def stay_partner(runner: LiveRunner, patient):
    """The stay partner the agent asks for this family's hospital."""
    registry = getattr(runner.kharcha, "registry", None)
    if registry is None:
        return None
    hotels = [
        o
        for o in registry.organisations()
        if o.type is OrgType.HOTEL and (not o.hospital_ids or patient.hospital_id in o.hospital_ids)
    ]
    for tier in TIER_ORDER:
        for org in hotels:
            if _tier(org) == tier:
                return org
    return hotels[0] if hotels else None


def terms_for(org) -> PartnerTerms:
    return SANDBOX_TERMS.get(_tier(org), SANDBOX_TERMS["standard"])


def _party_size(runner: LiveRunner, patient_id: str) -> int:
    for request in reversed(runner.requests.get(patient_id, ())):
        companions = getattr(request.travel, "companions", None)
        if companions:
            return int(companions) + 1
    return 2


def _check_in(runner: LiveRunner, patient_id: str) -> date | None:
    today = runner.world.today
    days = sorted(
        s.scheduled_for
        for s in runner.world.steps_for(patient_id)
        if s.scheduled_for is not None and s.scheduled_for >= today
    )
    return days[0] if days else None


def _label(org) -> str:
    return f"{org.name} (sandbox)"


def _say(
    runner: LiveRunner, patient, kind: str, text: str, *, day: date | None, detail: dict
) -> bool:
    verdict = guard.check_question(text, dates_given=(day,) if day else ())
    if not verdict.allowed:
        runner.bus.publish(
            EventKind.GUARD_BLOCKED,
            runner.world.today.isoformat(),
            patient_id=patient.id,
            summary=f"Guard held a stay message to {patient.id}: {verdict.reason}",
            triggers=list(verdict.triggers),
        )
        return False
    runner._record_outbound(
        patient.id,
        kind=kind,
        body=text,
        language=patient.language.value,
        channel=Channel.WHATSAPP.value,
        detail=detail,
    )
    return True


def _tool(runner: LiveRunner, patient_id: str, tool: str, summary: str, **extra) -> None:
    runner.bus.publish(
        EventKind.TOOL_CALLED,
        runner.world.today.isoformat(),
        patient_id=patient_id,
        summary=summary,
        tool=tool,
        provider="sandbox stay partner",
        **extra,
    )


async def quote_stay(runner: LiveRunner, patient_id: str, *, tell_family: bool = True):
    """Ask the stay partner for a room for this family's next visit.

    Returns the quote, or None when no night away is needed or nobody serves
    this hospital — both ordinary answers, not errors. Idempotent per visit: a
    quote already open for this family is returned rather than asked again.
    """
    patient = runner.world.patient(patient_id)
    desk = runner.kharcha
    if patient is None or desk is None:
        return None
    org = stay_partner(runner, patient)
    check_in = _check_in(runner, patient_id)
    if org is None or check_in is None:
        return None
    n = nights_for(patient.home_distance_km or 0.0, runner.journey_hours(patient))
    if n <= 0:
        return None

    for entry in desk.store.entries(patient_id):
        if (
            entry.category is SpendCategory.STAY
            and entry.status is SpendStatus.QUOTED
            and (entry.source_ref or "").startswith(("stay-quote:", "stay-deal:"))
        ):
            return entry

    terms = terms_for(org)
    party = _party_size(runner, patient_id)
    covered = runner.welfare_cover.get(patient_id) is not None
    async with runner.working(
        "Finding somewhere to stay near the hospital",
        patient_id=patient_id,
        detail=f"{n} night(s) from {check_in:%d %b}, party of {party}",
    ):
        total = terms.list_nightly_paise * n
        _tool(
            runner,
            patient_id,
            "stay_partner.quote",
            f"{_label(org)}: a room for {n} night(s) from {check_in:%d %b}, ₹{total // 100:,}",
            shared={
                "check_in": check_in.isoformat(),
                "nights": n,
                "party_size": party,
                "purpose": "hospital visit",
            },
        )
        entry = desk.from_provider(
            patient_id,
            source=SpendSource.PROVIDER_QUOTE,
            source_ref=f"stay-quote:{patient_id}:{uuid.uuid4().hex[:8]}",
            amount_paise=total,
            category=SpendCategory.STAY,
            status=SpendStatus.QUOTED,
            party=_label(org),
            organisation_id=org.id,
            on=check_in,
            covered_by=CoveredBy.HOSPITAL if covered else CoveredBy.SELF,
        )
    runner.stay_deals[entry.id] = {
        "organisation_id": org.id,
        "nights": n,
        "party_size": party,
        "check_in": check_in.isoformat(),
        "list_nightly_paise": terms.list_nightly_paise,
        "negotiation": None,
    }
    runner.ledger.record_once(
        patient_id=patient_id,
        source=SourceSystem.PARTNER,
        source_record_id=entry.id,
        claim=f"stay quoted by {_label(org)}: {n} night(s), ₹{total // 100:,}",
        metadata={
            "organisation_id": org.id,
            "nights": n,
            "shared": ["dates", "party size", "purpose"],
        },
    )
    if tell_family:
        _say(
            runner,
            patient,
            "stay_offer",
            words.stay_offer(
                language=patient.language,
                partner=org.name,
                n_nights=n,
                check_in=check_in,
                total_paise=total,
            ),
            day=check_in,
            detail={"entry_id": entry.id, "can_negotiate": True, "sandbox": True},
        )
    return entry


def _deal_for(runner: LiveRunner, patient_id: str, entry_id: str):
    desk = runner.kharcha
    if desk is None:
        raise StayError("no books are kept here")
    entry = desk.store.get(patient_id, entry_id)
    if (
        entry is None
        or entry.category is not SpendCategory.STAY
        or entry.status is not SpendStatus.QUOTED
    ):
        raise StayError("there is no stay quote waiting with that id")
    org = (
        next((o for o in desk.registry.organisations() if o.id == entry.organisation_id), None)
        if desk.registry
        else None
    )
    if org is None:
        raise StayError("the partner that quoted this is no longer in the directory")
    meta = runner.stay_deals.get(entry_id)
    if meta is None:
        # A restart forgot the working; rebuild it from the quote itself.
        terms = terms_for(org)
        nights = max(1, round(entry.amount_paise / terms.list_nightly_paise))
        meta = {
            "organisation_id": org.id,
            "nights": nights,
            "party_size": _party_size(runner, patient_id),
            "check_in": (entry.on or runner.world.today).isoformat(),
            "list_nightly_paise": entry.amount_paise // nights,
            "negotiation": None,
        }
        runner.stay_deals[entry_id] = meta
    return desk, entry, org, meta


async def negotiate_stay(
    runner: LiveRunner, patient_id: str, entry_id: str
) -> tuple[Negotiation, object]:
    """The family said "yes, ask". Bargain, then put the result to them."""
    patient = runner.world.patient(patient_id)
    if patient is None:
        raise StayError("unknown patient")
    desk, entry, org, meta = _deal_for(runner, patient_id, entry_id)
    if (entry.source_ref or "").startswith("stay-deal:") or meta.get("negotiation"):
        raise StayError("this rate was already negotiated; it can be booked")

    terms = terms_for(org)
    check_in = date.fromisoformat(meta["check_in"])
    async with runner.working(
        "Asking the rest house for a patient rate",
        patient_id=patient_id,
        detail=(
            f"{_label(org)}, at most 2 rounds, "
            f"never above ₹{terms.list_nightly_paise // 100:,}/night"
        ),
    ):
        deal = negotiate(
            terms,
            partner=_label(org),
            nights=meta["nights"],
            party_size=meta["party_size"],
            check_in=check_in,
        )
        for offer in deal.offers:
            who = "Saathi asked" if offer.by == "saathi" else f"{org.name} replied"
            _tool(
                runner,
                patient_id,
                "stay_partner.counter_offer",
                f"Round {offer.round}: {who} ₹{offer.nightly_paise // 100:,}/night — {offer.note}",
                round=offer.round,
                by=offer.by,
                nightly_paise=offer.nightly_paise,
                shared=deal.shared,
            )

    meta["negotiation"] = deal.to_json()
    runner.ledger.record_once(
        patient_id=patient_id,
        source=SourceSystem.PARTNER,
        source_record_id=f"negotiation:{entry.id}",
        claim=(
            f"stay negotiated with {_label(org)} in {deal.rounds} round(s): "
            + (
                f"₹{deal.agreed_nightly_paise // 100:,}/night agreed"
                if deal.agreed_nightly_paise
                else "no better rate"
            )
        ),
        metadata={
            "cap_nightly_paise": deal.cap_nightly_paise,
            "shared": deal.shared,
            "offers": [o.to_json() for o in deal.offers],
        },
    )

    result = entry
    if (
        deal.agreed_nightly_paise is not None
        and deal.agreed_nightly_paise < deal.list_nightly_paise
    ):
        # The first price is superseded, not withdrawn by the family, so it is
        # voided in place rather than through the family's own void action.
        gone = entry.model_copy(update={"status": SpendStatus.VOID})
        desk.store.save(gone)
        result = desk.from_provider(
            patient_id,
            source=SpendSource.PROVIDER_QUOTE,
            source_ref=f"stay-deal:{patient_id}:{uuid.uuid4().hex[:8]}",
            amount_paise=deal.total_paise,
            category=SpendCategory.STAY,
            status=SpendStatus.QUOTED,
            party=_label(org),
            organisation_id=org.id,
            on=check_in,
            covered_by=entry.covered_by,
        )
        runner.stay_deals[result.id] = {**meta, "negotiation": deal.to_json()}
        text = words.stay_agreed(
            language=patient.language,
            partner=org.name,
            n_nights=deal.nights,
            total_paise=deal.total_paise,
            nightly_paise=deal.agreed_nightly_paise,
            listed_paise=deal.list_nightly_paise,
            includes=deal.includes,
        )
    else:
        text = words.stay_no_better(
            language=patient.language,
            partner=org.name,
            n_nights=deal.nights,
            total_paise=entry.amount_paise,
        )
    _say(
        runner,
        patient,
        "stay_deal",
        text,
        day=None,
        detail={"entry_id": result.id, "negotiation": deal.to_json(), "sandbox": True},
    )
    runner._bump("stays_negotiated")
    return deal, result


async def book_stay(runner: LiveRunner, patient_id: str, entry_id: str) -> ReadinessItem:
    """The family's tap. The room becomes a need the partner holds."""
    patient = runner.world.patient(patient_id)
    if patient is None:
        raise StayError("unknown patient")
    desk, entry, org, meta = _deal_for(runner, patient_id, entry_id)
    check_in = date.fromisoformat(meta["check_in"])
    hospital_pays = entry.covered_by is CoveredBy.HOSPITAL
    item = ReadinessItem(
        id=f"stay-{patient_id}",
        patient_id=patient_id,
        kind=ReadinessKind.STAY,
        party=org.name,
        status=ReadinessStatus.READY,
        ready_by=check_in,
        detail=(
            f"Room booked: {meta['nights']} night(s) from {check_in:%d %b}, "
            f"₹{entry.amount_paise // 100:,}"
            + (
                " — paid by the hospital welfare fund"
                if hospital_pays
                else " — family pays at the desk"
            )
        ),
        source=SourceSystem.PARTNER,
        partner_id=org.id,
    )
    async with runner._lock:
        runner.world.set_readiness_item(item)
    # The offer becomes a booking: from here it is money the family has
    # committed to, and their books count it as booked.
    ref = (entry.source_ref or "").split(":", 1)[-1]
    entry = desk.store.save(entry.model_copy(update={"source_ref": f"stay-booked:{ref}"}))
    _tool(
        runner,
        patient_id,
        "stay_partner.book",
        f"{_label(org)} confirmed the room for {meta['nights']} night(s) from {check_in:%d %b}",
    )
    runner.ledger.record_once(
        patient_id=patient_id,
        source=SourceSystem.CAREGIVER_REPLY,
        source_record_id=f"booked:{entry.id}",
        claim=f"family booked the stay at {_label(org)} for ₹{entry.amount_paise // 100:,}",
        metadata={"covered_by": entry.covered_by.value},
    )
    _say(
        runner,
        patient,
        "stay_booked",
        words.stay_booked(
            language=patient.language,
            partner=org.name,
            n_nights=meta["nights"],
            check_in=check_in,
            total_paise=entry.amount_paise,
            hospital_pays=hospital_pays,
        ),
        day=check_in,
        detail={"entry_id": entry.id},
    )
    await runner.plan_patient(patient_id, allow_render=True)
    return item


def offers_for(runner: LiveRunner, patient_id: str) -> list[dict]:
    """Every stay quote waiting on the family, with the working behind it."""
    desk = runner.kharcha
    if desk is None:
        return []
    rows = []
    for entry in desk.store.entries(patient_id):
        if entry.category is not SpendCategory.STAY or entry.status is not SpendStatus.QUOTED:
            continue
        ref = entry.source_ref or ""
        if not ref.startswith(("stay-quote:", "stay-deal:", "stay-booked:")):
            continue
        meta = runner.stay_deals.get(entry.id)
        if meta is None:
            try:  # a restart forgot the working; rebuild it from the quote
                meta = _deal_for(runner, patient_id, entry.id)[3]
            except StayError:
                meta = {}
        booked = ref.startswith("stay-booked:")
        rows.append(
            {
                "entry_id": entry.id,
                "partner": entry.party,
                "amount_paise": entry.amount_paise,
                "nights": meta.get("nights"),
                "check_in": meta.get("check_in"),
                "negotiated": ref.startswith("stay-deal:") or bool(meta.get("negotiation")),
                "can_negotiate": ref.startswith("stay-quote:") and not meta.get("negotiation"),
                "hospital_pays": entry.covered_by is CoveredBy.HOSPITAL,
                "booked": booked,
                "negotiation": meta.get("negotiation"),
                "sandbox": True,
            }
        )
    return rows
