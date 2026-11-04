"""Rules for a journey's dealings with the network. Triggers are code, never a model."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

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
) -> Organisation | None:
    """Who to ask for a need: the family's own choice, else the first that fits.

    "Fits" means the right kind, active, serving the family's district and working
    with their hospital. Ties go to the alphabetically first name, so the same
    inputs always choose the same organisation.
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
    return min(fits, key=lambda o: o.name.lower(), default=None)
