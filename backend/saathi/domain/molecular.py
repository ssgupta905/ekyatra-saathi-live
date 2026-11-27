"""A register of the molecular reports a patient has had, and nothing more.

**What this is not.** It is not a variant store, it does not parse a report,
and it never says what one means. There is no interpretation here and there
must never be: `language/guard.py` refuses clinical claims for a reason, and a
system that told a family what an EGFR result implied would be practising
medicine through a logistics app.

**Why it exists anyway.** A molecular panel in India is ordered — often at an
outside lab — and comes back as a PDF. It is handed over, emailed, sometimes
scanned into the chart. No hospital system in this project's reach holds the
structured result: OpenEMR has no genomics resource at all, and asking its
FHIR API for `MolecularSequence` returns a 404 because the route does not
exist. So the honest thing to hold is not the science. It is the *fact* of the
test: which panel, when, which lab, did the report come back, and where the
document is.

That fact is worth holding because losing it costs a family real money. A
patient moving from a district hospital to a tertiary centre is routinely
re-tested because nobody can find the panel done three months earlier —
twenty-five to eighty thousand rupees and several weeks, in a household
counting a nine-hundred-rupee bus fare. "This was done at Tata in March, here
is the report" is the whole value, and it is a logistics fact, not a clinical
one.

**It sits outside the logistics layer.** The planner must never read this. A
re-plan that moved a visit because of something in a molecular report would be
a clinical decision wearing a scheduling costume. `tests/test_architecture.py`
enforces the separation rather than trusting it.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field

from .models import Base


class MolecularTest(StrEnum):
    """The kinds of test this register knows how to name.

    Deliberately coarse. The register records *that* a panel was done, so the
    distinctions that matter are the ones a doctor at the next centre would
    ask about before ordering a repeat — not the assay's full taxonomy.
    """

    KARYOTYPE = "karyotype"
    FISH = "fish"
    IHC = "ihc"
    SINGLE_GENE = "single_gene"
    TARGETED_PANEL = "targeted_panel"
    EXOME = "exome"
    GENOME = "genome"
    TRANSCRIPTOME = "transcriptome"
    PROTEOMIC = "proteomic"
    OTHER = "other"


#: How each reads to a person, so the API, the Console and any future app
#: cannot describe the same test three different ways.
TEST_NAMES: dict[MolecularTest, str] = {
    MolecularTest.KARYOTYPE: "Karyotyping",
    MolecularTest.FISH: "FISH",
    MolecularTest.IHC: "Immunohistochemistry",
    MolecularTest.SINGLE_GENE: "Single-gene test",
    MolecularTest.TARGETED_PANEL: "Targeted panel",
    MolecularTest.EXOME: "Exome sequencing",
    MolecularTest.GENOME: "Genome sequencing",
    MolecularTest.TRANSCRIPTOME: "Transcriptomic panel",
    MolecularTest.PROTEOMIC: "Proteomic panel",
    MolecularTest.OTHER: "Molecular test",
}


class ReportState(StrEnum):
    """Where the report is, which is the only state worth tracking."""

    #: Ordered; nothing back.
    AWAITED = "awaited"
    #: The report exists and the register knows where.
    HELD = "held"
    #: The report exists somewhere, but not anywhere we can point to. Said out
    #: loud rather than left blank, because "we do not have it" is exactly the
    #: fact that stops a second centre assuming it can be fetched.
    ELSEWHERE = "elsewhere"


class MolecularReport(Base):
    """One test, and where its report is. No result, ever."""

    id: str
    patient_id: str
    test: MolecularTest
    state: ReportState

    #: Who ran it. Usually not the treating hospital — most panels go out.
    lab_name: str = Field(default="", max_length=200)
    #: The centre that ordered it, so a doctor knows whom to ask.
    ordered_by_centre: str = Field(default="", max_length=200)

    ordered_on: date | None = None
    reported_on: date | None = None

    #: Where the document lives — a FHIR `DocumentReference` id, a hospital
    #: record number, or a note saying the family holds the paper copy. A
    #: pointer, never the contents.
    document_ref: str = Field(default="", max_length=400)

    #: Free text from whoever entered it, for things the fields cannot hold.
    #: Screened the same way a family's message is: no result may be written
    #: here, and `api/molecular.py` refuses one.
    note: str = Field(default="", max_length=400)

    recorded_at: datetime
    recorded_by: str = Field(default="", max_length=120)

    @property
    def still_waiting(self) -> bool:
        return self.state is ReportState.AWAITED

    @property
    def can_be_fetched(self) -> bool:
        """Whether a second centre could actually get hold of this."""
        return self.state is ReportState.HELD and bool(self.document_ref)

    def summary(self) -> str:
        """One line for a doctor's list."""
        name = TEST_NAMES.get(self.test, self.test.value)
        where = f" at {self.lab_name}" if self.lab_name else ""
        when = f", {self.reported_on:%b %Y}" if self.reported_on else (
            f", ordered {self.ordered_on:%b %Y}" if self.ordered_on else ""
        )
        if self.state is ReportState.AWAITED:
            return f"{name}{where}{when} — not back yet"
        if self.state is ReportState.ELSEWHERE:
            return f"{name}{where}{when} — report not held here"
        return f"{name}{where}{when}"


#: Words that would make this a result rather than a record of one. A register
#: that quietly accumulated findings in its note field would become the thing
#: this module says it is not, one well-meaning entry at a time.
RESULT_WORDS: frozenset[str] = frozenset(
    {
        "positive", "negative", "mutation", "variant", "amplified", "deleted",
        "fusion", "wild type", "wildtype", "detected", "not detected",
        "pathogenic", "benign", "vus", "allele", "expression", "overexpressed",
        "msi", "tmb", "her2", "egfr", "alk", "ros1", "braf", "kras", "brca",
    }
)


def reads_like_a_result(text: str) -> str | None:
    """The first result-ish word in this text, or None.

    Used to refuse a note that is trying to be a finding. Crude on purpose: a
    false refusal costs somebody a rephrase, and a false accept puts a clinical
    claim in a logistics system.
    """
    lowered = f" {text.lower()} "
    for word in sorted(RESULT_WORDS):
        if f" {word} " in lowered or f" {word}." in lowered or f" {word}," in lowered:
            return word
    return None
