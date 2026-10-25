"""What the registry starts with when nobody has filled it in yet.

Only things the system already knows: the hospitals named in configuration, and
— in the demo — the scripted families' clinicians and the district centres the
geo cache covers. A real deployment starts with its configured hospitals and
nothing invented on its behalf; everything else is entered by an administrator.
"""

from __future__ import annotations

from ..config import Settings
from ..domain.registry import Clinician, Hospital, NetworkCentre
from ..ports.registry import RegistryStore

#: Display names for the hospitals the demo is set at. A real registry gets its
#: names from the administrator who enters them.
DEMO_NAMES = {
    "TMH-MUM": "Tata Memorial Hospital, Mumbai",
    "HBCH-MZP": "Homi Bhabha Cancer Hospital, Muzaffarpur",
}

DEMO_DEPARTMENTS = {
    "TMH-MUM": ("radiology", "pathology", "head and neck surgery", "day_care"),
    "HBCH-MZP": ("cardiology", "medical oncology", "day_care"),
}

DEMO_CLINICIANS = (
    Clinician(id="dr-menon", name="Dr R. Menon", specialty="Head and neck surgery",
              hospital_id="TMH-MUM", department="head and neck surgery"),
    Clinician(id="dr-sinha", name="Dr Amrita Sinha", specialty="Medical oncology",
              hospital_id="HBCH-MZP", department="medical oncology", username="amrita"),
)  # fmt: skip


def _places(pairs: list[str]) -> list[tuple[str, str]]:
    out = []
    for pair in pairs:
        hospital_id, _, place = pair.partition("=")
        if hospital_id and place:
            out.append((hospital_id.strip(), place.strip()))
    return out


def seed_registry(store: RegistryStore, settings: Settings, *, demo: bool) -> None:
    if store.hospitals():
        return
    hospitals = _places(settings.hospital_places)
    for hospital_id, place in hospitals:
        store.save_hospital(
            Hospital(
                id=hospital_id,
                name=DEMO_NAMES.get(hospital_id, hospital_id) if demo else hospital_id,
                place=place,
                timezone=settings.hospital_timezone,
                departments=DEMO_DEPARTMENTS.get(hospital_id, ()) if demo else (),
            )
        )
    if not demo or not hospitals:
        return
    hub = hospitals[-1][0]
    for place in settings.centre_places:
        store.save_centre(
            NetworkCentre(
                id=f"dc-{place.lower()}",
                hospital_id=hub,
                name=f"District day-care centre, {place}",
                place=place,
                kind="day_care",
                handles=("bloods", "maintenance_dose"),
            )
        )
    for clinician in DEMO_CLINICIANS:
        store.save_clinician(clinician)
