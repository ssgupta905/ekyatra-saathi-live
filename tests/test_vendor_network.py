"""The vendor network: applying, being let in, rates, standing, earnings.

The three things worth failing a build over:

**An application cannot be given work.** `POST /partner/apply` needs no
sign-in, which is only safe because what it creates is switched off. If an
applicant could ever be selected for a family's journey, the open route would
be a way to insert yourself into somebody's cancer treatment.

**A vendor sees its own business and nobody else's.** Its rates, its jobs, its
money. Not another vendor's, and nothing about a family beyond what
`test_partner_app.py` already pins down.

**The commission never reaches the family.** It is capped in the domain and
comes off the vendor's side. A family is told the vendor's price and pays the
vendor's price, and that is asserted here rather than asserted in a comment.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from saathi.config import get_settings
from saathi.domain.directory import MOST_COMMISSION_PCT, Organisation, OrgType, PartnerMode
from saathi.domain.enums import ReadinessKind, ReadinessStatus, Role
from saathi.main import create_app

PASSWORD = "correct horse battery"
OLA = "cab-ola"

APPLICATION = {
    "id": "gaya-travels",
    "name": "Gaya Travels",
    "type": "travel",
    "contact": "+91 90000 11122",
    "districts": ["Gaya", "Nalanda"],
    "services": ["station pickup", "overnight to Mumbai"],
    "hours": "24 hours",
    "rate_card": [
        {"service": "Gaya to Mumbai, sleeper", "unit": "per trip", "amount_inr": 2400},
        {"service": "station pickup", "unit": "per trip", "amount_inr": 350,
         "note": "₹100 more after 10pm"},
    ],
    "note": "Four cars, two drivers who have done hospital runs for years.",
}


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/vendors.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        container.identity.add_user("neha", "Neha", Role.ADMIN, PASSWORD)
        container.identity.add_user("seema", "Seema", Role.NAVIGATOR, PASSWORD)
        container.identity.add_user(
            "ola", "Ola", Role.PARTNER, PASSWORD, organisation_id=OLA
        )
        client.container = container
        yield client
    get_settings.cache_clear()


def _as(client, username: str, password: str = PASSWORD) -> dict:
    answer = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert answer.status_code == 200, answer.text
    return {"authorization": f"Bearer {answer.json()['token']}"}


def _org(net, organisation_id: str) -> Organisation:
    return next(o for o in net.container.registry.organisations() if o.id == organisation_id)


# ------------------------------------------------------------- applying


def test_a_vendor_can_apply_without_signing_in(net):
    applied = net.post("/api/partner/apply", json=APPLICATION)
    assert applied.status_code == 201, applied.text
    assert applied.json()["status"] == "awaiting_review"

    org = _org(net, "gaya-travels")
    assert org.awaiting_review and not org.active
    assert org.mode is PartnerMode.PEOPLE, "a real vendor is not auto-answered"
    assert [r.amount_inr for r in org.rate_card] == [2400, 350]


def test_an_application_can_never_be_given_work(net):
    """The whole reason the apply route can be left open.

    Asserted through the real chooser, and in its strongest form: even when
    the applicant is named as the preferred organisation — which is how a
    family's own choice reaches the orchestrator — it is not selected.
    """
    from saathi.orchestrator.rules import choose_organisation

    net.post("/api/partner/apply", json=APPLICATION)
    organisations = net.container.registry.organisations()
    assert any(o.id == "gaya-travels" for o in organisations)

    for preferred in (None, "gaya-travels"):
        chosen = choose_organisation(
            ReadinessKind.TRANSPORT,
            district="Gaya",
            hospital_id="TMH-MUM",
            organisations=organisations,
            preferred_id=preferred,
        )
        assert chosen is None or chosen.id != "gaya-travels"


def test_an_applicant_is_not_in_the_directory_a_navigator_books_from(net):
    net.post("/api/partner/apply", json=APPLICATION)
    listed = net.get("/api/directory", headers=_as(net, "seema")).json()
    row = next((o for o in listed if o["id"] == "gaya-travels"), None)
    # Visible, because a navigator asking "who is in Gaya" should see that
    # somebody applied — but unmistakably off.
    assert row is not None and row["active"] is False


def test_a_name_already_taken_is_refused_plainly(net):
    assert net.post("/api/partner/apply", json=APPLICATION).status_code == 201
    again = net.post("/api/partner/apply", json=APPLICATION)
    assert again.status_code == 409
    assert "already taken" in again.json()["detail"]


def test_the_open_route_cannot_grow_the_directory_without_bound(net):
    """A route with no sign-in that writes rows needs a ceiling.

    Not a breach if it is missing — just a denial of the thing the route is
    for, because a real vendor's application would be lost in the noise.
    """
    from saathi.api.partner import MOST_WAITING_APPLICATIONS

    for n in range(MOST_WAITING_APPLICATIONS):
        sent = net.post("/api/partner/apply", json={**APPLICATION, "id": f"vendor-{n}"})
        assert sent.status_code == 201, sent.text

    full = net.post("/api/partner/apply", json={**APPLICATION, "id": "one-too-many"})
    assert full.status_code == 429
    assert "queue, not a refusal" in full.json()["detail"]

    # And the queue drains: a decision makes room for the next applicant.
    net.post(
        "/api/partner/applications/vendor-0/decline",
        json={"reason": "no permit on file"},
        headers=_as(net, "neha"),
    )
    room = net.post("/api/partner/apply", json={**APPLICATION, "id": "one-too-many"})
    assert room.status_code == 201, room.text


def test_an_application_with_a_shouty_id_is_refused(net):
    bad = net.post("/api/partner/apply", json={**APPLICATION, "id": "Gaya Travels!"})
    assert bad.status_code == 422


# ------------------------------------------------------------ the review


def test_a_navigator_sees_who_is_waiting_to_be_let_in(net):
    net.post("/api/partner/apply", json=APPLICATION)
    waiting = net.get("/api/partner/applications", headers=_as(net, "seema"))
    assert waiting.status_code == 200, waiting.text
    row = next(o for o in waiting.json() if o["id"] == "gaya-travels")
    assert row["rate_lines"] == 2
    assert "hospital runs" in row["applicant_note"]


def test_approving_lets_a_vendor_in_and_creates_its_login(net):
    net.post("/api/partner/apply", json=APPLICATION)
    approved = net.post(
        "/api/partner/applications/gaya-travels/approve",
        json={"commission_pct": 5, "username": "gaya", "password": "a long enough one"},
        headers=_as(net, "neha"),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["account"] == "gaya"

    org = _org(net, "gaya-travels")
    assert org.active and org.approved_on is not None and not org.awaiting_review
    assert org.commission_pct == 5

    # And the vendor can now actually sign in and see itself.
    mine = net.get("/api/partner/me", headers=_as(net, "gaya", "a long enough one"))
    assert mine.status_code == 200, mine.text
    assert mine.json()["name"] == "Gaya Travels"


def test_a_vendor_cannot_approve_itself(net):
    net.post("/api/partner/apply", json=APPLICATION)
    refused = net.post(
        "/api/partner/applications/gaya-travels/approve",
        json={"commission_pct": 0},
        headers=_as(net, "ola"),
    )
    assert refused.status_code == 403, refused.text
    assert not _org(net, "gaya-travels").active


def test_a_navigator_cannot_approve_either(net):
    """Letting somebody into the network is an administrator's decision."""
    net.post("/api/partner/apply", json=APPLICATION)
    refused = net.post(
        "/api/partner/applications/gaya-travels/approve",
        json={"commission_pct": 0},
        headers=_as(net, "seema"),
    )
    assert refused.status_code == 403


