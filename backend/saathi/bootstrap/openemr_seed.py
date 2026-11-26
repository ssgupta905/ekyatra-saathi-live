"""Put the demo's hospital into a real OpenEMR, over FHIR.

The counterpart to `bahmni_seed.py`, and it follows the same three rules
because they were learned the hard way: **idempotent** (look before writing,
so running it twice changes nothing and it doubles as the reset between
takes), **namespaced** (nothing outside the `EKY-` identifier prefix is ever
touched), and **dry by default** (it prints what it would do; writing takes
`--write`, typed on purpose).

Unlike the Bahmni seeder this one is pure FHIR — no database access — which
took some finding. Everything surprising is in `docs/openemr.md`; the four
that bite hardest:

* A `Patient` needs `name[].use = "official"`, or the validator reports the
  name empty having never read it.
* The identifier FHIR reports is OpenEMR's External ID, and it is only
  written when the identifier carries the v2-0203 `PT` type coding. Without
  that, OpenEMR silently keeps its own auto-assigned number and the connector
  can never match the family.
* An `Appointment` needs three participants — Patient, Practitioner and
  Location — plus a `comment`. Omit the Practitioner and the appointment is
  created, readable over FHIR, and **invisible on the calendar**, which is the
  one place the demo needs it to be.
* The Location must be the **facility**, whose uuid comes from `Organization`
  and is *not* the same as the clinic's `Location` id.

Three things it cannot do, because they are not reachable over HTTP. Each is
detected and reported rather than failing cryptically:

* turning the FHIR API on (`globals.rest_api`, `rest_fhir_api`,
  `rest_system_scopes_api`)
* enabling a newly registered client (`oauth_clients.is_enabled`)
* giving a user an NPI, which is the only thing that makes them a Practitioner

    python -m saathi.bootstrap.openemr_seed --register   # once, per instance
    python -m saathi.bootstrap.openemr_seed              # say what it would do
    python -m saathi.bootstrap.openemr_seed --write --local
"""

from __future__ import annotations

import argparse
import base64
import logging
import sys
import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import httpx

from ..adapters.hospital._smart import SYSTEM_SCOPES as SCOPES
from ..config import get_settings
from .bahmni_seed import APPOINTMENTS, PATIENTS, PREFIX, seed_local_cast

logger = logging.getLogger("openemr_seed")

#: The coding that makes OpenEMR treat an identifier as its External ID.
_PT_TYPE = {
    "coding": [
        {"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "PT"}
    ]
}
_ID_SYSTEM = "http://terminology.hl7.org/CodeSystem/v2-0203"


#: Kamla's pre-MRI renal function test. An `active` ServiceRequest *is*
#: "creatinine pending" — the beat Bahmni could not express at all.
CREATININE = {
    "code": "2160-0",
    "display": "Creatinine [Mass/volume] in Serum or Plasma",
}


class OpenEmrError(RuntimeError):
    """Something the seeder cannot fix by itself, said in words."""


class Client:
    """FHIR over HTTP, with a SMART token minted per run."""

    def __init__(self, base_url: str, token: str, *, write: bool) -> None:
        self.root = base_url.rstrip("/")
        self.fhir = f"{self.root}/apis/default/fhir"
        self.write = write
        self.did: list[str] = []
        self.would: list[str] = []
        self._http = httpx.Client(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/fhir+json",
                "Content-Type": "application/fhir+json",
            },
        )

    def close(self) -> None:
        self._http.close()

    def note(self, message: str) -> None:
        (self.did if self.write else self.would).append(message)
        logger.info("%s %s", "did:" if self.write else "would:", message)

    def get(self, path: str, **params) -> dict:
        response = self._http.get(f"{self.fhir}{path}", params=params or None)
        if response.status_code == 401:
            raise OpenEmrError(
                f"401 reading {path}. The client's registered scopes may not cover it, "
                "or the client is not enabled — see docs/openemr.md"
            )
        response.raise_for_status()
        return response.json() if response.content else {}

    def post(self, path: str, body: dict) -> dict:
        response = self._http.post(f"{self.fhir}{path}", json=body)
        if response.status_code >= 400:
            raise OpenEmrError(
                f"{response.status_code} creating {path}: {response.text[:300].strip()}"
            )
        return response.json() if response.content else {}

    def entries(self, path: str, **params) -> list[dict]:
        bundle = self.get(path, **params)
        return [
            e["resource"]
            for e in bundle.get("entry", [])
            if isinstance(e, dict) and isinstance(e.get("resource"), dict)
        ]


# ---------------- discovery ----------------


