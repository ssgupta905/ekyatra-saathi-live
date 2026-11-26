"""How to get there: which bus, boarded where, and which way suits this family.

Family only, like the books it reads: the answer weighs what the family said
they can manage. The place a family types for the last leg is sent to the route
service for this one request and is not kept.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query

from ..domain.enums import StepStatus
from ..domain.itinerary import FareBasis, RouteOption
from ..domain.railways import IRCTC_SEARCH, LIVE_STATUS, arrival_stations, rail_hint
from ..live.events import EventKind
from ..orchestrator.trip_options import LONG_ROAD_MINUTES, next_visit_start, weigh
from ..ports.routes import Place, RoutesUnavailable
from .access import FamilyOnly
from .deps import ContainerDep

logger = logging.getLogger(__name__)
router = APIRouter(tags=["trip"])


def _travel_day(state, patient_id: str, arrive_by) -> date | None:
    """The day the money is spent: when they set out, else the day of the visit."""
    run = state.runner.plans.get(patient_id)
    if run is not None and run.plan is not None and run.plan.travel_on is not None:
        return run.plan.travel_on
    return arrive_by.date() if arrive_by is not None else None


def _stated_fare(state, patient_id: str) -> tuple[int, str] | None:
    """The fare the family themselves said, with the sentence it came from.

    Never a figure Saathi worked out: only one a family said out loud, read
    into a request a person has not rejected, and kept with its sentence.
    """
    for request in reversed(state.runner.requests.get(patient_id, [])):
        travel = request.travel
        if (
            request.rejected_reason is None
            and travel.stated_cost_inr
            and request.travel_is_attributable
        ):
            return travel.stated_cost_inr * 100, travel.stated_in
    return None


def _budget(state, patient_id: str, arrive_by) -> dict | None:
    """What the family said they can manage, for the month they will travel in.

    The room is the limit less what is already spent, booked or expected in that
    month. None when they have said neither a limit nor a fare, so the screen
    can ask rather than imply a budget that was never set.
    """
    desk = state.runner.kharcha
    if desk is None:
        return None
    limit = desk.store.limit(patient_id)
    stated = _stated_fare(state, patient_id)
    if limit is None and stated is None:
        return None
    this_month, following = desk.months(patient_id)
    day = _travel_day(state, patient_id, arrive_by)
    month = following if day is not None and day >= following.month else this_month
    room = max(limit.monthly_paise - month.total_known_paise, 0) if limit else None
    return {
        "month": month.month.isoformat(),
        "limit_paise": limit.monthly_paise if limit else None,
        "said": limit.stated_in if limit else None,
        "committed_paise": month.total_known_paise,
        "room_paise": room,
        "stated_fare_paise": stated[0] if stated else None,
        "stated_in": stated[1] if stated else None,
    }


def _rail(
    patient, leg: str, transit: list[RouteOption], driving: list[RouteOption], arrive_by
) -> dict | None:
    """Train guidance for the long leg, when a train is the realistic way.

    Only when the road is long and no route service found a public way. It
    names the two stations with the codes IRCTC asks for and links to IRCTC;
    it does not claim a train, a time or a fare, none of which Saathi can read.
    """
    if leg != "far" or transit:
        return None
    hint = rail_hint(patient.home_district, patient.hospital_id)
    if hint is None:
        return None
    road = min((o.minutes for o in driving), default=None)
    if road is not None and road <= LONG_ROAD_MINUTES:
        return None

    def station(st):
        return {"name": st.name, "code": st.code}

    return {
        "from": station(hint.origin),
        "to": station(hint.nearest),
        "also": [station(st) for st in hint.arrival[1:]],
        "visit_at": arrive_by.isoformat() if arrive_by is not None else None,
        "road_minutes": road,
        "allow_days": math.ceil(road / 1440) if road else None,
        "irctc_url": IRCTC_SEARCH,
        "status_url": LIVE_STATUS,
    }


def _say_what_was_worked_out(
    state, patient, *, leg, planner, transit, driving, guidance, budget, rail
) -> None:
    """Put the journey work on the event stream, where a navigator can see it.

    This used to happen in silence. A family opened the screen, a route
    service was asked, three ways came back, one was recommended against what
    they said they could afford — and none of it reached the reasoning log, so
    nobody but the family ever knew it had happened. "Why was she told to take
    a train?" had no answer anywhere.

    It is a `SEARCH` step for the same reason the planner's date search is:
    this enumerates what could be done. Nothing here decides anything, and a
    failure to publish must never fail the family's screen, which is why the
    whole thing is wrapped.
    """
    try:
        ways = len(transit) + len(driving)
        picked = guidance.recommended_id if guidance is not None else None
        parts = [f"{ways} way(s) by {planner.name}"]
        if rail is not None:
            parts.append(f"train from {rail['from']['code']} to {rail['to']['code']}")
        elif leg == "far" and not transit:
            parts.append("no public way found")
        if budget:
            room = budget.get("room_paise")
            if room is not None:
                parts.append(f"₹{room // 100} left this month")
            elif budget.get("stated_fare_paise"):
                parts.append(f"they said ₹{budget['stated_fare_paise'] // 100}")
        if picked:
            parts.append(f"recommended {picked}")
        state.bus.publish(
            EventKind.JOURNEY_GUIDED,
            state.world.today.isoformat(),
            patient_id=patient.id,
            summary=f"{patient.id}: {leg} leg — " + "; ".join(parts),
            leg=leg,
            source=planner.name,
            ways=ways,
            recommended=picked,
            rail=rail,
            budget=budget,
        )
    except Exception:  # noqa: BLE001 - the family's screen is not worth a log line
        logger.exception("could not record the journey guidance for %s", patient.id)


def _booked_arrival(state, patient, hospital) -> datetime | None:
    """When the hospital's own diary says this family's next visit starts."""
    sync = state.runner.sync_for_patient(patient.id)
    if sync is None:
        return None
    booked = [
        a.starts_at
        for a in sync.snapshot.by_ref.values()
        if a.state.is_open and sync.links.patient_for(a) == patient.id
    ]
    days = [
        s.scheduled_for
        for s in state.world.steps_for(patient.id)
        if s.scheduled_for is not None and s.status is StepStatus.SCHEDULED
    ]
    try:
        tz = ZoneInfo(getattr(hospital, "timezone", None) or "UTC")
    except ZoneInfoNotFoundError:
        tz = UTC
    return next_visit_start(booked, days, tz=tz, now=datetime.now(UTC))


@router.get("/patients/{patient_id}/trip/options", dependencies=[FamilyOnly])
async def options(
    state: ContainerDep,
    patient_id: str,
    leg: Literal["far", "near"] = "far",
    origin: str = Query(default="", max_length=200),
    arrive_by: datetime | None = None,
) -> dict:
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    planner = state.routes
    if planner is None:
        raise HTTPException(409, "no route service is set up here")
    hospital = next(
        (
            h
            for h in (state.registry.hospitals() if state.registry else [])
            if h.id == patient.hospital_id
        ),
        None,
    )
    if hospital is None or hospital.latitude is None or hospital.longitude is None:
        raise HTTPException(409, "the hospital's entrance is not on record")
    start = patient.home_district if leg == "far" else origin.strip()
    origin_used = None
    if not start and leg == "near":
        # Most families arrive by train: begin from the terminal nearest the
        # hospital, so the last leg loads without anyone typing a place.
        arrival = arrival_stations(patient.hospital_id)
        if arrival:
            start, origin_used = arrival[0].place, arrival[0].name
    if not start:
        raise HTTPException(422, "say where you are starting from")

    arrive_source = "given" if arrive_by is not None else None
    if arrive_by is None:
        arrive_by = _booked_arrival(state, patient, hospital)
        arrive_source = "hospital_booking" if arrive_by is not None else None

    to = Place(f"{hospital.latitude},{hospital.longitude}")
    try:
        transit, driving = await asyncio.gather(
            planner.options(Place(start), to, mode="transit", arrive_by=arrive_by),
            planner.options(Place(start), to, mode="driving"),
        )
    except RoutesUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    # A seller's firm price for a car is the family's to book: it is the only
    # cost a car option may carry, with its owner named.
    quoted = next(
        (b["amount_paise"]
         for b in (state.runner.network.bookable(patient_id) if state.runner.network else [])
         if b.get("amount_paise")),
        None,
    )
    cars: list[RouteOption] = [
        o.model_copy(update={"fare_paise": quoted, "fare_basis": FareBasis.QUOTE})
        if quoted and leg == "near"
        else o
        for o in driving[:1]
    ]
    budget = _budget(state, patient_id, arrive_by)
    guidance = weigh(
        transit[:4] + cars,
        room_paise=budget["room_paise"] if budget else None,
        arrive_by=arrive_by,
    )
    # Say what is not there rather than let one car route stand in for a journey:
    # no open source carries reserved intercity trains, and Google's route data
    # does not either.
    notes = ["intercity_rail_not_covered"] if leg == "far" and not transit else []

    # On the record, not just on the family's screen.
    rail = _rail(patient, leg, transit, driving, arrive_by)
    _say_what_was_worked_out(
        state, patient, leg=leg, planner=planner, transit=transit, driving=driving,
        guidance=guidance, budget=budget, rail=rail,
    )
    return {
        "leg": leg,
        "source": planner.name,
        "arrive_by": arrive_by.isoformat() if arrive_by is not None else None,
        "arrive_by_source": arrive_source,
        "origin_used": origin_used,
        "notes": notes,
        "rail": rail,
        "budget": budget,
        "guidance": guidance.model_dump(mode="json"),
    }
