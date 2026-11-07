"""A made-up network to onboard against: about thirty organisations in five cities.

Invented for the demonstration. Nothing here is a real business; the names are
generic on purpose. Entered through the same store an administrator's additions
go to, so from then on they are ordinary records.
"""

from __future__ import annotations

import logging

from ..domain.affordability import CostTier
from ..domain.directory import Organisation, OrgType, PartnerMode
from ..ports.registry import RegistryStore

logger = logging.getLogger(__name__)

_MUM = ("TMH-MUM",)


def _org(id, name, type_, *, services=(), districts=(), hospitals=(), contact="", hours="",
         delay=30, alternate=None, linked=(), address="", cost=CostTier.STANDARD):
    return Organisation(
        id=id, name=name, type=type_, services=tuple(services), districts=tuple(districts),
        hospital_ids=tuple(hospitals), address=address, contact=contact, hours=hours,
        mode=PartnerMode.SIMULATED, answer="ready", delay_seconds=delay,
        alternate_id=alternate, linked_ids=tuple(linked), cost_tier=cost,
    )


#: Shorthands, so the tier reads as a word at each entry rather than a constant.
_SUBSIDISED = CostTier.SUBSIDISED
_MODEST = CostTier.MODEST


DEMO_DIRECTORY: tuple[Organisation, ...] = (
    # ---- hospitals: the slot, the doctor and the bed a visit depends on
    _org("hosp-tmh-mum", "Tata Memorial Hospital, Mumbai", OrgType.HOSPITAL,
         services=("outpatient slots", "consultants", "day-care beds"), districts=("Mumbai",),
         hospitals=_MUM, delay=20, hours="8am to 6pm"),
    _org("hosp-hbch-mzp", "Homi Bhabha Cancer Hospital, Muzaffarpur", OrgType.HOSPITAL,
         services=("outpatient slots", "consultants"), districts=("Muzaffarpur",),
         hospitals=("HBCH-MZP",), delay=20),
    # ---- labs and diagnostic centres
    _org("lab-tmh-path", "Hospital pathology lab, Mumbai", OrgType.LAB,
         services=("pathology", "blood tests"), districts=("Mumbai",), hospitals=_MUM,
         hours="7am to 7pm", contact="022 5550 0101"),
    _org("lab-metro-mum", "Metro Diagnostics, Parel", OrgType.LAB,
         services=("MRI", "CT", "PET", "blood tests"), districts=("Mumbai",), hospitals=_MUM,
         hours="6am to 10pm", contact="022 5550 0102"),
    _org("lab-pathcare-patna", "Pathcare Labs, Patna", OrgType.LAB,
         services=("blood tests", "pathology"), districts=("Patna", "Gaya"), hours="7am to 8pm"),
    _org("lab-eastscan-kol", "East Scan Centre, Kolkata", OrgType.LAB,
         services=("MRI", "CT", "blood tests"), districts=("Kolkata", "Nadia", "Murshidabad")),
    _org("lab-cuttack-diag", "Cuttack Diagnostic Centre", OrgType.LAB,
         services=("blood tests", "ultrasound"), districts=("Cuttack", "Balasore")),
    # ---- pharmacies
    _org("ph-daycare-mum", "Day-care pharmacy, Mumbai", OrgType.PHARMACY,
         services=("hospital supplies", "home delivery"), districts=("Mumbai",), hospitals=_MUM,
         delay=60, alternate="ph-wellmed-mum", linked=("md-westcare",)),
    _org("ph-wellmed-mum", "WellMed Pharmacy, Parel", OrgType.PHARMACY,
         services=("home delivery",), districts=("Mumbai",), hospitals=_MUM,
         linked=("md-westcare",)),
    _org("ph-medplus-patna", "MedPlus, Patna", OrgType.PHARMACY,
         services=("home delivery",), districts=("Patna",), linked=("md-eastern",)),
    _org("ph-janaushadhi-gaya", "Jan Aushadhi Kendra, Gaya", OrgType.PHARMACY,
         services=("generic supplies",), districts=("Gaya",), linked=("md-eastern",),
         cost=_SUBSIDISED),
    _org("ph-janaushadhi-mum", "Jan Aushadhi Kendra, Parel", OrgType.PHARMACY,
         services=("generic supplies",), districts=("Mumbai",), hospitals=_MUM,
         linked=("md-westcare",), cost=_SUBSIDISED),
    _org("ph-generic-patna", "Generic Medical Store, Patna", OrgType.PHARMACY,
         services=("generic supplies",), districts=("Patna", "Gaya"),
         linked=("md-eastern",), cost=_MODEST),
    _org("ph-wellness-cuttack", "Wellness Pharmacy, Cuttack", OrgType.PHARMACY,
         districts=("Cuttack",), linked=("md-eastern",)),
    # ---- medicine and equipment distributors (upstream; families never see them)
    _org("md-westcare", "WestCare Medicine Distributors", OrgType.MEDICINE_DISTRIBUTOR,
         services=("cold chain", "bulk supply"), districts=("Mumbai", "Pune")),
    _org("md-eastern", "Eastern Pharma Distribution", OrgType.MEDICINE_DISTRIBUTOR,
         services=("bulk supply",), districts=("Kolkata", "Patna", "Cuttack")),
    _org("eq-meditech-mum", "MediTech Equipment, Mumbai", OrgType.EQUIPMENT_DISTRIBUTOR,
         services=("wheelchairs", "oxygen", "dialysis supplies"), districts=("Mumbai",)),
    _org("eq-biomed-patna", "BioMed Supplies, Patna", OrgType.EQUIPMENT_DISTRIBUTOR,
         services=("wheelchairs", "oxygen"), districts=("Patna", "Gaya")),
    # ---- shops and merchants
    _org("sh-medmart-mum", "MedMart, Parel", OrgType.SHOP,
         services=("dressings", "hygiene supplies"), districts=("Mumbai",)),
    _org("sh-careneeds-patna", "Care Needs Store, Patna", OrgType.SHOP,
         services=("dressings", "hygiene supplies"), districts=("Patna",)),
    # ---- cab services. All market rate: this is what a family pays for when
    # nothing cheaper will do, not the first thing to reach for.
    _org("cab-uber", "Uber", OrgType.CAB, services=("pickup", "airport pickup"),
         districts=("Mumbai", "Patna", "Kolkata"), delay=30, alternate="cab-ola"),
    _org("cab-ola", "Ola", OrgType.CAB, services=("pickup",),
         districts=("Mumbai", "Patna", "Kolkata"), delay=30, alternate="cab-meru-mum"),
    _org("cab-meru-mum", "Meru Cabs, Mumbai", OrgType.CAB, services=("pickup", "station pickup"),
         districts=("Mumbai",), hospitals=_MUM),
    _org("cab-regional", "Regional taxi network", OrgType.CAB,
         services=("pickup from any district",), delay=40),
    _org("cab-saarthi-patna", "Saarthi Taxi, Patna", OrgType.CAB, services=("pickup",),
         districts=("Patna", "Gaya")),
    # ---- shared and public transport, which is how most of these families
    # actually travel. A 600km journey by app cab is not a plan.
    _org("tr-shared-jeep-gaya", "Shared jeep stand, Gaya", OrgType.CAB,
         services=("shared seats to the station",), districts=("Gaya", "Patna"),
         delay=35, cost=_MODEST),
    # ---- travel partners
    # Tied to no district, because the railway is not. Listing five cities here
    # is how the first version of this quietly failed: every family outside
    # them fell through to the one unrestricted option, which was a taxi.
    _org("tr-rail-assist", "Railway booking desk", OrgType.TRAVEL,
         services=("rail tickets", "sleeper class", "senior and patient quota"),
         delay=45, alternate="tr-bus-assist", cost=_MODEST),
    _org("tr-rail-quota", "Railway patient quota desk", OrgType.TRAVEL,
         services=("patient and escort quota", "concession on a medical certificate"),
         delay=60, alternate="tr-rail-assist", cost=_SUBSIDISED),
    _org("tr-bus-assist", "State bus booking desk", OrgType.TRAVEL, services=("bus tickets",),
         districts=("Patna", "Gaya", "Cuttack"), delay=45, cost=_MODEST),
    # ---- hotels and stays, cheapest first in the fall-back chain
    _org("ho-oyo-parel", "OYO, Parel", OrgType.HOTEL, services=("rooms near the hospital",),
         districts=("Mumbai",), hospitals=_MUM, delay=45, alternate="ho-treebo-dadar"),
    _org("ho-treebo-dadar", "Treebo, Dadar", OrgType.HOTEL, services=("rooms",),
         districts=("Mumbai",), hospitals=_MUM, delay=45, alternate="ho-lodge-parel"),
    _org("ho-lodge-parel", "Parel Guest House", OrgType.HOTEL,
         services=("shared rooms", "kitchen for attendants"), districts=("Mumbai",),
         hospitals=_MUM, delay=45, alternate="ho-dharamshala-parel", cost=_MODEST),
    _org("ho-dharamshala-parel", "Patient dharamshala, Parel", OrgType.HOTEL,
         services=("low-cost beds for patients", "beds for one attendant"),
         districts=("Mumbai",), hospitals=_MUM, cost=_SUBSIDISED),
    _org("ho-sewa-sadan-mum", "Sewa Sadan patient shelter, Mumbai", OrgType.HOTEL,
         services=("free beds for patients on treatment",), districts=("Mumbai",),
         hospitals=_MUM, delay=70, cost=_SUBSIDISED),
    _org("ho-lodge-patna", "Station Road Lodge, Patna", OrgType.HOTEL, districts=("Patna",),
         cost=_MODEST),
    # ---- insurers and scheme desks
    _org("in-pmjay-desk", "PM-JAY help desk", OrgType.INSURER,
         services=("scheme pre-authorisation",), districts=("Mumbai", "Patna", "Gaya"),
         delay=90, alternate="in-state-scheme"),
    _org("in-state-scheme", "State health scheme desk", OrgType.INSURER,
         services=("scheme pre-authorisation",), delay=90),
    _org("in-starcare", "StarCare Health Insurance", OrgType.INSURER,
         services=("cashless pre-authorisation",), delay=120),
    # ---- ambulance
    _org("am-108-mum", "108 Ambulance, Mumbai", OrgType.AMBULANCE, districts=("Mumbai",),
         contact="108"),
    _org("am-patna", "Patna Patient Transport", OrgType.AMBULANCE, districts=("Patna", "Gaya")),
)


def seed_directory(store: RegistryStore) -> bool:
    """Add any demonstration organisation the directory does not have yet.

    Additive by id: an organisation that is already there is never touched, so an
    administrator's edits stand, and a database seeded before an entry existed
    picks it up. True when it added anything.
    """
    have = {o.id for o in store.organisations()}
    missing = [o for o in DEMO_DIRECTORY if o.id not in have]
    for organisation in missing:
        store.save_organisation(organisation)
    if missing:
        logger.info("added %d demonstration organisations to the directory", len(missing))
    return bool(missing)
