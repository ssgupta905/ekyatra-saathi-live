"""What the family is entitled to, and what they still have to bring.

The temptation here is to return a tidy list of entitlements with statuses, and
it would be a lie. Saathi does not know whether Shambhu holds an Ayushman card.
Nobody has told it. The only honest states are *held* (because somebody said so
and there is a ledger row), *missing* (because somebody checked and said no),
and **unknown**, which is where almost every family starts.

Unknown is the useful answer. It is what puts "bring your Ayushman card" on the
checklist, and it is what a navigator asks about on the call. A tool that
guessed "probably has one" would quietly remove that line and the family would
arrive without it — which is a wasted journey caused by a confident default.

Entitlements come from two places, both real: a live scheme endpoint when one is
configured, and otherwise the ledger — what the family themselves said, and what
a desk recorded. Requirements come from `HospitalPolicy`, because which papers a
hospital wants for which step is that hospital's rule.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import httpx

from ..domain.enums import SourceSystem, StepKind
from ..domain.models import Patient
from ..domain.policy import ENTITLEMENTS
from .base import PROVIDER_LIVE, PROVIDER_LOCAL, ToolResult, ToolUnavailable

logger = logging.getLogger(__name__)


class Holding(StrEnum):
    HELD = "held"
    MISSING = "missing"
    #: Nobody has been asked yet. The common case, and the one that drives the
    #: checklist — never collapse it into "missing" or into "held".
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Entitlement:
    id: str
    label: str
    holding: Holding
    #: Ledger ids backing a `held`/`missing` answer. Empty for `unknown`, which
    #: is itself the evidence that nobody has asked.
    evidence_ids: tuple[str, ...] = ()
    note: str = ""

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "holding": self.holding.value,
            "evidence_ids": list(self.evidence_ids),
            "note": self.note,
        }


#: What a step needs the family to carry. Shaped as a question the hospital
#: answers through the admin console; these ids are the vocabulary, not the
#: answers — whether a given hospital wants a demand draft for a given step is
#: `HospitalPolicy`'s business, and the default below asks for nothing.
KNOWN_ENTITLEMENTS = ENTITLEMENTS


class SchemeTool:
    """Entitlement status, from a scheme feed or from what the family told us."""

    name = "schemes.entitlements"

    def __init__(
        self,
        *,
        feed_url: str | None = None,
        allow_network: bool = False,
        timeout: float = 5.0,
    ) -> None:
        self._feed_url = feed_url.rstrip("/") if feed_url else None
        self._allow_network = allow_network
        self._timeout = timeout

    @property
    def live(self) -> bool:
        return bool(self._feed_url and self._allow_network)

    def entitlements(
        self,
        patient: Patient,
        *,
        required: tuple[str, ...],
        recorded: dict[str, tuple[Holding, tuple[str, ...]]] | None = None,
    ) -> ToolResult[tuple[Entitlement, ...]] | None:
        """What this family needs for the step, and whether we know they have it.

        `recorded` is what the ledger already says — `{entitlement_id: (holding,
        evidence_ids)}`. Anything not in it comes back `unknown`, which is the
        point of this tool rather than a gap in it.
        """
        if not required:
            return None

        known = dict(recorded or {})
        if self.live:
            fetched = self._from_feed(patient)
            if fetched is not None:
                known = {**fetched, **known}  # a desk's record beats a stale feed

        items: list[Entitlement] = []
        for entitlement_id in required:
            holding, evidence = known.get(entitlement_id, (Holding.UNKNOWN, ()))
            items.append(
                Entitlement(
                    id=entitlement_id,
                    label=KNOWN_ENTITLEMENTS.get(entitlement_id, entitlement_id),
                    holding=holding,
                    evidence_ids=evidence,
                )
            )

        unknown = [i for i in items if i.holding is Holding.UNKNOWN]
        missing = [i for i in items if i.holding is Holding.MISSING]
        if missing:
            claim = f"{len(missing)} of {len(items)} required documents are not held"
        elif unknown:
            claim = (
                f"{len(unknown)} of {len(items)} required documents have not been "
                f"checked with the family"
            )
        else:
            claim = f"all {len(items)} required documents are held"

        return ToolResult(
            value=tuple(items),
            tool=self.name,
            source=SourceSystem.CAREGIVER_REPLY if not self.live else SourceSystem.ABDM,
            source_record_id=f"entitlements:{patient.id}",
            claim=claim,
            provider=PROVIDER_LIVE if self.live else PROVIDER_LOCAL,
            detail={"items": [i.to_json() for i in items]},
        )

    def required_for(
        self, kind: StepKind, policy_requirements: dict[str, list[str]]
    ) -> tuple[str, ...]:
        """What the hospital asks families to bring for this step kind.

        Read from the hospital's configured requirements. A hospital that has
        configured nothing asks for nothing, rather than this module deciding
        on its behalf.
        """
        return tuple(policy_requirements.get(kind.value, ()))

    def _from_feed(
        self, patient: Patient
    ) -> dict[str, tuple[Holding, tuple[str, ...]]] | None:
        url = f"{self._feed_url}/entitlements/{patient.id}"
        try:
            response = httpx.get(url, timeout=self._timeout)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolUnavailable(f"scheme feed: {exc}") from exc

        out: dict[str, tuple[Holding, tuple[str, ...]]] = {}
        for item in body.get("entitlements", []):
            try:
                holding = Holding(item["holding"])
            except (KeyError, ValueError):
                continue
            out[str(item.get("id"))] = (holding, ())
        return out
