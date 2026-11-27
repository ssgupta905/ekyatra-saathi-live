"""What a cab firm, a hotel desk or a pharmacy sees, and the one thing it does.

A partner is not staff. It signs in with a password like staff do, and that is
where the resemblance ends: it sees the jobs its own organisation has been
asked to do and nothing else — no families, no care steps, no plan, no other
organisation's work. `Role.PARTNER` is deliberately outside `STAFF_ROLES`, so
every endpoint guarded by `AnyStaff` already refuses it without being told to.

A job carries the least that lets someone do it: a first name, the district to
collect from, the day when the plan actually promises one, and which need it
is. Contact details are not in that list unless the family has agreed to share
them for coordinating their care — and when they have not, the job says so
plainly rather than leaving a driver to wonder.

Three answers, because three is what a vendor actually gives: *accepted* (we
have it), *ready* (it is arranged) and *cannot* (find someone else). The last
one is what drives a journey into REPLAN, where a person decides what happens
next — which is the same path a simulated organisation takes when it refuses.

THE NETWORK SIDE

Four more things, all about the vendor's own business and none about anybody's
care.

*Applying.* `POST /partner/apply` is the one route here with no sign-in, and it
creates nothing that can be routed work: an application is an `Organisation`
with `active` false, which every selection rule in this system already skips
without being told to. Somebody at the hospital then turns it on, or declines
it with a reason. There is no self-approval, because a network anyone can join
unreviewed is a network a family cannot be sent into.

*Rates.* A vendor states its own prices. Saathi does not negotiate them,
discount them, or average them into an estimate it then attributes to the
vendor — the same line `money/rates.py` already draws between a figure
somebody gave us and one we worked out.

*Standing.* Counted from what actually happened: asked, answered, could not,
left past the time it was promised by. No stars and no score, because a score
is an opinion wearing a number's clothes, and the counts are what a desk
deciding whom to call next would want anyway.

*Earnings.* The vendor's own quotes, and Saathi's capped share of them. The
share comes off the vendor's side: a family is told the vendor's price and pays
the vendor's price, and `tests/test_vendor_network.py` holds that to be true
rather than asking anyone to believe it.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.consent import ConsentPurpose
from ..domain.directory import MOST_COMMISSION_PCT, Organisation, OrgType, PartnerMode, VendorRate
from ..domain.enums import ReadinessStatus, Role, SourceSystem
from ..domain.models import ReadinessItem
from ..domain.spends import MOST_ONE_SPEND_PAISE, SpendSource, SpendStatus
from .access import AdminOnly, AnyStaff, PrincipalDep, require
from .deps import ContainerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/partner", tags=["partner"])

PartnerOnly = require(Role.PARTNER)

#: What a partner is told about the family. Nothing clinical, and no more of
#: the name than it takes to greet someone at a door.
_ANSWERS = {
    "accepted": ReadinessStatus.PENDING,
    "ready": ReadinessStatus.READY,
    "cannot": ReadinessStatus.BLOCKED,
}


class Answer(BaseModel):
    answer: Literal["accepted", "ready", "cannot"]
    #: Why not, in the vendor's own words. Asked for on "cannot" because a
    #: navigator about to book someone else needs to know what went wrong.
    reason: str = Field(default="", max_length=200)
    #: The vendor's own price, in whole rupees, for a ride, a stay or pharmacy
    #: items. Goes into the family's books as this vendor's quote — the only way
    #: a figure for this job may ever be shown to them.
    quote_inr: int | None = Field(default=None, ge=1, le=MOST_ONE_SPEND_PAISE // 100)


def _organisation(container, principal) -> str:
    org = getattr(principal, "organisation_id", None)
    if not org:
        # An account that answers for nobody must see nothing. Failing closed
        # here is the difference between "no jobs" and "everybody's jobs".
        raise HTTPException(403, "this account is not linked to an organisation")
    return org


def _may_share_contact(container, patient) -> bool:
    """Has this family agreed to their details being shared to arrange care?"""
    registry = getattr(container, "consent", None)
    if registry is None or not patient.abha_number:
        return False
    try:
        return bool(
            registry.active_grants(patient.abha_number, ConsentPurpose.CARE_COORDINATION)
        )
    except Exception:  # noqa: BLE001 - a consent lookup must never leak details
        logger.exception("consent lookup failed; treating as no permission")
        return False


def _job(container, patient_id: str, item: ReadinessItem) -> dict | None:
    patient = container.world.patient(patient_id)
    if patient is None:
        return None
    run = container.runner.plans.get(patient_id)
    plan = run.plan if run else None
    shareable = _may_share_contact(container, patient)
    # A first name only. A driver needs to know who to greet, not who is ill.
    first = (patient.name or "").split(" ")[0]
    return {
        "item_id": item.id,
        "need": item.kind.value,
        "status": item.status.value,
        "detail": item.detail,
        "family": {
            "first_name": first or "the family",
            "district": patient.home_district,
            # Promised dates only. A partner told "Thursday" when the family
            # has not been told anything will arrange a car nobody comes for.
            "on": plan.travel_on.isoformat() if plan and plan.travel_on else None,
            "contact": patient.caregiver_phone if shareable else None,
            "contact_withheld": not shareable,
        },
    }


@router.get("/jobs", dependencies=[PartnerOnly])
async def jobs(container: ContainerDep, principal: PrincipalDep) -> dict:
    """Every job this organisation has been asked to do."""
    organisation = _organisation(container, principal)
    org = next(
        (o for o in container.registry.organisations() if o.id == organisation), None
    )
    open_jobs = []
    for patient in container.world.patients():
        for item in container.world.readiness_for(patient.id):
            if item.partner_id != organisation:
                continue
            job = _job(container, patient.id, item)
            if job is not None:
                open_jobs.append(job)
    # Waiting first: those are the ones somebody is expecting an answer to.
    open_jobs.sort(key=lambda j: (j["status"] != "pending", j["item_id"]))
    return {
        "organisation": {"id": organisation, "name": org.name if org else organisation},
        "jobs": open_jobs,
    }


@router.post("/jobs/{item_id}", dependencies=[PartnerOnly])
async def answer(
    container: ContainerDep,
    principal: PrincipalDep,
    item_id: str,
    body: Annotated[Answer, ...],
) -> dict:
    """The vendor's own answer. Re-plans the family it belongs to."""
    organisation = _organisation(container, principal)
    found: tuple[str, ReadinessItem] | None = None
    for patient in container.world.patients():
        for item in container.world.readiness_for(patient.id):
            if item.id == item_id:
                found = (patient.id, item)
                break
        if found:
            break
    if found is None:
        raise HTTPException(404, "no such job")
    patient_id, item = found
    if item.partner_id != organisation:
        # Not "forbidden": a partner should not be able to learn that a job
        # exists for somebody else by the shape of the refusal.
        raise HTTPException(404, "no such job")

    if body.answer == "cannot" and not body.reason.strip():
        raise HTTPException(422, "say what went wrong, so someone can book another")

    status = _ANSWERS[body.answer]
    detail = {
        "accepted": f"{principal.name} has it",
        "ready": f"confirmed by {principal.name}",
        "cannot": f"{principal.name} cannot: {body.reason.strip()}",
    }[body.answer]
    updated = container.world.set_readiness_item(
        item.model_copy(
            update={"status": status, "detail": detail, "due_at": None, "answer_by": None}
        )
    )
    _record_quote(container, patient_id, item, body, principal.name)
    await container.runner.plan_patient(patient_id, allow_render=True)
    return {"item_id": updated.id, "status": updated.status.value, "detail": updated.detail}


