"""The agent's working, shown as a log a judge can read in one pass.

**This is a projection, not a narration.** Every line comes from a
`WorldEvent` that was published by the code that did the work, carrying the
duration that work actually took. Nothing here is written alongside the work
to describe it, because a description written alongside the work is a thing
that can be wrong about it — and a demo whose log says "checked the hospital"
when no request was made is worse than a demo with no log.

The step labels are the vocabulary a reader needs to follow a decision without
knowing the codebase:

    [EVENT]   something happened that nobody here chose
    [CHECK]   a fact source was consulted
    [INFER]   a reading or a prediction was made from what was found
    [SEARCH]  options were enumerated
    [PLAN]    a plan was computed
    [GUARD]   something was refused
    [HUMAN]   a person decided
    [WRITE]   a record was written
    [NOTIFY]  a family was told, or asked

Two properties worth stating because they are what make the log trustworthy:

**An unmapped event is still shown.** It gets `[EVENT]`, which is the weakest
honest label, rather than being dropped. A log that silently omitted event
kinds it did not recognise would be a log that quietly got shorter as the
system grew.

**`[GUARD]` lines are kept, never filtered.** They are the ones that look bad
— a message held, a question refused, a clinical term blocked — and they are
the strongest evidence the system has that its own limits are real. A reader
who never sees a refusal has no reason to believe refusals happen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from .events import EventKind, WorldEvent


class Step(StrEnum):
    """What kind of work a line represents."""

    EVENT = "EVENT"
    CHECK = "CHECK"
    INFER = "INFER"
    SEARCH = "SEARCH"
    PLAN = "PLAN"
    GUARD = "GUARD"
    HUMAN = "HUMAN"
    WRITE = "WRITE"
    NOTIFY = "NOTIFY"


#: Event kind -> step. Every mapping here is a claim about what the publishing
#: code actually does, so the two have to be read together; a kind whose
#: meaning changes must move, not keep an inherited label.
_STEPS: dict[str, Step] = {
    # Things that happened to us.
    EventKind.DISRUPTION_RAISED: Step.EVENT,
    EventKind.STEP_RELEASED: Step.EVENT,
    EventKind.INBOUND_RECEIVED: Step.EVENT,
    EventKind.CONFIRMATION_RECEIVED: Step.EVENT,
    EventKind.ALERT_RAISED: Step.EVENT,
    EventKind.LANGUAGE_CHANGED: Step.EVENT,
    # Asking something outside this process.
    EventKind.TOOL_CALLED: Step.CHECK,
    EventKind.DESK_CANDIDATE: Step.CHECK,
    # Reading meaning out of what came back. `QUESTION_ANSWERED` and
    # `REQUEST_RAISED` are both model readings of a family's own words, which
    # is the only place in this system a model's output enters a decision —
    # and it enters as a proposal, never as the decision.
    EventKind.QUESTION_ANSWERED: Step.INFER,
    EventKind.REQUEST_RAISED: Step.INFER,
    # Enumerating what could be done.
    EventKind.OPTIONS_READY: Step.SEARCH,
    EventKind.PLAN_SEARCHED: Step.SEARCH,
    # Deciding what to do.
    EventKind.PLAN_RECOMPUTED: Step.PLAN,
    # Refusing.
    EventKind.GUARD_BLOCKED: Step.GUARD,
    EventKind.MESSAGE_HELD: Step.GUARD,
    # A person, which is the only thing that can approve anything.
    EventKind.APPROVAL_RECORDED: Step.HUMAN,
    EventKind.OPTIONS_REJECTED: Step.HUMAN,
    EventKind.REQUEST_CONFIRMED: Step.HUMAN,
    EventKind.REQUEST_REJECTED: Step.HUMAN,
    EventKind.DESK_CONFIRMED: Step.HUMAN,
    # Writing a record, ours or the hospital's.
    EventKind.LEDGER_APPENDED: Step.WRITE,
    EventKind.ESCALATION_WRITTEN: Step.WRITE,
    # Saying something to a family, or asking them something.
    EventKind.MESSAGE_RENDERED: Step.NOTIFY,
    EventKind.HOLDING_MESSAGE_SENT: Step.NOTIFY,
    EventKind.PROCESS_ANSWERED: Step.NOTIFY,
    EventKind.QUESTION_ASKED: Step.NOTIFY,
    EventKind.QUESTION_EXPIRED: Step.NOTIFY,
    EventKind.ADVICE_SENT: Step.NOTIFY,
}

#: Event kinds that are machinery rather than reasoning. A clock tick and a
#: metrics refresh are true, and putting them in a log of how a decision was
#: reached would bury the decision. Listed rather than inferred, so adding a
#: kind never silently hides it — an unlisted, unmapped kind still shows up
#: as `[EVENT]`.
_PLUMBING: frozenset[str] = frozenset(
    {
        EventKind.CLOCK_TICK,
        EventKind.METRICS_UPDATED,
        EventKind.RUNNER_STATE,
        EventKind.WORLD_RESET,
        # The agent pair is the activity drawer's business, not this log's.
        # Every piece of agent work publishes a specific event right after it
        # — `plan.recomputed`, `options.ready`, `question.answered` — which
        # carries both the meaning and the same measured duration. Keeping
        # these produced two lines per action, the first of them labelled
        # `[INFER]` for work that was planning or searching.
        EventKind.AGENT_STARTED,
        EventKind.AGENT_FINISHED,
    }
)


@dataclass(frozen=True)
class ReasoningLine:
    """One step of the agent's working."""

    step: Step
    #: Real time, so a reader can see the gaps as well as the order.
    at: str
    sim_date: str
    patient_id: str | None
    summary: str
    #: Measured, never estimated. `None` when the publishing code did not
    #: time itself — which is honest, and different from zero.
    duration_ms: float | None
    kind: str
    seq: int
    #: How many times in a row this same line occurred. 1 is the usual case.
    repeated: int = 1

    def render(self) -> str:
        """The line as a judge reads it."""
        took = f" ({self.duration_ms:.0f}ms)" if self.duration_ms is not None else ""
        again = f" ×{self.repeated}" if self.repeated > 1 else ""
        return f"[{self.step.value}] {self.summary}{took}{again}"

    def to_json(self) -> dict:
        return {
            "step": self.step.value,
            "at": self.at,
            "sim_date": self.sim_date,
            "patient_id": self.patient_id,
            "summary": self.summary,
            "duration_ms": self.duration_ms,
            "kind": self.kind,
            "seq": self.seq,
            "repeated": self.repeated,
            "line": self.render(),
        }