def test_declining_keeps_the_record_and_the_reason(net):
    net.post("/api/partner/apply", json=APPLICATION)
    declined = net.post(
        "/api/partner/applications/gaya-travels/decline",
        json={"reason": "no commercial vehicle permit on file"},
        headers=_as(net, "neha"),
    )
    assert declined.status_code == 200, declined.text

    org = _org(net, "gaya-travels")
    assert org.declined and not org.active and not org.awaiting_review
    assert "permit" in org.declined_reason
    # Gone from the queue, so nobody reviews it twice.
    waiting = net.get("/api/partner/applications", headers=_as(net, "neha")).json()
    assert "gaya-travels" not in [o["id"] for o in waiting]


def test_an_application_is_decided_once(net):
    net.post("/api/partner/apply", json=APPLICATION)
    admin = _as(net, "neha")
    net.post(
        "/api/partner/applications/gaya-travels/decline",
        json={"reason": "no permit"}, headers=admin,
    )
    again = net.post(
        "/api/partner/applications/gaya-travels/approve",
        json={"commission_pct": 0}, headers=admin,
    )
    assert again.status_code == 409


def test_declining_needs_a_reason(net):
    net.post("/api/partner/apply", json=APPLICATION)
    refused = net.post(
        "/api/partner/applications/gaya-travels/decline",
        json={"reason": ""}, headers=_as(net, "neha"),
    )
    assert refused.status_code == 422


