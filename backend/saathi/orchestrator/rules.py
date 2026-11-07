"""Rules for a journey's dealings with the network. Triggers are code, never a model."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..domain.affordability import MEANS_SENSITIVE, Means, rank_of
from ..domain.directory import NEED_FOR_TYPE, Organisation
from ..domain.enums import ReadinessKind, StepKind
from ..domain.models import ReadinessItem
from ..domain.pathway import Pathway
from ..domain.policy import HospitalPolicy

#: What a hospital's rules say about stay-or-go when it has saved none.
DEFAULT_STAY_HOURS: float = HospitalPolicy.model_fields["stay_rather_than_travel_hours"].default


def needs_for(
    pathway: Pathway,
    target: StepKind,
    *,
    round_trip_hours: float | None,
    stay_threshold_hours: float,
) -> tuple[ReadinessKind, ...]:
    """The parties a journey to `target` depends on.

    A stay is dropped for a family close enough to go home between visits. When
    the journey is unknown the stay stays in: the cautious answer is the one that
    leaves nobody without a bed.
    """
    wanted = pathway.partner_needs.get(target, ())
    near = round_trip_hours is not None and round_trip_hours < stay_threshold_hours
    return tuple(k for k in wanted if not (k is ReadinessKind.STAY and near))


def missing_needs(
    needs: Iterable[ReadinessKind], items: Iterable[ReadinessItem]
) -> tuple[ReadinessKind, ...]:
    """The needs nobody has been asked about yet. Idempotent: ask once, not every plan."""
    asked = {i.kind for i in items}
    return tuple(k for k in needs if k not in asked)


def choose_organisation(
    kind: ReadinessKind,
    *,
    district: str,
    hospital_id: str,
    organisations: Sequence[Organisation],
    preferred_id: str | None = None,
    means: Means = Means.NOT_STATED,
) -> Organisation | None:
    """Who to ask for a need: the family's own choice, else the best fit.

    "Fits" means the right kind, active, serving the family's district and
    working with their hospital.

    Among those, what the family can carry comes first — but only for the needs
    they pay for out of pocket (`MEANS_SENSITIVE`). A ride and a bed are bought
    with the family's money, so a household on the lowest band is offered the
    railway desk before an app cab and a dharamshala before a hotel. A slot, a
    doctor and a bed inside the hospital are the hospital's to allocate, and
    ordering *those* by price would be a clinical decision wearing a logistics
    hat; for them the tier is ignored entirely.

    This reorders and never filters. Every organisation stays reachable, so a
    dharamshala with no beds still falls through to a lodge by the usual
    `alternate_id` chain.

    Below cost, the old rules stand: the more wanted kind, then the
    alphabetically first name, so the same inputs always choose the same
    organisation.
    """
    types = NEED_FOR_TYPE.get(kind.value, ())
    candidates = [o for o in organisations if o.active and o.type in types]
    if preferred_id is not None:
        chosen = next((o for o in candidates if o.id == preferred_id), None)
        if chosen is not None:
            return chosen
    place = district.strip().lower()
    fits = [
        o
        for o in candidates
        if (not o.districts or place in {d.lower() for d in o.districts})
        and (not o.hospital_ids or hospital_id in o.hospital_ids)
    ]
    pays = kind.value in MEANS_SENSITIVE

    def order(o: Organisation) -> tuple[int, int, str]:
        return (
            rank_of(o.cost_tier, means) if pays else 0,
            types.index(o.type),
            o.name.lower(),
        )

    return min(fits, key=order, default=None)