def _facility(client: Client) -> str:
    """The uuid an Appointment's Location participant must name.

    Deliberately `Organization`, not `Location`. OpenEMR's FHIR `Location`
    search returns every patient's home address alongside the clinic, and the
    clinic's `Location` id is a *different* uuid from the facility row the
    appointment validator resolves against. Using it produces
    "Appointment requires a participant whose actor is a Location reference"
    while pointing at something that is, visibly, a location.
    """
    found = client.entries("/Organization", _count=20)
    if not found:
        raise OpenEmrError(
            "this OpenEMR has no Organization — there is no facility to book into"
        )
    if len(found) > 1:
        logger.info(
            "%d organisations; using %r", len(found), found[0].get("name", found[0]["id"])
        )
    return str(found[0]["id"])


def _practitioner(client: Client) -> str:
    """Whoever the appointments are booked under.

    Without one the appointment exists and the calendar does not show it,
    which is the single most confusing failure in this whole integration:
    everything reads back correctly over FHIR and the screen is empty.
    """
    found = client.entries("/Practitioner", _count=20)
    if not found:
        raise OpenEmrError(
            "this OpenEMR has no Practitioner. A user becomes one only by having an "
            "NPI: UPDATE users SET npi='1234567893' WHERE username='admin'"
        )
    return str(found[0]["id"])


def _patients_by_identifier(client: Client) -> dict[str, str]:
    """Our `EKY-` families, as OpenEMR holds them. Keyed by our own id."""
    known: dict[str, str] = {}
    for resource in client.entries("/Patient", _count=100):
        for identifier in resource.get("identifier", []):
            value = str((identifier or {}).get("value") or "")
            if value.startswith(PREFIX):
                known[value] = str(resource["id"])
    return known


# ---------------- seeding ----------------


def ensure_patients(client: Client, cast=None) -> dict[str, str]:
    """Register whichever families are given, defaulting to the standing cast.

    Taking a cast rather than reading the module constant lets a second set of
    families be seeded — the ones who fail in other ways — without editing the
    list every demo already depends on.
    """
    standing = _patients_by_identifier(client)
    for patient in cast if cast is not None else PATIENTS:
        if patient.identifier in standing:
            logger.info("patient %s already exists", patient.identifier)
            continue
        client.note(f"register patient {patient.identifier} ({patient.given_name})")
        if not client.write:
            standing[patient.identifier] = f"<would-create:{patient.identifier}>"
            continue
        client.post(
            "/Patient",
            {
                "resourceType": "Patient",
                "identifier": [
                    {
                        "use": "official",
                        "type": _PT_TYPE,
                        "system": _ID_SYSTEM,
                        "value": patient.identifier,
                    }
                ],
                # `use: official` is load-bearing; without it the name is not read.
                "name": [
                    {
                        "use": "official",
                        "family": patient.family_name,
                        "given": [patient.given_name],
                    }
                ],
                "gender": "female" if patient.gender == "F" else "male",
                "birthDate": patient.birthdate,
            },
        )
        standing = _patients_by_identifier(client)
    return standing


