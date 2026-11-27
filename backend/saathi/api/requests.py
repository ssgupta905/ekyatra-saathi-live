"""What families asked for, waiting on a person to agree with the reading.

This is the half of the loop that did not exist. `domain/requests.py`,
`live/actors.py:extract_request` and `planner/options.py:candidates_for_request`
were all built and tested, and none of them was reachable: `main.py` registered
seventeen routers and not one of them for a patient request. So a family could
say "nothing before the 1st, my salary comes then" and the sentence went into
storage and stopped.

Everything here is deliberately a two-step. A reading arrives with
`confirmed_by` empty, a navigator agrees with it or corrects it, and only then
may the planner act. The reason is in `domain/requests.py` and bears repeating
at the API boundary, because this is where somebody would be tempted to skip
it: mishearing "after the 20th" as "on the 20th" costs a family a journey of
several hundred kilometres, and the cost of asking a person is one tap.

Rejecting is a first-class outcome, not an error path. A navigator who reads
the message and sees the extractor got it wrong has done the most valuable
thing in the loop, and that has to be recordable with the correction attached
— otherwise the only way to disagree with the machine is to ignore it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..live.knowledge import build as build_graph
from ..live.reasoning import reasoning_log
from ..research.burden import COLUMNS as RESEARCH_COLUMNS
from ..research.collect import build as build_release
from .access import DeskWork, PrincipalDep
from .deps import ContainerDep

router = APIRouter(tags=["requests"])


class RejectIn(BaseModel):
    """Why the reading was wrong, in the navigator's words."""

    reason: str = Field(min_length=1, max_length=280)


def _who(principal: object) -> str:
    """The name to record a decision under.

    `PrincipalDep` is `Principal | None` by design — sign-in can be switched
    off, and the demo runs that way. Reaching through it for a name without
    checking is how the budget endpoint once returned a 500 on the single
    configuration the recording uses.
    """
    name = getattr(principal, "name", "") if principal is not None else ""
    return name or "staff"


@router.get("/requests/waiting", dependencies=[DeskWork])
async def requests_waiting(state: ContainerDep) -> list[dict]:
    """Every reading a family is waiting on a person for.

    Sorted so the ones a machine cannot help with come first. A request the
    planner can act on will be acted on the moment it is confirmed; one that
    needs money, papers or transport needs a human being either way, and
    leaving those at the bottom of a queue is how they go cold.
    """
    out = []
    for patient_id, queue in state.runner.requests.items():
        patient = state.world.patient(patient_id)
        for request in queue:
            if request.confirmed_by is not None or request.rejected_reason is not None:
                continue
            row = {
                "id": request.id,
                "patient_id": patient_id,
                "name": patient.name if patient else patient_id,
                # Which language they actually replied in. Absent until now,
                # which left every reader of this row — the Console, and a
                # film trying to tap a card on their screen — guessing, and
                # defaulting to English for a family who does not read it.
                "language": patient.language.value if patient else None,
                "intent": request.intent.value,
                "summary": request.summary(),
                "raw_text": request.raw_text,
                "gloss": request.gloss,
                "step_kind": request.step_kind.value if request.step_kind else None,
                "confidence": request.confidence,
                "needs_a_person": request.needs_a_person,
                "received_at": request.received_at.isoformat(),
                "constraint": request.constraint.model_dump(mode="json"),
            }
            # Travel facts are shown only when every figure can be traced to
            # something the family said. A number with no sentence behind it
            # is indistinguishable from one this system invented, and the
            # Console must not be the place that blurs the two.
            if request.travel.anything_said and request.travel_is_attributable:
                row["travel"] = request.travel.model_dump(mode="json")
            out.append(row)
    out.sort(key=lambda row: (not row["needs_a_person"], row["received_at"]))
    return out


@router.get("/questions/waiting", dependencies=[DeskWork])
async def questions_waiting(state: ContainerDep) -> list[dict]:
    """Questions Saathi has asked and not had an answer to.

    On the same screen as the readings on purpose. A family who was asked
    something and never replied is not visible anywhere else, and they are the
    ones most likely to turn up on the wrong day — or not at all.
    """
    out = []
    for question in state.runner.conversation.waiting():
        patient = state.world.patient(question.patient_id)
        out.append(
            {
                "id": question.id,
                "patient_id": question.patient_id,
                "name": patient.name if patient else question.patient_id,
                "reason": question.reason.value,
                "topics": [topic.value for topic in question.topics],
                "asked_text": question.asked_text,
                "language": question.language.value,
                "about_day": question.about_day,
                "asked_at": question.asked_at.isoformat(),
                "summary": question.summary(),
            }
        )
    out.sort(key=lambda row: row["asked_at"])
    return out