def _record_quote(container, patient_id: str, item: ReadinessItem, body: Answer, by: str) -> None:
    """A vendor's price for something the family pays for, kept as that vendor's quote."""
    from ..live.kharcha import CATEGORY_FOR_NEED

    desk = container.runner.kharcha
    category = CATEGORY_FOR_NEED.get(item.kind)
    if desk is None or body.quote_inr is None or body.answer == "cannot" or category is None:
        return
    desk.from_provider(
        patient_id,
        source=SpendSource.PROVIDER_QUOTE,
        source_ref=f"partner-quote:{item.id}:{item.partner_id}",
        amount_paise=body.quote_inr * 100,
        category=category,
        status=SpendStatus.QUOTED,
        party=by,
        organisation_id=item.partner_id,
    )


# ======================================================================
# The network: applying, rates, standing, earnings
# ======================================================================


def _registry(container):
    store = getattr(container, "registry", None)
    if store is None:
        raise HTTPException(503, "no directory is configured")
    return store


def _own(container, principal) -> Organisation:
    """The one organisation this account answers for."""
    organisation = _organisation(container, principal)
    org = next((o for o in _registry(container).organisations() if o.id == organisation), None)
    if org is None:
        raise HTTPException(404, "this account's organisation is no longer in the directory")
    return org


