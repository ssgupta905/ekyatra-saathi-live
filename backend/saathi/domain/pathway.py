"""Care pathways as data.

A pathway says what a kind of journey is made of: which steps exist, which must
come before which, which can share a trip, what a family carries and where they
go first. The planner reads a patient's pathway instead of module constants, so
a new condition is a new `Pathway` value, not a change to the planner.

Edges are logistical ordering, not clinical advice: they say which step's
*output* must exist before another step is worth a journey. Nothing here can
hold report content.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .enums import ReadinessKind, ResourceKind, StepKind

DEFAULT_PATHWAY_ID = "oncology"


class Recurrence(BaseModel):
    """A step that repeats on a fixed interval, and the doses that need a companion.

    A plain lookup, not a clinical judgement: whoever owns the regimen set the
    gated indices; this only remembers them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: StepKind
    interval_days: int
    #: None means open-ended (a dialysis schedule has no 17th session).
    total: int | None = None
    #: The step that must be bundled in before the gated indices.
    companion: StepKind | None = None
    gated_indices: frozenset[int] = frozenset()


class Pathway(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    #: (parent, child): the child requires the parent's output.
    edges: tuple[tuple[StepKind, StepKind], ...]
    #: Unordered pairs that can share a trip when both are due.
    co_locatable: tuple[frozenset[StepKind], ...] = ()
    #: Which kind of bookable resource a step needs, for matching a disruption.
    resource_requirements: dict[StepKind, ResourceKind] = {}
    #: What to carry for each step, beyond the common list. Logistics only.
    documents: dict[StepKind, tuple[str, ...]] = {}
    #: Which desk to reach first.
    first_stop: dict[StepKind, str] = {}
    #: The step a family is planned towards when none is chosen.
    default_target: StepKind = StepKind.REVIEW_CONSULT
    recurrence: Recurrence | None = None
    #: Which other parties a journey towards each step depends on. A stay is
    #: only asked for when the family lives far enough to need one.
    partner_needs: dict[StepKind, tuple[ReadinessKind, ...]] = {}

    @property
    def kinds(self) -> frozenset[StepKind]:
        return frozenset(
            kind for edge in self.edges for kind in edge
        ) | frozenset(self.first_stop) | frozenset(self.documents)

    def requires_companion(self, index: int) -> bool:
        rule = self.recurrence
        return bool(rule and rule.companion and index in rule.gated_indices)


#: Who a cancer journey leans on beyond the hospital: scheme, pharmacy, ride, a room.
_ONCOLOGY_PARTIES = (
    ReadinessKind.INSURANCE,
    ReadinessKind.MEDICINE,
    ReadinessKind.TRANSPORT,
    ReadinessKind.STAY,
)

ONCOLOGY = Pathway(
    id=DEFAULT_PATHWAY_ID,
    name="Solid-tumour pathway",
    edges=(
        (StepKind.CONSULT, StepKind.BIOPSY),
        (StepKind.CONSULT, StepKind.BLOODS),
        (StepKind.CONSULT, StepKind.SCAN),
        (StepKind.BIOPSY, StepKind.PATHOLOGY_REPORT),
        (StepKind.SCAN, StepKind.RADIOLOGY_REPORT),
        # The doctor's sketch: the PET-CT follows the MRI and its report, and
        # the joint clinic cannot sit before the PET-CT it exists to discuss.
        (StepKind.RADIOLOGY_REPORT, StepKind.PET_CT),
        (StepKind.PET_CT, StepKind.JOINT_CLINIC),
        (StepKind.REVIEW_CONSULT, StepKind.JOINT_CLINIC),
        (StepKind.PATHOLOGY_REPORT, StepKind.REVIEW_CONSULT),
        (StepKind.RADIOLOGY_REPORT, StepKind.REVIEW_CONSULT),
        (StepKind.BLOODS, StepKind.REVIEW_CONSULT),
        # Back on the spine via the review consult, not the joint clinic: the
        # joint clinic is a leaf. Putting it between the review and treatment
        # would make every patient in the cohort — none of whom have one on
        # record — fail `missing_prerequisite_kinds` and go UNCERTAIN.
        (StepKind.REVIEW_CONSULT, StepKind.TREATMENT),
        # Maintenance is a single repeating kind; the 21-day recurrence and the
        # per-dose echo gate are in `recurrence`, not in edges.
        (StepKind.TREATMENT, StepKind.MAINTENANCE_DOSE),
    ),
    co_locatable=(
        frozenset({StepKind.CONSULT, StepKind.BIOPSY}),
        frozenset({StepKind.CONSULT, StepKind.BLOODS}),
        frozenset({StepKind.BIOPSY, StepKind.BLOODS}),
        frozenset({StepKind.SCAN, StepKind.REVIEW_CONSULT}),
        # The pair the brief's option B turns on: the MRI at 8 am and the PET-CT
        # at 2 pm the same afternoon, one visit instead of two.
        frozenset({StepKind.SCAN, StepKind.PET_CT}),
        frozenset({StepKind.REVIEW_CONSULT, StepKind.JOINT_CLINIC}),
        frozenset({StepKind.BLOODS, StepKind.REVIEW_CONSULT}),
        frozenset({StepKind.MAINTENANCE_DOSE, StepKind.ECHO_REVIEW}),
    ),
    resource_requirements={
        StepKind.SCAN: ResourceKind.MACHINE,
        StepKind.ECHO_REVIEW: ResourceKind.STAFF,
        StepKind.MAINTENANCE_DOSE: ResourceKind.SUPPLY,
    },
    documents={
        StepKind.SCAN: ("scan request form", "previous scan films if you have them"),
        StepKind.BLOODS: ("blood test request form", "come without eating if told to"),
        StepKind.BIOPSY: ("biopsy consent form", "someone to travel back with you"),
        StepKind.REVIEW_CONSULT: ("all report slips collected so far",),
        StepKind.TREATMENT: ("admission letter", "payment or scheme documents"),
        StepKind.MAINTENANCE_DOSE: ("treatment card", "payment or scheme documents"),
        StepKind.ECHO_REVIEW: ("treatment card",),
    },
    first_stop={
        StepKind.CONSULT: "OPD registration counter",
        StepKind.BIOPSY: "OPD registration counter",
        StepKind.BLOODS: "sample collection counter",
        StepKind.SCAN: "radiology reception",
        StepKind.REVIEW_CONSULT: "OPD registration counter",
        StepKind.TREATMENT: "admission desk",
        StepKind.MAINTENANCE_DOSE: "day-care centre",
        StepKind.ECHO_REVIEW: "cardiology reception",
    },
    default_target=StepKind.REVIEW_CONSULT,
    partner_needs={
        StepKind.REVIEW_CONSULT: _ONCOLOGY_PARTIES,
        StepKind.TREATMENT: _ONCOLOGY_PARTIES,
        StepKind.MAINTENANCE_DOSE: _ONCOLOGY_PARTIES,
    },
    recurrence=Recurrence(
        kind=StepKind.MAINTENANCE_DOSE,
        interval_days=21,
        total=17,
        companion=StepKind.ECHO_REVIEW,
        gated_indices=frozenset({5, 9, 13, 17}),
    ),
)

#: Maintenance dialysis. The recurring session is the journey; a monthly bloods
#: visit and a nephrology review gate nothing about the session itself, but a
#: session cannot be planned until the patient has been reviewed once. The bloods
#: and the review share a trip so a monthly check is one journey, not two.
DIALYSIS = Pathway(
    id="dialysis",
    name="Maintenance dialysis",
    edges=(
        (StepKind.NEPHROLOGY_REVIEW, StepKind.DIALYSIS_SESSION),
        (StepKind.BLOODS, StepKind.NEPHROLOGY_REVIEW),
    ),
    co_locatable=(
        frozenset({StepKind.BLOODS, StepKind.NEPHROLOGY_REVIEW}),
        frozenset({StepKind.NEPHROLOGY_REVIEW, StepKind.DIALYSIS_SESSION}),
    ),
    resource_requirements={StepKind.DIALYSIS_SESSION: ResourceKind.MACHINE},
    documents={
        StepKind.DIALYSIS_SESSION: ("dialysis card", "payment or scheme documents"),
        StepKind.BLOODS: ("blood test request form",),
        StepKind.NEPHROLOGY_REVIEW: ("all report slips collected so far",),
    },
    first_stop={
        StepKind.DIALYSIS_SESSION: "dialysis unit reception",
        StepKind.BLOODS: "sample collection counter",
        StepKind.NEPHROLOGY_REVIEW: "OPD registration counter",
    },
    default_target=StepKind.DIALYSIS_SESSION,
    partner_needs={StepKind.DIALYSIS_SESSION: (ReadinessKind.TRANSPORT, ReadinessKind.STAY)},
    recurrence=Recurrence(kind=StepKind.DIALYSIS_SESSION, interval_days=2),
)

#: The weeks after a hospital stay: a first review, a wound/dressing visit that
#: can share its trip, and bloods before the review.
POST_DISCHARGE = Pathway(
    id="post_discharge",
    name="Recovery after discharge",
    edges=(
        (StepKind.BLOODS, StepKind.DISCHARGE_REVIEW),
        (StepKind.WOUND_CHECK, StepKind.DISCHARGE_REVIEW),
    ),
    co_locatable=(
        frozenset({StepKind.BLOODS, StepKind.WOUND_CHECK}),
        frozenset({StepKind.BLOODS, StepKind.DISCHARGE_REVIEW}),
        frozenset({StepKind.WOUND_CHECK, StepKind.DISCHARGE_REVIEW}),
    ),
    documents={
        StepKind.DISCHARGE_REVIEW: ("discharge summary", "all medicine strips and slips"),
        StepKind.WOUND_CHECK: ("discharge summary",),
        StepKind.BLOODS: ("blood test request form",),
    },
    first_stop={
        StepKind.DISCHARGE_REVIEW: "OPD registration counter",
        StepKind.WOUND_CHECK: "dressing room",
        StepKind.BLOODS: "sample collection counter",
    },
    default_target=StepKind.DISCHARGE_REVIEW,
    partner_needs={
        StepKind.DISCHARGE_REVIEW: (ReadinessKind.MEDICINE, ReadinessKind.TRANSPORT),
    },
)

PATHWAYS: dict[str, Pathway] = {p.id: p for p in (ONCOLOGY, DIALYSIS, POST_DISCHARGE)}


def get_pathway(pathway_id: str | None) -> Pathway:
    """A patient's pathway. An unknown id is an error, not a silent oncology."""
    try:
        return PATHWAYS[pathway_id or DEFAULT_PATHWAY_ID]
    except KeyError:
        raise KeyError(f"unknown pathway {pathway_id!r}") from None