@router.get("/reasoning", dependencies=[DeskWork])
async def reasoning(
    state: ContainerDep, patient_id: str | None = None, limit: int = 200
) -> list[dict]:
    """The agent's working, as a judge reads it.

    A projection of the real event stream — every line was published by the
    code that did the work, carrying the duration that work actually took.
    Nothing is written here to describe the work, because a description
    written alongside the work is a thing that can disagree with it.

    `GET /api/reasoning?patient_id=…` is the question a judge actually asks:
    show me why this family was told this day.
    """
    return [
        line.to_json()
        for line in reasoning_log(
            state.runner.bus.recent(limit=600), patient_id=patient_id, limit=limit
        )
    ]


@router.get("/research/release", dependencies=[DeskWork])
async def research_release(state: ContainerDep) -> dict:
    """What this system could contribute to cancer research, right now.

    Returns the dataset *and* the manifest: the columns, what was removed
    before export and why, how many families consented, and how many were
    left out. Read-only — nothing is written and nothing is sent. An export
    that posted itself would be the wrong shape for something leaving an
    institution; a person looks at this and then decides.

    India has cancer registries with staging and survival. What it has almost
    none of is why patients stop coming, and the answer is usually a bus fare
    and a lost working day. That is what this contributes.
    """
    release = build_release(state.runner, state.consent)
    return {
        "manifest": release.manifest(),
        "csv": release.to_csv(),
        "rows": [
            dict(zip(RESEARCH_COLUMNS, row.as_csv_row(), strict=True))
            for row in release.rows
        ],
    }


@router.get("/patients/{patient_id}/search", dependencies=[DeskWork])
async def plan_search(state: ContainerDep, patient_id: str) -> dict:
    """Every date the planner tried for this family, and what became of each.

    The question nobody can answer from a plan alone: *what else did you look
    at?* The filtering itself is unchanged — a family is still never offered
    a date the rules would then refuse — but the discarding is on the record.

    Empty until a disruption has made the planner search. A family whose plan
    has never been challenged has no search, and saying so is better than an
    invented one.
    """
    found = state.runner.searches.get(patient_id)
    return found.to_json() if found else {
        "patient_id": patient_id,
        "step_kind": "",
        "summary": "nothing has forced a re-plan for this family yet",
        "considered": [],
    }


@router.get("/patients/{patient_id}/graph", dependencies=[DeskWork])
async def knowledge_graph(state: ContainerDep, patient_id: str) -> dict:
    """One family's situation as a graph of things that actually exist.

    Built by reading live state, not from a description: the hospital
    snapshot, the questions asked, the readings waiting, the plan. A family
    with nothing pending has no pending node — a four-node graph is the right
    graph when there are four things.
    """
    return build_graph(state.runner, patient_id).to_json()


@router.post("/patients/{patient_id}/requests/{request_id}/confirm", dependencies=[DeskWork])
async def confirm_request(
    state: ContainerDep, principal: PrincipalDep, patient_id: str, request_id: str
) -> dict:
    """A navigator agrees this is what the family meant.

    Re-plans at once, so the options a navigator sees next already reflect the
    constraint they just agreed to rather than the one before it.

    Two steps, in this order. First the constraint is actually searched
    against — `replan_for_request` tries what she asked for, the edge of the
    hospital's tolerance, and earlier, and records every date it ruled out.
    Then the ordinary plan re-runs. Before this, only the second half
    happened, so a confirmed constraint changed nothing at all.
    """
    request = state.runner.confirm_request(patient_id, request_id, _who(principal))
    if request is None:
        raise HTTPException(404, "no such request from this family")
    search = await state.runner.replan_for_request(patient_id, request)
    run = await state.runner.plan_patient(patient_id, allow_render=True)
    return {
        "request": request.model_dump(mode="json"),
        "decision": run.decision.value if run else None,
        "search": search.to_json() if search is not None else None,
    }


@router.post("/patients/{patient_id}/requests/{request_id}/reject", dependencies=[DeskWork])
async def reject_request(
    state: ContainerDep,
    principal: PrincipalDep,
    patient_id: str,
    request_id: str,
    body: RejectIn,
) -> dict:
    """A navigator says the reading was wrong, and what it should have said.

    No re-plan. The planner never saw this request, so there is nothing to
    undo — which is the point of confirming before acting rather than after.
    """
    request = state.runner.reject_request(
        patient_id, request_id, _who(principal), body.reason
    )
    if request is None:
        raise HTTPException(404, "no such request from this family")
    return {"request": request.model_dump(mode="json")}
