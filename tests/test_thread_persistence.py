"""A family's thread survives the server restarting, which Render's free plan does when idle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import Role
from saathi.main import create_app

PASSWORD = "correct horse battery"


def _boot(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/thread.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    return TestClient(create_app())


def _thread(client, pid="SHOW-DIA-1"):
    container = client.app.state.container
    if "neha" not in {u["username"] for u in container.identity.list_users()}:
        container.identity.add_user("neha", "Neha", Role.ADMIN, PASSWORD)
    token = client.post(
        "/api/auth/login", json={"username": "neha", "password": PASSWORD}
    ).json()["token"]
    return client.get(
        f"/api/patients/{pid}/notifications", headers={"authorization": f"Bearer {token}"}
    ).json()["thread"]


def test_what_a_family_was_told_is_still_there_after_a_restart(tmp_path, monkeypatch):
    with _boot(tmp_path, monkeypatch) as first:
        desk = first.app.state.container.runner.partners
        desk._now = lambda: datetime.now(UTC) + timedelta(minutes=10)
        first.portal.call(first.app.state.container.runner.settle_partners)
        before = _thread(first)
    assert any(m["kind"] == "guide" for m in before)

    with _boot(tmp_path, monkeypatch) as second:
        after = _thread(second)

    assert {m["id"] for m in before} <= {m["id"] for m in after}
    plan_messages = [m for m in after if m["kind"] == "plan"]
    assert len({(m["body"], m["language"]) for m in plan_messages}) == len(plan_messages), (
        "the same plan message is not sent again just because the server restarted"
    )
    get_settings.cache_clear()


def test_a_message_the_guard_diverted_is_not_shown_to_the_family(tmp_path, monkeypatch):
    with _boot(tmp_path, monkeypatch) as client:
        runner = client.app.state.container.runner
        runner._record_outbound(
            "SHOW-DIA-1", kind="plan", body="", language="hi", channel="whatsapp",
            held=True, reason="date stated in a non-GO plan",
        )
        thread = _thread(client)

        assert all(row["body"] for row in thread)
    get_settings.cache_clear()
