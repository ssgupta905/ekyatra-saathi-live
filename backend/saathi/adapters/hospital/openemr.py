"""OpenEMR: FHIR for everything it projects, and a read-only view for one thing it does not.

`FhirHospital` already answers four of the five questions this project asks an
HMS — appointments, services, who is away, what is outstanding — because
OpenEMR projects all of them over FHIR R4. The fifth, how far behind the
clinic is running, is not projected at all: the status change is, the
timestamp is not, and "Arrived" and "Arrived late" collapse onto the same FHIR
status. See `ports/clinic_flow.py`.

So this is `FhirHospital` plus an optional read-only database handle, and the
only reason it is a class rather than a configuration flag is that callers
should get one object that either can answer the question or says it cannot.
The alternative — a connector that holds a hospital and separately maybe holds
a database — pushes that "maybe" into every call site.

**The database half is optional and failure is `None`.** A deployment that
does not configure it, or whose database is unreachable, reports that a family
arrived and claims no delay. That is the honest outcome: a family rearranges
their day around a delay, and a guessed one is worse than none.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ...ports.clinic_flow import ClinicFlow
from .fhir import FhirHospital
from .openemr_db import OpenEMRDatabase


class OpenEMRHospital(FhirHospital):
    """One adapter for everything OpenEMR can be asked."""

    name = "openemr"

    def __init__(self, *, flow: OpenEMRDatabase | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._flow = flow

    def clinic_flow(self, *, on: date) -> ClinicFlow | None:
        """How today is running, or None when nothing here can tell us."""
        if self._flow is None:
            return None
        return self._flow.clinic_flow(on=on)

    @property
    def reads_arrival_times(self) -> bool:
        """Whether the delay is readable at all, for the Console's banner.

        Worth surfacing rather than inferring from an absent number: "we
        cannot read arrival times here" and "nobody has arrived yet" look
        identical on a screen and mean entirely different things.
        """
        return self._flow is not None

    def describe(self) -> str:
        """One line for `GET /api/live`, saying what this connection can do."""
        if self._flow is None:
            return "openemr (fhir; no arrival times)"
        return "openemr (fhir + read-only arrival times)"


__all__ = ["OpenEMRHospital"]
