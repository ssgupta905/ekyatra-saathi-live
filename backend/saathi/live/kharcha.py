"""Kharcha: keeping a family's journey costs, with nobody at the hospital in the loop.

The desk does the bookkeeping a family has no time for. It records what a
provider says it charged or was paid, reads the family's own "₹450 auto" into
an entry they confirm with one tap, works out what this month and the next
will cost from those figures alone, points out what might make it cheaper, and
— only when the month looks like more than the family said they can manage —
tells the social-work desk that someone should call. That alert carries no
amounts: a person reading it learns that help is needed, not what this
household spends.

Nothing here moves money. A provider collects its own fare through its own
link; what arrives here is the provider's word that it was paid.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from ..domain.affordability import CostTier
from ..domain.directory import OrgType
from ..domain.enums import AlertKind, ReadinessKind, SourceSystem, StepStatus
from ..domain.models import Alert
from ..domain.pathway import get_pathway
from ..domain.profile import DocumentKind
from ..domain.spends import (
    CoveredBy,
    MonthOutlook,
    Nudge,
    SpendCategory,
    SpendEntry,
    SpendSource,
    SpendStatus,
    StatedLimit,
)
from ..orchestrator.kharcha import month_of, next_month, nudges, outlook, read_spend, visits_ahead
from ..ports.ledger import EvidenceLedger
from ..ports.onboarding import OnboardingStore
from ..ports.registry import RegistryStore
from ..ports.spends import SpendStore
from .world import LiveWorld

logger = logging.getLogger(__name__)

#: Which need a provider's figure belongs to, for the three the family pays for itself.
CATEGORY_FOR_NEED: dict[ReadinessKind, SpendCategory] = {
    ReadinessKind.TRANSPORT: SpendCategory.TRAVEL,
    ReadinessKind.STAY: SpendCategory.STAY,
    ReadinessKind.MEDICINE: SpendCategory.MEDICINE,
}

#: How far from a visit a spend may be and still count as part of that trip.
_TRIP_REACH = timedelta(days=7)


class NotReadable(ValueError):
    """The family's words did not say an amount clearly enough to record."""


