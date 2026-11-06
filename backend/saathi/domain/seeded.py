"""Which records exist only to fill a screen.

Demonstration data and real records live side by side in the same database, so
something has to tell them apart. Two things do, and both are facts about the
record rather than flags somebody has to remember to set:

* the synthetic cohort has **no name**, because nobody entered one;
* the showcase families carry a reserved **id prefix**.

A family the hospital actually entered has neither property, and is treated as
real everywhere — written to, planned for, counted.
"""

from __future__ import annotations

#: Reserved for the showcase families seeded into an empty deployment.
SHOWCASE_PREFIX = "SHOW-"


def is_seed_data(patient_id: str, name: str) -> bool:
    """True for a record no one entered and no one is looking after."""
    return not name or patient_id.startswith(SHOWCASE_PREFIX)
