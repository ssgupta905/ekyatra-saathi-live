"""What a host with no shell needs: a pasted database URL, a first admin, a starter cohort."""

from __future__ import annotations

from datetime import date

import pytest
from saathi.adapters.records import MemoryRecordStore, SqlRecordStore
from saathi.bootstrap.container import build_container
from saathi.bootstrap.demo_records import SEED_FAMILIES, SHOWCASE_PREFIX, seed_demo_records
from saathi.config import Settings
from saathi.domain.enums import Role

TODAY = date(2026, 11, 3)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql+psycopg://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("sqlite:///./local.db", "sqlite:///./local.db"),
    ],
)
def test_a_database_url_is_accepted_as_the_host_shows_it(given, expected):
    assert Settings(_env_file=None, records_url=given).records_url == expected


def _real(tmp_path, **over) -> Settings:
    return Settings(
        _env_file=None, world="real", records_url=f"sqlite:///{tmp_path}/deploy.db", **over
    )


def test_the_first_admin_is_created_from_configuration(tmp_path):
    state = build_container(
        _real(tmp_path, admin_username="Founder", admin_password="a-long-secret")
    )

    users = state.identity.list_users()

    assert [(u["username"], u["role"]) for u in users] == [("founder", Role.ADMIN.value)]
    assert state.identity.login("founder", "a-long-secret") is not None


def test_a_restart_does_not_reset_a_password_changed_since(tmp_path):
    settings = _real(tmp_path, admin_username="founder", admin_password="the-first-secret")
    first = build_container(settings)
    first.identity.add_user("founder", "Founder", Role.ADMIN, "changed-in-the-console")

    second = build_container(settings)

    assert second.identity.login("founder", "changed-in-the-console") is not None
    assert second.identity.login("founder", "the-first-secret") is None


def test_no_admin_is_created_unless_both_halves_are_given(tmp_path):
    state = build_container(_real(tmp_path, admin_username="founder"))

    assert state.identity.list_users() == []


def test_an_empty_database_is_seeded_once():
    store = MemoryRecordStore()
    settings = Settings(_env_file=None, seed_demo=True)

    assert seed_demo_records(store, TODAY, settings) is True
    assert len(store.load().patients) == SEED_FAMILIES
    assert store.load().turnaround, "the forecast needs history to learn from"
    assert seed_demo_records(store, TODAY, settings) is False
    assert len(store.load().patients) == SEED_FAMILIES


def test_a_database_that_already_has_a_family_is_left_alone(tmp_path):
    store = SqlRecordStore(f"sqlite:///{tmp_path}/has-one.db")
    seed_demo_records(store, TODAY, Settings(_env_file=None, seed_demo=True))
    before = store.load()

    assert seed_demo_records(store, TODAY, Settings(_env_file=None, seed_demo=True)) is False
    assert store.load().patients == before.patients


def test_the_first_seeded_family_answers_to_the_given_phone():
    store = MemoryRecordStore()
    settings = Settings(_env_file=None, seed_demo=True, seed_demo_phone="+919811122233")

    seed_demo_records(store, TODAY, settings)
    patients = store.load().patients

    assert patients[0].caregiver_phone == "+919811122233"
    assert all(p.caregiver_phone != "+919811122233" for p in patients[1:])


def test_a_seeded_deployment_boots_with_families_and_a_way_in(tmp_path):
    state = build_container(
        _real(
            tmp_path, seed_demo=True, seed_demo_phone="+919811122233",
            admin_username="founder", admin_password="a-long-secret",
        )
    )

    families = state.world.patients()
    assert len([p for p in families if not p.id.startswith(SHOWCASE_PREFIX)]) == SEED_FAMILIES
    assert any(p.id.startswith(SHOWCASE_PREFIX) for p in families), "the showcase comes with it"
    assert state.identity.login("founder", "a-long-secret") is not None
    assert state.identity._phones.families_for("9811122233"), "the seeded phone finds its family"