#: How many applications may be waiting at once.
#:
#: `POST /partner/apply` needs no sign-in, and it writes a row. Without a bound
#: somebody could grow the directory until the review queue is unreadable and
#: a real vendor's application is lost in it — not a breach, just a denial of
#: the thing this route exists for. A ceiling on the *queue* rather than on
#: requests per minute, because the queue is what a reviewer has to get
#: through, and it drains as decisions are made.
MOST_WAITING_APPLICATIONS = 50


class RateIn(BaseModel):
    service: str = Field(min_length=1, max_length=120)
    unit: str = Field(default="per trip", max_length=40)
    amount_inr: int = Field(ge=1, le=10_00_000)
    note: str = Field(default="", max_length=200)


class Application(BaseModel):
    """What a vendor says about itself when it asks to join.

    No commission here, and no `active`: terms are agreed with a person, and an
    applicant does not get to decide whether it is in the network.
    """

    #: Chosen by the applicant, so the account it will sign in with can be
    #: created against something stable. Checked for collisions.
    id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=160)
    type: OrgType
    contact: str = Field(min_length=4, max_length=120)
    districts: tuple[str, ...] = Field(default=(), max_length=40)
    services: tuple[str, ...] = Field(default=(), max_length=20)
    address: str = Field(default="", max_length=240)
    hours: str = Field(default="", max_length=80)
    rate_card: tuple[RateIn, ...] = Field(default=(), max_length=40)
    note: str = Field(default="", max_length=600)


@router.post("/apply", status_code=201)
async def apply(container: ContainerDep, body: Application) -> dict:
    """A vendor asking to join. The only route here that needs no sign-in.

    It creates an organisation that is switched off, which is what makes this
    safe to leave open: nothing selects an inactive organisation, so an
    application cannot be given work, cannot be shown to a family, and cannot
    see one. A person at the hospital decides.
    """
    store = _registry(container)
    known = store.organisations()
    if any(o.id == body.id for o in known):
        # Said plainly. A vendor retyping its name needs to know the name is
        # taken, and an id already in a public directory is not a secret.
        raise HTTPException(409, f"{body.id} is already taken; choose another short name")
    if sum(1 for o in known if o.awaiting_review) >= MOST_WAITING_APPLICATIONS:
        raise HTTPException(
            429,
            "there are already more applications waiting than anyone can read. "
            "Ring the hospital — this is a queue, not a refusal.",
        )

    applicant = Organisation(
        id=body.id,
        name=body.name.strip(),
        type=body.type,
        services=tuple(s.strip() for s in body.services if s.strip()),
        districts=tuple(d.strip() for d in body.districts if d.strip()),
        address=body.address.strip(),
        contact=body.contact.strip(),
        hours=body.hours.strip(),
        # A vendor that applied is answered by its own people, not simulated.
        mode=PartnerMode.PEOPLE,
        active=False,
        rate_card=tuple(VendorRate(**r.model_dump()) for r in body.rate_card),
        applied_on=container.clock.today(),
        applicant_note=body.note.strip(),
    )
    store.save_organisation(applicant)
    container.ledger.record(
        patient_id="",
        source=SourceSystem.PARTNER,
        source_record_id=f"vendor-application/{applicant.id}",
        claim=f"{applicant.type.value} {applicant.name} applied to join the network",
        metadata={"districts": list(applicant.districts), "rates": len(applicant.rate_card)},
    )
    return {
        "id": applicant.id,
        "status": "awaiting_review",
        "what_happens_next": (
            "Somebody at the hospital reviews this. Nothing is sent to you, and "
            "no work reaches you, until they do."
        ),
    }


@router.get("/me", dependencies=[PartnerOnly])
async def me(container: ContainerDep, principal: PrincipalDep) -> dict:
    """The vendor's own record: what it offers, what it charges, how it stands."""
    org = _own(container, principal)
    return {
        "id": org.id,
        "name": org.name,
        "type": org.type.value,
        "services": list(org.services),
        "districts": list(org.districts),
        "contact": org.contact,
        "hours": org.hours,
        "active": org.active,
        "applied_on": org.applied_on.isoformat() if org.applied_on else None,
        "approved_on": org.approved_on.isoformat() if org.approved_on else None,
        "rate_card": [r.model_dump(mode="json") for r in org.rate_card],
        "commission_pct": org.commission_pct,
        "commission_cap_pct": MOST_COMMISSION_PCT,
        "commission_note": (
            "Taken off our side of your price, never added to the family's. "
            "They are told your rate and they pay your rate."
        ),
        "standing": _standing(container, org.id),
    }