def ensure_appointments(
    client: Client,
    patients: dict[str, str],
    *,
    facility: str,
    practitioner: str,
    today: date,
    cast=None,
) -> dict[tuple[str, str], date]:
    """Book what is missing, and report the day each booking sits on.

    Returns the dates so our own records can be written from what the hospital
    actually holds rather than from "today" — the two drifting apart is a bug
    we have already had once, and it made a real cancellation land on a date
    no local step was sitting on. See `bahmni_seed.seed_local_cast`.
    """
    booked: dict[tuple[str, str], date] = {}
    by_id = {v: k for k, v in patients.items()}

    standing = client.entries(
        "/Appointment",
        date=[
            f"ge{(today - timedelta(days=2)).isoformat()}",
            f"le{(today + timedelta(days=21)).isoformat()}",
        ],
        _count=100,
    )
    held: set[tuple[str, str]] = set()
    for row in standing:
        reference = ""
        for participant in row.get("participant", []):
            actor = str(((participant or {}).get("actor") or {}).get("reference") or "")
            if actor.startswith("Patient/"):
                reference = actor.split("/", 1)[1]
        identifier = by_id.get(reference, "")
        start = str(row.get("start") or "")
        if not identifier or not start:
            continue
        moment = datetime.fromisoformat(start.replace("Z", "+00:00"))
        service = str(row.get("description") or "")
        booked.setdefault((identifier, service), moment.date())
        # Only an *open* appointment counts as held. A cancelled one is what
        # this script exists to undo — that is what makes it a reset.
        #
        # Keyed on the **moment**, not the service name: OpenEMR does not
        # echo `description` back, so every appointment reads as having no
        # service and a name-based key matches nothing. Seeding then re-books
        # every slot on every run — five identical appointments for the same
        # patient at the same minute, which is what this looked like before.
        if str(row.get("status")) not in ("cancelled", "noshow"):
            held.add((identifier, moment))

    for booking in cast if cast is not None else APPOINTMENTS:
        day = today + timedelta(days=booking.days_from_today)
        starts = datetime.combine(day, booking.at, tzinfo=UTC)
        booked.setdefault((booking.patient_identifier, booking.service_name), day)
        if (booking.patient_identifier, starts) in held:
            logger.info(
                "appointment for %s (%s) already stands",
                booking.patient_identifier,
                booking.service_name,
            )
            continue

        client.note(
            f"book {booking.service_name} for {booking.patient_identifier} "
            f"on {day:%a %d %b} at {booking.at:%H:%M}"
        )
        if not client.write:
            continue

        client.post(
            "/Appointment",
            {
                "resourceType": "Appointment",
                "status": "booked",
                "start": _instant(starts),
                "end": _instant(starts + timedelta(minutes=30)),
                "description": booking.service_name,
                # `comment` maps to pc_hometext, which is NotEmpty.
                # `description` alone does not satisfy it.
                "comment": f"{booking.service_name} — EKYATRA demo",
                "participant": [
                    {
                        "actor": {
                            "reference": f"Patient/{patients[booking.patient_identifier]}"
                        },
                        "status": "accepted",
                    },
                    # Without this the appointment never appears on the calendar.
                    {
                        "actor": {"reference": f"Practitioner/{practitioner}"},
                        "status": "accepted",
                    },
                    {"actor": {"reference": f"Location/{facility}"}, "status": "accepted"},
                ],
            },
        )
        booked[(booking.patient_identifier, booking.service_name)] = day
    return booked


def ensure_creatinine(client: Client, patients: dict[str, str], today: date) -> None:
    """Kamla's pending renal function test, left `active`.

    `active` *is* "pending" — there is nothing else to set and nothing to
    wait for. This is the beat Bahmni could not express at all: its demo held
    no orders and exposed none through FHIR.
    """
    kamla = patients.get(f"{PREFIX}KAMLA")
    if not kamla:
        return

    for order in client.entries("/ServiceRequest", patient=kamla, _count=20):
        if order.get("status") == "active":
            logger.info("the creatinine order is already pending")
            return

    client.note(f"order a creatinine for {PREFIX}KAMLA, left pending")
    if not client.write:
        return
    client.post(
        "/ServiceRequest",
        {
            "resourceType": "ServiceRequest",
            "status": "active",
            "intent": "order",
            "code": {"coding": [{"system": "http://loinc.org", **CREATININE}]},
            "subject": {"reference": f"Patient/{kamla}"},
            "authoredOn": _instant(datetime.combine(today, time(9, 0), tzinfo=UTC)),
        },
    )


# ---------------- registration ----------------