@dataclass
class KharchaDesk:
    store: SpendStore
    world: LiveWorld
    ledger: EvidenceLedger
    registry: RegistryStore | None = None
    onboarding: OnboardingStore | None = None
    #: The runner's alert list; the only thing staff ever see from here.
    alerts: list = field(default_factory=list)
    now: Callable[[], datetime] = lambda: datetime.now(UTC)

    # ---------------------------------------------------------------- recording

    def _today(self) -> date:
        return self.world.today

    def _record(self, entry: SpendEntry, source: SourceSystem, claim: str) -> SpendEntry:
        saved = self.store.save(entry)
        # The ledger proves an entry existed and who gave it; it never holds the
        # figure. The hash makes a later edit to the amount evident.
        fingerprint = hashlib.sha256(f"{entry.amount_paise}|{entry.id}".encode()).hexdigest()
        self.ledger.record_once(
            entry.patient_id,
            source=source,
            source_record_id=f"spend:{entry.id}:{entry.status.value}",
            claim=claim,
            metadata={"fingerprint": fingerprint, "source": entry.source.value},
        )
        return saved

    def note_from_family(
        self,
        patient_id: str,
        *,
        text: str = "",
        amount_paise: int | None = None,
        category: SpendCategory | None = None,
        on: date | None = None,
    ) -> SpendEntry:
        """What the family said or typed, as a proposed entry they then confirm.

        Typed fields win over what is read from the words; the words are kept
        either way, because they are the reason the figure may be shown.
        """
        read_amount, read_category = read_spend(text) if text else (None, None)
        amount = amount_paise or read_amount
        if amount is None:
            raise NotReadable("say or type the amount")
        said = (
            text.strip()
            or f"{amount // 100} ({(category or read_category or SpendCategory.OTHER).value})"
        )
        day = on or self._today()
        entry = SpendEntry(
            id=f"sp-{patient_id}-{uuid4().hex[:10]}",
            patient_id=patient_id,
            category=category or read_category or SpendCategory.OTHER,
            amount_paise=amount,
            status=SpendStatus.PROPOSED,
            source=SpendSource.FAMILY_STATED,
            stated_in=said[:400],
            on=day,
            visit_on=self._visit_for(patient_id, day),
        )
        return self.store.save(entry)

    def confirm(self, patient_id: str, entry_id: str) -> SpendEntry | None:
        """The family taps "yes, that's right". Their own entry becomes money spent."""
        entry = self.store.get(patient_id, entry_id)
        if entry is None or entry.status is not SpendStatus.PROPOSED:
            return entry
        paid = entry.model_copy(update={"status": SpendStatus.PAID})
        saved = self._record(
            paid,
            SourceSystem.CAREGIVER_REPLY,
            f"the family confirmed a {paid.category.value} spend",
        )
        self.review(patient_id)
        return saved

    def void(self, patient_id: str, entry_id: str) -> SpendEntry | None:
        entry = self.store.get(patient_id, entry_id)
        if entry is None or entry.status is SpendStatus.VOID:
            return entry
        gone = entry.model_copy(update={"status": SpendStatus.VOID})
        saved = self._record(
            gone, SourceSystem.CAREGIVER_REPLY, f"the family withdrew a {gone.category.value} spend"
        )
        self.review(patient_id)
        return saved

    def from_provider(
        self,
        patient_id: str,
        *,
        source: SpendSource,
        source_ref: str,
        amount_paise: int,
        category: SpendCategory,
        status: SpendStatus,
        party: str | None = None,
        organisation_id: str | None = None,
        on: date | None = None,
        covered_by: CoveredBy = CoveredBy.UNKNOWN,
    ) -> SpendEntry:
        """A figure a provider gave: a quote, a payment it received, a bill.

        Idempotent on the provider's own reference, so a webhook delivered twice
        is one spend, and a quote that is later paid moves to paid in place.
        """
        day = on or self._today()
        existing = self.store.by_source(source, source_ref)
        if existing is not None and existing.status is status:
            return existing
        entry = (
            existing
            or SpendEntry(
                id=f"sp-{patient_id}-{uuid4().hex[:10]}",
                patient_id=patient_id,
                category=category,
                amount_paise=amount_paise,
                status=status,
                source=source,
                source_ref=source_ref,
                covered_by=covered_by,
                on=day,
                visit_on=self._visit_for(patient_id, day),
                organisation_id=organisation_id,
                party=party,
            )
        ).model_copy(update={"status": status, "amount_paise": amount_paise})
        ledger_source = (
            SourceSystem.HOSPITAL_FEED
            if source is SpendSource.HOSPITAL_BILL
            else SourceSystem.PARTNER
        )
        saved = self._record(
            entry,
            ledger_source,
            f"{party or 'a provider'} reported a {category.value} amount as {status.value}",
        )
        self.review(patient_id)
        return saved

    def set_limit(self, patient_id: str, monthly_paise: int, stated_in: str) -> StatedLimit:
        limit = StatedLimit(patient_id=patient_id, monthly_paise=monthly_paise, stated_in=stated_in)
        self.store.save_limit(limit)
        self.review(patient_id)
        return limit

    # ---------------------------------------------------------------- the visits

    def _kinds(self, patient_id: str):
        """(pathway, the step a trip is for now, the step that repeats if any)."""
        patient = self.world.patient(patient_id)
        pathway = get_pathway(patient.pathway_id if patient else None)
        repeats = pathway.recurrence.kind if pathway.recurrence is not None else None
        return pathway, self.world.target_kind_for(patient_id), repeats

    def _visit_dates(self, patient_id: str, kinds) -> tuple[list[date], list[date]]:
        """(done, booked) dates of this family's visits of these kinds."""
        done, booked = [], []
        for step in self.world.steps_for(patient_id):
            if step.kind not in kinds:
                continue
            if step.status in (StepStatus.COMPLETED, StepStatus.RESULT_AVAILABLE):
                if step.completed_on or step.scheduled_for:
                    done.append(step.completed_on or step.scheduled_for)
            elif step.scheduled_for:
                booked.append(step.scheduled_for)
        return done, booked

    def _visit_for(self, patient_id: str, day: date) -> date | None:
        _, target, repeats = self._kinds(patient_id)
        done, booked = self._visit_dates(patient_id, {target, repeats} - {None})
        near = [v for v in (*done, *booked) if abs((v - day).days) <= _TRIP_REACH.days]
        return min(near, key=lambda v: abs((v - day).days)) if near else None

    def _ahead(self, patient_id: str, start: date, end: date) -> tuple[date, ...]:
        """Booked visits of either kind, then the regimen's rhythm from its own last session."""
        pathway, target, repeats = self._kinds(patient_id)
        _, booked = self._visit_dates(patient_id, {target})
        days = set(
            visits_ahead(
                scheduled=booked, last_visit=None, interval_days=None, remaining=None,
                start=start, end=end,
            )
        )  # fmt: skip
        rec = pathway.recurrence
        if rec is not None and repeats is not None:
            done_r, booked_r = self._visit_dates(patient_id, {repeats})
            remaining = None
            if rec.total is not None:
                remaining = max(rec.total - len(done_r) - len(booked_r), 0)
            days |= set(
                visits_ahead(
                    scheduled=booked_r,
                    last_visit=max(done_r) if done_r else None,
                    interval_days=rec.interval_days,
                    remaining=remaining,
                    start=start,
                    end=end,
                )
            )
        return tuple(sorted(days))

    # ---------------------------------------------------------------- reading the month

    def months(self, patient_id: str) -> tuple[MonthOutlook, MonthOutlook]:
        today = self._today()
        entries = self.store.entries(patient_id)
        this_first, _ = month_of(today)
        following = next_month(today)
        _, following_last = month_of(following)
        visits = self._ahead(patient_id, today, following_last)
        return (
            outlook(entries, month=this_first, today=today, visits=visits),
            outlook(entries, month=following, today=today, visits=visits),
        )

    def over_limit(self, patient_id: str, month: MonthOutlook | None = None) -> bool:
        limit = self.store.limit(patient_id)
        if limit is None:
            return False
        month = month or self.months(patient_id)[0]
        return month.total_known_paise > limit.monthly_paise

    def suggestions(self, patient_id: str, month: MonthOutlook | None = None) -> tuple[Nudge, ...]:
        patient = self.world.patient(patient_id)
        if patient is None:
            return ()
        return nudges(
            self.store.entries(patient_id),
            today=self._today(),
            subsidised_stay=self._subsidised_stay(patient.hospital_id),
            has_scheme_card=self._has_scheme_card(patient_id),
            on_cancer_pathway=(patient.pathway_id or "oncology") == "oncology",
            over_limit=self.over_limit(patient_id, month),
        )

    def _subsidised_stay(self, hospital_id: str) -> tuple[str, str] | None:
        if self.registry is None:
            return None
        hospital = next((h for h in self.registry.hospitals() if h.id == hospital_id), None)
        place = (hospital.place if hospital else "").lower()
        for org in self.registry.organisations():
            serves = (hospital_id in org.hospital_ids) or (
                not org.hospital_ids and place in {d.lower() for d in org.districts}
            )
            if (
                org.active
                and org.type is OrgType.HOTEL
                and org.cost_tier is CostTier.SUBSIDISED
                and serves
            ):
                return org.id, org.name
        return None

    def _has_scheme_card(self, patient_id: str) -> bool:
        if self.onboarding is None:
            return True  # nobody has asked; do not suggest a card they may well hold
        return any(
            d.kind is DocumentKind.SCHEME_CARD for d in self.onboarding.documents(patient_id)
        )

    # ---------------------------------------------------------------- the safety net

    def review(self, patient_id: str) -> bool:
        """Tell the social-work desk when the month is more than the family said. True if it did.

        Once a month per family, and with no figure in it: the person who calls
        needs to know help is wanted, not what this household spends.
        """
        month = self.months(patient_id)[0]
        if not self.over_limit(patient_id, month):
            return False
        alert_id = f"alert-{patient_id}-kharcha-{month.month:%Y-%m}"
        if any(getattr(a, "id", None) == alert_id for a in self.alerts):
            return False
        self.alerts.append(
            Alert(
                id=alert_id,
                patient_id=patient_id,
                kind=AlertKind.NEEDS_HELP,
                raised_at=self.now(),
                detail=(
                    "this month's journey costs look like more than the family said "
                    "they can manage"
                ),
            )
        )
        return True

    def sweep(self) -> int:
        """Look at every family with anything recorded; a new month is enough to matter."""
        return sum(1 for patient_id in self.store.patients() if self.review(patient_id))

    async def run(self, every_seconds: float = 600.0) -> None:
        while True:
            try:
                await asyncio.to_thread(self.sweep)
                await asyncio.sleep(every_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one family's books must not stop the rest
                logger.exception("kharcha sweep failed; continuing")
                await asyncio.sleep(every_seconds)


__all__ = ["CATEGORY_FOR_NEED", "KharchaDesk", "NotReadable"]