@router.put("/rates", dependencies=[PartnerOnly])
async def set_rates(
    container: ContainerDep,
    principal: PrincipalDep,
    body: Annotated[tuple[RateIn, ...], Field(max_length=40)],
) -> dict:
    """The vendor's own price list, replaced wholesale.

    Wholesale rather than line by line, because a half-updated price list is
    worse than an old one: somebody quotes from the line that did not change.
    """
    org = _own(container, principal)
    updated = org.model_copy(
        update={"rate_card": tuple(VendorRate(**r.model_dump()) for r in body)}
    )
    _registry(container).save_organisation(updated)
    container.ledger.record(
        patient_id="",
        source=SourceSystem.PARTNER,
        source_record_id=f"vendor-rates/{org.id}/{len(body)}",
        claim=f"{org.name} stated {len(body)} rate(s)",
        metadata={"by": principal.name if principal else org.name},
    )
    return {"rate_card": [r.model_dump(mode="json") for r in updated.rate_card]}


def _standing(container, organisation_id: str) -> dict:
    """How this vendor has actually behaved. Counted, never scored.

    Every number here comes from readiness items this system wrote down at the
    time. There is no rating, because a rating is an opinion with a number's
    authority, and a desk choosing whom to ring next is better served by "has
    said no to four of nine" than by three and a half stars.
    """
    now = container.clock.now()
    asked = confirmed = accepted = could_not = overdue = waiting = 0
    for patient in container.world.patients():
        for item in container.world.readiness_for(patient.id):
            if item.partner_id != organisation_id:
                continue
            asked += 1
            if item.status is ReadinessStatus.READY:
                confirmed += 1
            elif item.status is ReadinessStatus.BLOCKED:
                could_not += 1
            elif item.status is ReadinessStatus.PENDING:
                waiting += 1
                if item.answer_by is not None and item.answer_by < now:
                    overdue += 1
                elif item.detail:
                    # Accepted but not yet confirmed: the vendor has answered
                    # once and owes a second answer.
                    accepted += 1
    return {
        "asked": asked,
        "confirmed": confirmed,
        "accepted_not_yet_confirmed": accepted,
        "could_not": could_not,
        "waiting_on_you": waiting,
        "past_the_time_promised": overdue,
        "how_this_is_worked_out": (
            "Counted from the jobs themselves, as they were recorded at the "
            "time. There is no rating: how long each answer took is not kept, "
            "so it is not reported."
        ),
    }


@router.get("/earnings", dependencies=[PartnerOnly])
async def earnings(container: ContainerDep, principal: PrincipalDep) -> dict:
    """What this vendor has quoted, and Saathi's share of it.

    Quotes, not receipts. Money moves from the family to the vendor through the
    vendor's own account; this system hears that it did, and never holds it.
    """
    org = _own(container, principal)
    desk = container.runner.kharcha
    store = getattr(desk, "store", None) if desk is not None else None
    if store is None:
        raise HTTPException(503, "no spends ledger is configured")

    quoted_paise = 0
    lines: list[dict] = []
    for patient_id in store.patients():
        for entry in store.entries(patient_id):
            if entry.organisation_id != org.id:
                continue
            quoted_paise += entry.amount_paise
            lines.append(
                {
                    "on": entry.on.isoformat(),
                    "amount_inr": entry.amount_paise // 100,
                    "category": entry.category.value,
                    "status": entry.status.value,
                    # The job this came from, which the vendor was told when it
                    # was asked and needs in order to reconcile its own books.
                    # Nothing else: no name, no district, no step, nothing
                    # clinical. The internal reference is not passed through,
                    # because it is built for this system's own tracing and
                    # its shape is not a promise to anybody outside.
                    "job": (entry.source_ref or "").split(":")[1]
                    if ":" in (entry.source_ref or "")
                    else "",
                }
            )
    lines.sort(key=lambda line: line["on"], reverse=True)
    commission_paise = org.commission_paise(quoted_paise)
    return {
        "organisation": {"id": org.id, "name": org.name},
        "quoted_inr": quoted_paise // 100,
        "commission_pct": org.commission_pct,
        "commission_inr": commission_paise // 100,
        "you_keep_inr": (quoted_paise - commission_paise) // 100,
        "family_pays_inr": quoted_paise // 100,
        "note": (
            "The family is told your price and pays your price. Our share comes "
            f"out of ours, is capped at {MOST_COMMISSION_PCT:g}%, and never "
            "appears on their bill."
        ),
        "lines": lines,
    }


