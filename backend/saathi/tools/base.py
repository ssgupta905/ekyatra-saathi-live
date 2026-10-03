"""What a tool is, and what it is not.

A tool here is a **fact source**, not something a model can call. That
distinction is the whole reason this package can exist without weakening the
architecture's central claim.

`language/rendering.py` gives the model a decided plan and the evidence claims
behind it, and nothing else — no tools, so nothing to fetch and nothing to leak.
Adding a distance finder or a lab feed does not change that. Tools are called by
*code*: the planner, the scheduler, the runner. What they return enters the
evidence ledger as a sourced fact, and the model sees it the same way it sees a
desk booking — as a claim someone can open. There is still no call path from the
model to anything.

Four rules every tool follows.

**Every answer carries its source.** A `ToolResult` is never a bare value; it
names the provider, the record id and the time it was true. That is what lets
`record_once` write a ledger row for it, and what lets a navigator click the
number on screen and see where it came from.

**Fail closed.** A tool that cannot answer returns `None`. It never guesses, and
it never falls back to a plausible number. Downstream, an unknown is an unmet
prerequisite with no window, which is UNCERTAIN — a navigator calls. A tool
returning a confident wrong distance is worse than one returning nothing.

**Live first, real data always.** Each tool has a live client that activates when
its endpoint is configured, and a local provider backed by *real* reference data
— actual coordinates, actual corridors, the actual centre list. The fallback is
not a mock: it is the same computation over data that is true, just not fetched.
Which one answered is recorded, because "we computed this from a bundled table"
and "we asked the hospital just now" are different claims.

**Timed, like everything else.** Every call is measured and published, so a tool
call appears in the activity strip beside the planner and the model with its own
latency. A figure nobody timed is a figure nobody can check.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Generic, TypeVar

from ..domain.enums import SourceSystem

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Where a tool's answer came from. Recorded on every result because a bundled
#: table and a live hospital feed are not the same evidence.
PROVIDER_LIVE = "live"
PROVIDER_LOCAL = "local"


@dataclass(frozen=True)
class ToolResult(Generic[T]):
    """One answer, and everything needed to defend it later."""

    value: T
    #: Which tool produced this, e.g. "geo.journey".
    tool: str
    #: Ledger vocabulary: who is asserting the fact.
    source: SourceSystem
    #: Stable id for the thing asked about, so `record_once` can tell a repeat
    #: question from a changed answer.
    source_record_id: str
    #: Human-readable statement an auditor reads. This becomes the ledger claim.
    claim: str
    #: `live` or `local`.
    provider: str = PROVIDER_LOCAL
    #: When the underlying fact was true, which is not always when we asked.
    as_of: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: Measured call duration. Set by `call`.
    duration_ms: float | None = None
    #: Anything structured the console wants to show; never report content.
    detail: dict[str, Any] = field(default_factory=dict)

    def with_timing(self, duration_ms: float) -> ToolResult[T]:
        return ToolResult(
            value=self.value,
            tool=self.tool,
            source=self.source,
            source_record_id=self.source_record_id,
            claim=self.claim,
            provider=self.provider,
            as_of=self.as_of,
            duration_ms=duration_ms,
            detail=self.detail,
        )

    def to_json(self) -> dict:
        return {
            "tool": self.tool,
            "source": self.source.value,
            "source_record_id": self.source_record_id,
            "claim": self.claim,
            "provider": self.provider,
            "as_of": self.as_of.isoformat(),
            "duration_ms": self.duration_ms,
            "detail": self.detail,
        }


class ToolUnavailable(RuntimeError):
    """Raised inside a provider when it cannot answer.

    Never escapes `call` — it becomes `None`, which downstream reads as
    "unknown", which reads as UNCERTAIN. That chain is deliberate: the one
    outcome a tool must never produce is a confident wrong answer.
    """


def call(
    fn: Callable[[], ToolResult[T] | None],
    *,
    on_result: Callable[[ToolResult[Any]], None] | None = None,
) -> ToolResult[T] | None:
    """Run a provider, time it, and never let it raise into the planner.

    `on_result` is how the runner hears about the call — it writes the ledger
    row and publishes the event. Passing it is optional so the tools stay
    usable from a test or a script with no world attached.
    """
    started = perf_counter()
    try:
        result = fn()
    except ToolUnavailable as exc:
        logger.info("tool unavailable: %s", exc)
        return None
    except Exception:  # noqa: BLE001 — a bad tool must not stop a plan
        logger.exception("tool raised; treating as unknown")
        return None

    if result is None:
        return None

    timed = result.with_timing((perf_counter() - started) * 1000)
    if on_result is not None:
        on_result(timed)
    return timed
