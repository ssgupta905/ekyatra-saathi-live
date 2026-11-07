"""Configuration an administrator can see and, for each hospital's rules, edit.

The rules (`HospitalPolicy`) are stored, versioned and ledgered here, and once a
hospital has saved a version **the planner reads it**: what families are asked to
bring, and in a disruption re-plan, which days a step runs, the lead days after
its prerequisites, the stay-or-go threshold and the reservation notice. Saving
re-plans every family at once, so the effect is visible immediately.

What the planner does not read yet is said on every response, so nobody edits a
value expecting an effect it does not have.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ..domain.enums import StepKind
from ..domain.policy import HospitalPolicy, default_policy
from ..tools.schemes import KNOWN_ENTITLEMENTS
from .access import AdminOnly, PrincipalDep
from .deps import ContainerDep
from .registry import ledger, who

router = APIRouter(prefix="/admin")

#: What the planner reads from a hospital's saved rules, and what it does not yet.
READ_BY_PLANNER = (
    "what a family is asked to bring",
    "in a disruption re-plan: the days each step runs and its lead days after prerequisites",
    "in a disruption re-plan: when waiting in the city beats going home",
    "in a disruption re-plan: journeys needing a reservation, and how much notice",
)
NOT_READ_YET = (
    "slot times (plans give a date, not a time)",
    "how far a step may move when a family asks (that request flow is not wired yet)",
    "treatment centres (the nearer-centre option is not wired yet)",
)


def _note(saved: bool) -> str:
    if saved:
        return "In force: the planner reads these rules for this hospital."
    return (
        "No rules saved for this hospital: it is planned with Saathi's built-in behaviour, "
        "not the placeholders below. Saving makes them this hospital's rules."
    )


def _registry(state: ContainerDep):
    if state.registry is None:
        raise HTTPException(503, "no registry is configured")
    return state.registry


@router.get("/policy-vocabulary", dependencies=[AdminOnly])
async def vocabulary() -> dict:
    """The words a rules editor offers: step kinds and the documents a family can be asked for."""
    return {
        "step_kinds": [k.value for k in StepKind],
        "entitlements": KNOWN_ENTITLEMENTS,
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    }


@router.get("/policy/{hospital_id}", dependencies=[AdminOnly])
async def get_policy(state: ContainerDep, hospital_id: str) -> dict:
    registry = _registry(state)
    if not any(h.id == hospital_id for h in registry.hospitals()):
        raise HTTPException(404, "unknown hospital")
    stored = registry.policy(hospital_id)
    if stored is None:
        policy, version, saved_by, source = default_policy(hospital_id), 0, None, "default"
    else:
        policy = HospitalPolicy.model_validate(stored[0])
        version, saved_by, source = stored[1], stored[2], "saved"
    return {
        "hospital_id": hospital_id,
        "policy": policy.model_dump(mode="json"),
        "version": version,
        "saved_by": saved_by,
        "source": source,
        "used_by_planner": source == "saved",
        "note": _note(source == "saved"),
        "read_by_planner": list(READ_BY_PLANNER),
        "not_read_yet": list(NOT_READ_YET),
        "centres": [
            c.model_dump(mode="json") for c in registry.centres() if c.hospital_id == hospital_id
        ],
    }


@router.put("/policy/{hospital_id}", dependencies=[AdminOnly])
async def put_policy(
    state: ContainerDep, principal: PrincipalDep, hospital_id: str, body: dict
) -> dict:
    registry = _registry(state)
    if not any(h.id == hospital_id for h in registry.hospitals()):
        raise HTTPException(404, "unknown hospital")
    if body.get("hospital_id", hospital_id) != hospital_id:
        raise HTTPException(422, "the rules name a different hospital")
    try:
        policy = HospitalPolicy.model_validate({**body, "hospital_id": hospital_id})
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from exc
    unknown_docs = {
        doc for docs in policy.requirements.values() for doc in docs
    } - set(KNOWN_ENTITLEMENTS)
    if unknown_docs:
        raise HTTPException(422, f"unknown documents: {', '.join(sorted(unknown_docs))}")
    unknown_steps = set(policy.requirements) - {k.value for k in StepKind}
    if unknown_steps:
        raise HTTPException(422, f"unknown step kinds: {', '.join(sorted(unknown_steps))}")
    version = registry.save_policy(hospital_id, policy.model_dump(mode="json"), who(principal))
    ledger(state, principal, f"policy/{hospital_id}",
           f"rules for {hospital_id} saved as version {version}")  # fmt: skip
    if state.rules is not None:
        state.rules.invalidate()
    # Re-plan now, so a changed rule shows in every family's plan at once rather
    # than at the next tick (which on real records may be minutes away).
    await state.runner.plan_all()
    return {"hospital_id": hospital_id, "version": version, "used_by_planner": True,
            "note": _note(True)}  # fmt: skip


def _listens(settings) -> list[str]:
    """Every service that would be asked to listen, best first."""
    asked = []
    if settings.sarvam_api_key:
        asked.append(f"Sarvam · {settings.sarvam_listen_model}")
    if settings.groq_api_key:
        asked.append(f"Groq · {settings.whisper_model}")
    return asked


def _speaks(settings) -> list[str]:
    """Every service that could read a message out.

    Empty is meaningful: no browser and few phones have an Odia voice, so an
    empty list here means an Odia family hears nothing at all.
    """
    return [f"Sarvam · {settings.sarvam_speak_model}"] if settings.sarvam_api_key else []


def _scheme_and_host(url: str | None) -> str | None:
    """A URL without credentials or path: enough to recognise, nothing to leak."""
    if not url:
        return None
    parts = urlsplit(url)
    host = parts.hostname or parts.path.split("/")[0]
    return f"{parts.scheme}://{host}" if host else parts.scheme


@router.get("/integrations", dependencies=[AdminOnly])
async def integrations(state: ContainerDep) -> dict:
    """What is switched on and where it points. Never a key, a password or a full URL."""
    settings = state.settings
    layer = state.planner.language_layer
    cache = settings.reference_cache_file
    return {
        "world": settings.world,
        "environment": settings.environment,
        "login": {
            "on": settings.auth_on,
            "provider": settings.identity_provider,
            "secret_is_default": settings.auth_secret.startswith("dev-only"),
        },
        "records_database": urlsplit(settings.records_url).scheme or None,
        "language_layer": (
            getattr(layer, "describe", lambda: "on")() if layer is not None else None
        ),
        "actors": state.runner.actors is not None,
        #: Who is *asked*, in order — not who answers.
        #:
        #: This used to read "Sarvam · saarika:v2.5" whenever a key was present,
        #: which is how a deployment ran for hours with a key the service
        #: rejected: listening quietly fell through to Whisper and looked fine,
        #: speaking had nothing to fall through to and returned 502, and this
        #: page said Sarvam was doing both. A key being set is not the same as
        #: a key that works, and the screen should not blur the two.
        "speech_to_text": _listens(settings),
        "text_to_speech": _speaks(settings),
        "reference_cache": {
            "present": cache.exists(),
            "network_lookups": settings.tools_allow_network,
        },
        "geocoder": _scheme_and_host(settings.geocoder_url),
        "router": _scheme_and_host(settings.router_url),
        "feeds": {
            "hospital": _scheme_and_host(settings.hospital_feed_url),
            "schemes": _scheme_and_host(settings.scheme_feed_url),
            "abdm": settings.abdm_enabled,
        },
        "channels": {"whatsapp": settings.whatsapp_enabled, "bhashini": settings.bhashini_enabled},
        "graph_database": settings.neo4j_enabled,
    }