# ---------------------------------------------------------- the review


@router.get("/applications", dependencies=[AnyStaff])
async def applications(container: ContainerDep) -> list[dict]:
    """Vendors waiting to be let in, oldest first."""
    pending = [o for o in _registry(container).organisations() if o.awaiting_review]
    pending.sort(key=lambda o: (o.applied_on or container.clock.today(), o.id))
    return [
        {
            **org.model_dump(mode="json"),
            "rate_lines": len(org.rate_card),
            "awaiting_review": True,
        }
        for org in pending
    ]


class Decision(BaseModel):
    #: Agreed with the vendor, not set by the vendor. Capped by the domain.
    commission_pct: float = Field(default=0.0, ge=0.0, le=MOST_COMMISSION_PCT)
    #: Optional: create the vendor's login in the same step. Left out when the
    #: account already exists, or when somebody would rather do it separately.
    username: str | None = Field(default=None, min_length=2, max_length=64)
    password: str | None = Field(default=None, min_length=8, max_length=256)


@router.post("/applications/{organisation_id}/approve", dependencies=[AdminOnly])
async def approve(
    container: ContainerDep,
    principal: PrincipalDep,
    organisation_id: str,
    body: Annotated[Decision, ...],
) -> dict:
    """Let a vendor in, on agreed terms, and optionally create its login."""
    store = _registry(container)
    org = next((o for o in store.organisations() if o.id == organisation_id), None)
    if org is None:
        raise HTTPException(404, "no such application")
    if not org.awaiting_review:
        raise HTTPException(409, "this application has already been decided")

    approved = org.model_copy(
        update={
            "active": True,
            "approved_on": container.clock.today(),
            "commission_pct": body.commission_pct,
            "declined_reason": "",
        }
    )
    store.save_organisation(approved)

    account: str | None = None
    if body.username and body.password:
        identity = getattr(container, "identity", None)
        if identity is None or not hasattr(identity, "add_user"):
            raise HTTPException(
                409,
                "the organisation is approved, but this deployment has no account "
                "store, so create the vendor's login where its accounts are kept",
            )
        try:
            identity.add_user(
                body.username,
                approved.name,
                Role.PARTNER,
                body.password,
                organisation_id=approved.id,
            )
        except ValueError as exc:
            # The organisation is in; only the login failed. Say which, rather
            # than rolling back something a person just agreed to.
            raise HTTPException(422, f"approved, but the login was refused: {exc}") from exc
        account = body.username.lower()

    container.ledger.record(
        patient_id="",
        source=SourceSystem.NAVIGATOR,
        source_record_id=f"vendor-approval/{approved.id}",
        claim=(
            f"{approved.name} approved into the network at "
            f"{approved.commission_pct:g}% commission"
        ),
        metadata={"by": principal.name if principal else "", "account": account or ""},
    )
    return {
        "id": approved.id,
        "active": True,
        "commission_pct": approved.commission_pct,
        "account": account,
    }


class Declined(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/applications/{organisation_id}/decline", dependencies=[AdminOnly])
async def decline(
    container: ContainerDep,
    principal: PrincipalDep,
    organisation_id: str,
    body: Annotated[Declined, ...],
) -> dict:
    """Turn an application down, with a reason somebody can be told.

    The record stays, switched off and carrying the reason. A declined vendor
    that vanished from the directory would be reapplied for, reviewed again,
    and declined again by somebody who never saw the first decision.
    """
    store = _registry(container)
    org = next((o for o in store.organisations() if o.id == organisation_id), None)
    if org is None:
        raise HTTPException(404, "no such application")
    if not org.awaiting_review:
        raise HTTPException(409, "this application has already been decided")
    declined = org.model_copy(
        update={"active": False, "declined_reason": body.reason.strip()}
    )
    store.save_organisation(declined)
    container.ledger.record(
        patient_id="",
        source=SourceSystem.NAVIGATOR,
        source_record_id=f"vendor-decline/{declined.id}",
        claim=f"{declined.name} declined: {declined.declined_reason}",
        metadata={"by": principal.name if principal else ""},
    )
    return {"id": declined.id, "declined_reason": declined.declined_reason}


__all__ = ["router"]
