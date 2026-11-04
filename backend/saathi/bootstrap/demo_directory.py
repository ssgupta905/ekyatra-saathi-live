"""A made-up network to onboard against: about thirty organisations in five cities.

Invented for the demonstration. Nothing here is a real business; the names are
generic on purpose. Entered through the same store an administrator's additions
go to, so from then on they are ordinary records.
"""

from __future__ import annotations

import logging

from ..domain.directory import Organisation, OrgType, PartnerMode
from ..ports.registry import RegistryStore

logger = logging.getLogger(__name__)

_MUM = ("TMH-MUM",)


def _org(id, name, type_, *, services=(), districts=(), hospitals=(), contact="", hours="",
         delay=30, alternate=None, linked=(), address=""):
    return Organisation(
        id=id, name=name, type=type_, services=tuple(services), districts=tuple(districts),
        hospital_ids=tuple(hospitals), address=address, contact=contact, hours=hours,
        mode=PartnerMode.SIMULATED, answer="ready", delay_seconds=delay,
        alternate_id=alternate, linked_ids=tuple(linked),
    )


DEMO_DIRECTORY: tuple[Organisation, ...] = (
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
         services=("generic supplies",), districts=("Gaya",), linked=("md-eastern",)),
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
    # ---- cab services
    _org("cab-uber", "Uber", OrgType.CAB, services=("pickup", "airport pickup"),
         districts=("Mumbai", "Patna", "Kolkata"), delay=30, alternate="cab-ola"),
    _org("cab-ola", "Ola", OrgType.CAB, services=("pickup",),
         districts=("Mumbai", "Patna", "Kolkata"), delay=30, alternate="cab-meru-mum"),
    _org("cab-meru-mum", "Meru Cabs, Mumbai", OrgType.CAB, services=("pickup", "station pickup"),
         districts=("Mumbai",), hospitals=_MUM),
    _org("cab-saarthi-patna", "Saarthi Taxi, Patna", OrgType.CAB, services=("pickup",),
         districts=("Patna", "Gaya")),
    # ---- travel partners
    _org("tr-rail-assist", "Railway booking desk", OrgType.TRAVEL,
         services=("rail tickets", "senior and patient quota"),
         districts=("Mumbai", "Patna", "Gaya", "Kolkata", "Cuttack"), delay=45),
    _org("tr-bus-assist", "State bus booking desk", OrgType.TRAVEL, services=("bus tickets",),
         districts=("Patna", "Gaya", "Cuttack"), delay=45),
    # ---- hotels and stays
    _org("ho-oyo-parel", "OYO, Parel", OrgType.HOTEL, services=("rooms near the hospital",),
         districts=("Mumbai",), hospitals=_MUM, delay=45, alternate="ho-treebo-dadar"),
    _org("ho-treebo-dadar", "Treebo, Dadar", OrgType.HOTEL, services=("rooms",),
         districts=("Mumbai",), hospitals=_MUM, delay=45, alternate="ho-dharamshala-parel"),
    _org("ho-dharamshala-parel", "Patient dharamshala, Parel", OrgType.HOTEL,
         services=("low-cost beds for patients",), districts=("Mumbai",), hospitals=_MUM),
    _org("ho-lodge-patna", "Station Road Lodge, Patna", OrgType.HOTEL, districts=("Patna",)),
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
    """Fill an empty directory. True when it did, False when it left things alone."""
    if store.organisations():
        return False
    for organisation in DEMO_DIRECTORY:
        store.save_organisation(organisation)
    logger.info("seeded %d organisations into an empty directory", len(DEMO_DIRECTORY))
    return True
