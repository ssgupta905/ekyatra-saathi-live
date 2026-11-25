"""What the planner considered, and why each candidate lived or died.

Until now the planner produced an answer and threw away its reasoning. That is
correct for the family — `care_rules.filter_options` drops impossible options
*silently*, on purpose, because showing somebody a date and then refusing it is
worse than never offering it. But it left a system that could not answer the
only question anybody senior ever asks about an automated decision: **what else
did you look at?**

So the filtering is unchanged and the discarding is recorded. Two audiences,
two views of the same search:

* a family and a navigator see the options that are actually on offer;
* the reasoning log and the Console show the whole search — every candidate,
  with the rule that killed it, in the planner's own words.

**Why the reasons are enumerated rather than free text.** A string assembled at
the rejection site drifts from the rule that produced it, and six months later
the log says something the code no longer does. `Verdict` is a closed list, each
member paired with the rule it comes from, so a new rule cannot be added without
giving it a name here.

**This records; it never decides.** Nothing in this module can keep an option
the rules rejected or drop one they kept. If that inverted, the log would stop
being a description of the search and start being part of it — and a log you
cannot trust to be a bystander is worth nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class Verdict(StrEnum):
    """Why a candidate is or is not on the list.

    Each member names a real rule in `planner/care_rules.py` or a real
    constraint from the family. Adding a rule means adding a member; a rule
    that rejects under `OTHER` is a rule nobody can explain to a clinician.
    """

    #: On the list.
    OFFERED = "offered"
    #: The hospital's own schedule rule refused it — e.g. an echo is due
    #: before the next dose and this option would skip it.
    CARE_RULE = "care_rule"
    #: Outside the window the hospital said a step may move within.
    OUTSIDE_TOLERANCE = "outside_tolerance"
    #: A prerequisite would not be ready in time, at the confidence the
    #: predictor requires. Not "probably fine" — the interval says no.
    PREREQUISITE_NOT_READY = "prerequisite_not_ready"
    #: The family told us they cannot travel then.
    FAMILY_CANNOT = "family_cannot"
    #: It would need a night away the family has not got, or a second trip
    #: when one would do.
    COSTS_THE_FAMILY_MORE = "costs_more"
    #: The resource is still unavailable on that day.
    RESOURCE_DOWN = "resource_down"
    #: Something rejected it that this vocabulary cannot name. Visible on
    #: purpose: an unexplainable rejection should look wrong in the log.
    OTHER = "other"

    @property
    def offered(self) -> bool:
        return self is Verdict.OFFERED


#: How each verdict reads to a person. Kept here rather than in the UI so the
#: API, the log and the screen cannot say three different things about one
#: decision.
WHY: dict[Verdict, str] = {
    Verdict.OFFERED: "on the list",
    Verdict.CARE_RULE: "the hospital's schedule rule does not allow it",
    Verdict.OUTSIDE_TOLERANCE: "outside the window this step may move within",
    Verdict.PREREQUISITE_NOT_READY: "a result it depends on would not be back in time",
    Verdict.FAMILY_CANNOT: "the family said they cannot travel then",
    Verdict.COSTS_THE_FAMILY_MORE: "it would cost the family an extra trip or night",
    Verdict.RESOURCE_DOWN: "the resource is still down that day",
    Verdict.OTHER: "rejected by a rule with no name — this should not appear",
}


@dataclass(frozen=True)
class Considered:
    """One candidate the planner looked at, and what became of it."""

    #: The option's own id when it survived; otherwise a stable description
    #: of the date that was tried, so a rejected candidate is still nameable.
    ref: str
    #: The day the step would land on. The thing a reader actually compares.
    on: date | None
    verdict: Verdict
    #: What the rule objected to, in the rule's own terms — a day of the week,
    #: a confidence, a number of nights. Empty when the verdict says it all.
    detail: str = ""
    #: Nights and trips this would add, when it got far enough to be costed.
    nights_added: int | None = None
    trips_added: int | None = None

    def render(self) -> str:
        """One line, as a judge reads it."""
        when = self.on.strftime("%d %b") if self.on else "no date"
        if self.verdict.offered:
            cost = []
            if self.nights_added:
                cost.append(f"{self.nights_added:+d} nights")
            if self.trips_added:
                cost.append(f"{self.trips_added:+d} trips")
            tail = f" ({', '.join(cost)})" if cost else ""
            return f"{when} — offered{tail}"
        why = WHY[self.verdict]
        return f"{when} — rejected: {why}{f' ({self.detail})' if self.detail else ''}"

    def to_json(self) -> dict:
        return {
            "ref": self.ref,
            "on": self.on.isoformat() if self.on else None,
            "verdict": self.verdict.value,
            "offered": self.verdict.offered,
            "why": WHY[self.verdict],
            "detail": self.detail,
            "nights_added": self.nights_added,
            "trips_added": self.trips_added,
            "line": self.render(),
        }


@dataclass
class Search:
    """Every candidate for one patient's re-plan, in the order tried.

    Mutable while the planner works, read-only in effect afterwards: nothing
    downstream may add to it, because a search that grew after the decision
    would no longer describe the decision.
    """

    patient_id: str
    #: Which step was being moved.
    step_kind: str = ""
    considered: list[Considered] = field(default_factory=list)

    def note(self, item: Considered) -> None:
        self.considered.append(item)

    @property
    def offered(self) -> tuple[Considered, ...]:
        return tuple(c for c in self.considered if c.verdict.offered)

    @property
    def rejected(self) -> tuple[Considered, ...]:
        return tuple(c for c in self.considered if not c.verdict.offered)

    def summary(self) -> str:
        """One line for the reasoning log.

        Says how wide the search was before it says how narrow the answer is,
        because "we offered one option" and "we looked at five and one
        survived" are very different statements about the same result.
        """
        if not self.considered:
            return "no dates were available to try"
        kept, dropped = len(self.offered), len(self.rejected)
        step = f" for {self.step_kind.replace('_', ' ')}" if self.step_kind else ""
        if not dropped:
            return f"considered {kept} date(s){step}; all were possible"
        return (
            f"considered {len(self.considered)} date(s){step}; "
            f"{kept} possible, {dropped} ruled out"
        )

    def to_json(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "step_kind": self.step_kind,
            "summary": self.summary(),
            "considered": [c.to_json() for c in self.considered],
        }


__all__ = ["WHY", "Considered", "Search", "Verdict"]