def step_of(kind: str) -> Step:
    """The step a kind of event represents.

    Falls back to `EVENT` rather than raising: the weakest honest label beats
    both a crash and a silent omission.
    """
    return _STEPS.get(kind, Step.EVENT)


def is_plumbing(kind: str) -> bool:
    return kind in _PLUMBING


def reasoning_log(
    events: list[WorldEvent],
    *,
    patient_id: str | None = None,
    limit: int = 200,
) -> tuple[ReasoningLine, ...]:
    """Project events into the agent's working, oldest first.

    `patient_id` narrows to one family's decision, which is how a judge reads
    it: "show me why she was told the 3rd".

    **Narrowing means narrowing.** An earlier version also kept events with no
    patient on them, on the theory that a hospital-wide signal is often the
    reason. In practice that put seven route lookups for a family in
    Darbhanga into the log of a family in Gaya, which does not read as
    context — it reads as the system having confused two people. Anything
    that genuinely bears on one family is published carrying their id.

    Consecutive identical lines are collapsed with a count. A poller that
    consults the same route on every cycle is doing something real and
    repetitive, and seven copies of one sentence buries the line that matters
    underneath them.
    """
    lines: list[ReasoningLine] = []
    for event in events:
        if is_plumbing(event.kind):
            continue
        if patient_id is not None and event.patient_id != patient_id:
            continue
        if not event.summary:
            # Nothing to show a reader. The event is still in the stream and
            # in the ledger; this log is the readable view, not the record.
            continue
        if lines and lines[-1].kind == event.kind and lines[-1].summary == event.summary:
            lines[-1] = replace(lines[-1], repeated=lines[-1].repeated + 1)
            continue
        lines.append(
            ReasoningLine(
                step=step_of(event.kind),
                at=event.at.isoformat(),
                sim_date=event.sim_date,
                patient_id=event.patient_id,
                summary=event.summary,
                duration_ms=event.duration_ms,
                kind=event.kind,
                seq=event.seq,
            )
        )
    return tuple(lines[-limit:])


__all__ = [
    "ReasoningLine",
    "Step",
    "is_plumbing",
    "reasoning_log",
    "step_of",
]