def register(base_url: str, key_path: Path) -> dict:
    """Register an API client and write its signing key.

    The key is written to a file rather than printed, because a private key
    that goes through a terminal ends up in scrollback and shell history.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()

    def b64u(value: int) -> str:
        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    key_id = uuid.uuid4().hex
    body = {
        "application_type": "private",
        "client_name": "Saathi Connector",
        # Required even for client_credentials, which never redirects anywhere.
        "redirect_uris": ["http://localhost:8077/oauth/callback"],
        "token_endpoint_auth_method": "private_key_jwt",
        "grant_types": ["client_credentials"],
        "jwks": {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS384",
                    "kid": key_id,
                    "n": b64u(numbers.n),
                    "e": b64u(numbers.e),
                }
            ]
        },
        "scope": SCOPES,
    }
    response = httpx.post(
        f"{base_url.rstrip('/')}/oauth2/default/registration", json=body, timeout=30.0
    )
    if response.status_code >= 400:
        detail = response.text[:300].strip()
        hint = (
            "\n\nThe API is off by default. Enable it:\n"
            "  UPDATE globals SET gl_value='1' WHERE gl_name IN "
            "('rest_api','rest_fhir_api','rest_system_scopes_api');"
            if "API is disabled" in detail
            else ""
        )
        raise OpenEmrError(f"registration refused: {detail}{hint}")

    registered = response.json()
    key_path.write_text(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
    )
    key_path.chmod(0o600)
    return {"client_id": registered["client_id"], "key_id": key_id, "key_path": str(key_path)}


# ---------------- plumbing ----------------


def _instant(moment: datetime) -> str:
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _token(base_url: str, client_id: str, key_id: str, key_path: str) -> str:
    from ..adapters.hospital._smart import SmartTokens

    return SmartTokens(
        token_url=f"{base_url.rstrip('/')}/oauth2/default/token",
        client_id=client_id,
        key_id=key_id,
        private_key_pem=Path(key_path).read_text(),
        scope=SCOPES,
    )()


def _report(client: Client, today: date) -> int:
    print(f"\nOpenEMR at {client.root}")
    patients = _patients_by_identifier(client)
    print(f"  {len(patients)} EKY- patient(s): {', '.join(sorted(patients)) or '—'}")
    rows = client.entries(
        "/Appointment",
        date=[
            f"ge{(today - timedelta(days=2)).isoformat()}",
            f"le{(today + timedelta(days=21)).isoformat()}",
        ],
        _count=50,
    )
    print(f"  {len(rows)} appointment(s) in the window")
    for row in rows:
        print(f"    - {str(row.get('status')):10} {row.get('start')} {row.get('description')}")
    orders = client.entries("/ServiceRequest", _count=20)
    pending = sum(1 for o in orders if o.get("status") == "active")
    print(f"  {len(orders)} order(s), {pending} pending")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="actually create things")
    parser.add_argument("--check", action="store_true", help="report what is there, and stop")
    parser.add_argument(
        "--local",
        action="store_true",
        help="also write the matching families into our own records",
    )
    parser.add_argument(
        "--register", action="store_true", help="register an API client, then stop"
    )
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--key", default="openemr-key.pem", help="where the signing key lives")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    base_url = args.base_url or settings.openemr_base_url
    if not base_url:
        print("Set SAATHI_OPENEMR_BASE_URL or pass --base-url.", file=sys.stderr)
        return 2

    if args.register:
        try:
            made = register(base_url, Path(args.key))
        except OpenEmrError as exc:
            print(f"\n{exc}\n", file=sys.stderr)
            return 1
        print("\nRegistered. Two things are still needed, and neither is reachable over HTTP:\n")
        print("  UPDATE oauth_clients SET is_enabled=1, client_role='system';")
        print("  UPDATE users SET npi='1234567893' WHERE username='admin';")
        print("     ^ an NPI is the only thing that makes a user a Practitioner\n")
        print("Then set:\n")
        print(
            f"  SAATHI_HOSPITAL_SYSTEMS=<HOSPITAL>=openemr|{base_url}|"
            f"{made['client_id']}|{made['key_id']}|{made['key_path']}\n"
        )
        return 0

    if not (settings.openemr_client_id and settings.openemr_key_id):
        print(
            "No registered client. Run --register first, or set "
            "SAATHI_OPENEMR_CLIENT_ID and SAATHI_OPENEMR_KEY_ID.",
            file=sys.stderr,
        )
        return 2

    today = date.today()
    try:
        token = _token(
            base_url,
            settings.openemr_client_id,
            settings.openemr_key_id,
            settings.openemr_key_path or args.key,
        )
    except Exception as exc:  # noqa: BLE001 - the message is the whole point
        print(f"\nCould not authenticate: {exc}\n", file=sys.stderr)
        return 1

    client = Client(base_url, token, write=args.write)
    try:
        if args.check:
            return _report(client, today)

        facility = _facility(client)
        practitioner = _practitioner(client)
        patients = ensure_patients(client)
        booked = ensure_appointments(
            client, patients, facility=facility, practitioner=practitioner, today=today
        )
        ensure_creatinine(client, patients, today)

        if args.local and args.write:
            _seed_local(settings, today, booked)
    except OpenEmrError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1
    finally:
        client.close()

    if args.write:
        print(f"\nDone. {len(client.did)} change(s) made to {base_url}.")
    else:
        print(f"\nDry run against {base_url}. {len(client.would)} change(s) would be made:")
        for line in client.would:
            print(f"  - {line}")
        print("\nNothing was written. Re-run with --write to apply.")
    return 0


def _seed_local(settings, today: date, booked: dict) -> None:
    from ..adapters.records import SqlRecordStore

    store = SqlRecordStore(settings.records_url)
    hospital_id = (
        settings.hospital_places[0].partition("=")[0].strip()
        if settings.hospital_places
        else "TMH-MUM"
    )
    if seed_local_cast(store, today, hospital_id=hospital_id, booked=booked):
        print(f"  wrote the matching cast into {settings.records_url}")


if __name__ == "__main__":
    raise SystemExit(main())