# -------------------------------------------------------------- the rates


def test_a_vendor_states_its_own_rates(net):
    put = net.put(
        "/api/partner/rates",
        json=[{"service": "airport pickup", "unit": "per trip", "amount_inr": 900}],
        headers=_as(net, "ola"),
    )
    assert put.status_code == 200, put.text
    assert put.json()["rate_card"][0]["amount_inr"] == 900
    assert [r.service for r in _org(net, OLA).rate_card] == ["airport pickup"]


def test_rates_are_replaced_wholesale_not_merged(net):
    ola = _as(net, "ola")
    net.put(
        "/api/partner/rates",
        json=[
            {"service": "old route", "amount_inr": 100},
            {"service": "another", "amount_inr": 200},
        ],
        headers=ola,
    )
    net.put("/api/partner/rates", json=[{"service": "new route", "amount_inr": 300}], headers=ola)
    card = _org(net, OLA).rate_card
    assert [r.service for r in card] == ["new route"], (
        "a half-updated price list is worse than an old one"
    )


def test_a_vendor_cannot_set_another_vendors_rates(net):
    """There is no route that takes an organisation id, which is the point."""
    before = _org(net, "cab-uber").rate_card
    net.put("/api/partner/rates", json=[{"service": "x", "amount_inr": 1}], headers=_as(net, "ola"))
    assert _org(net, "cab-uber").rate_card == before


def test_staff_cannot_sign_in_to_the_vendor_side(net):
    assert net.get("/api/partner/me", headers=_as(net, "seema")).status_code == 403
    assert net.get("/api/partner/earnings", headers=_as(net, "neha")).status_code == 403


# --------------------------------------------------------- the commission


def test_the_commission_is_capped_in_the_domain():
    with pytest.raises(ValidationError):
        Organisation(
            id="greedy", name="Greedy", type=OrgType.CAB,
            commission_pct=MOST_COMMISSION_PCT + 0.1,
        )


def test_an_administrator_cannot_agree_terms_above_the_cap(net):
    net.post("/api/partner/apply", json=APPLICATION)
    refused = net.post(
        "/api/partner/applications/gaya-travels/approve",
        json={"commission_pct": MOST_COMMISSION_PCT + 1},
        headers=_as(net, "neha"),
    )
    assert refused.status_code == 422
    assert not _org(net, "gaya-travels").active


def test_the_commission_rounds_against_us_not_the_vendor():
    org = Organisation(id="c", name="C", type=OrgType.CAB, commission_pct=5)
    # ₹99.99 at 5% is 499.95 paise. A vendor keeps the half-paisa.
    assert org.commission_paise(9999) == 499


def test_the_family_pays_the_vendors_price_and_nothing_more(net):
    """The commission comes off our side. This is the invariant that matters."""
    registry = net.container.registry
    ola = _org(net, OLA)
    registry.save_organisation(
        ola.model_copy(update={"commission_pct": MOST_COMMISSION_PCT, "mode": PartnerMode.PEOPLE})
    )

    patient_id, item_id = _a_job_for_ola(net)
    answered = net.post(
        f"/api/partner/jobs/{item_id}",
        json={"answer": "ready", "quote_inr": 1000},
        headers=_as(net, "ola"),
    )
    assert answered.status_code == 200, answered.text

    # What the vendor is shown about its own money.
    books = net.get("/api/partner/earnings", headers=_as(net, "ola")).json()
    assert books["quoted_inr"] == 1000
    assert books["commission_inr"] == 80
    assert books["you_keep_inr"] == 920
    assert books["family_pays_inr"] == 1000

    # And what the family is actually asked for: the vendor's figure, whole.
    quotes = [
        e
        for e in net.container.runner.kharcha.store.entries(patient_id)
        if e.organisation_id == OLA
    ]
    assert [e.amount_paise for e in quotes] == [100_000], (
        "the family's books hold the vendor's quote, with no commission in it"
    )


def test_a_vendors_books_name_the_job_and_nothing_about_the_family(net):
    """What a vendor's own books may and may not say.

    They may name the job, because the vendor was told that reference when it
    was asked to do the work and cannot reconcile its money without it. They
    may not name a person, a place or a care step — and they must not pass
    through this system's internal tracing reference, whose shape is nobody's
    business outside and which happens to carry more than the job id.
    """
    registry = net.container.registry
    registry.save_organisation(_org(net, OLA).model_copy(update={"mode": PartnerMode.PEOPLE}))
    patient_id, item_id = _a_job_for_ola(net)
    net.post(
        f"/api/partner/jobs/{item_id}",
        json={"answer": "ready", "quote_inr": 1000},
        headers=_as(net, "ola"),
    )
    books = net.get("/api/partner/earnings", headers=_as(net, "ola")).json()
    patient = net.container.world.patient(patient_id)

    (line,) = [row for row in books["lines"] if row["amount_inr"] == 1000]
    assert line["job"] == item_id
    assert "partner-quote" not in str(books), "the internal reference is not passed through"
    assert patient.name and patient.name not in str(books)
    assert patient.home_district not in str(books)
    assert set(line) == {"on", "amount_inr", "category", "status", "job"}


# ---------------------------------------------------------- the standing


def test_standing_is_counted_from_what_happened(net):
    registry = net.container.registry
    registry.save_organisation(_org(net, OLA).model_copy(update={"mode": PartnerMode.PEOPLE}))
    _, item_id = _a_job_for_ola(net)
    ola = _as(net, "ola")

    before = net.get("/api/partner/me", headers=ola).json()["standing"]
    assert before["asked"] >= 1 and before["confirmed"] == 0

    net.post(f"/api/partner/jobs/{item_id}", json={"answer": "ready"}, headers=ola)
    after = net.get("/api/partner/me", headers=ola).json()["standing"]
    assert after["confirmed"] == before["confirmed"] + 1


def test_standing_says_how_it_was_worked_out_and_claims_no_rating(net):
    standing = net.get("/api/partner/me", headers=_as(net, "ola")).json()["standing"]
    assert "no rating" in standing["how_this_is_worked_out"]
    assert not any("rating" == key or "score" == key for key in standing)


def test_the_vendors_own_page_states_the_cap_and_who_pays_it(net):
    mine = net.get("/api/partner/me", headers=_as(net, "ola")).json()
    assert mine["commission_cap_pct"] == MOST_COMMISSION_PCT
    assert "never added to the family" in mine["commission_note"]


# ------------------------------------------------------------------ helper


def _a_job_for_ola(net, kind: ReadinessKind = ReadinessKind.TRANSPORT) -> tuple[str, str]:
    """Ask Ola for a ride, the way a navigator would.

    Transport by default, because that is a need the family pays for — which
    is what makes a quote, and therefore the commission, meaningful.
    """
    desk = net.container.runner.partners
    for patient in net.container.world.patients():
        if not patient.name:
            continue
        for item in net.container.world.readiness_for(patient.id):
            if item.partner_id and item.status is ReadinessStatus.PENDING and item.kind is kind:
                moved = desk.ask(patient.id, item.kind, OLA)
                return patient.id, moved.id
    raise AssertionError(f"no named family is waiting on anybody for {kind.value}")
