"""Settings: the guard that keeps demo controls out of production, and paths."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError
from saathi.adapters.clock import ControlledClock, SystemClock
from saathi.config import Settings


def test_sim_mode_is_refused_in_production():
    with pytest.raises(ValidationError, match="never be reachable in production"):
        Settings(_env_file=None, sim_mode=True, environment="production")


def test_sim_mode_is_fine_locally_and_off_by_default():
    assert Settings(_env_file=None).sim_mode is False
    assert Settings(_env_file=None, sim_mode=True, environment="local").sim_mode is True


def test_data_paths_are_absolute_whatever_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)
    assert settings.data_path.is_absolute()
    assert settings.reference_cache_file.is_absolute()
    assert settings.reference_cache_file.name == "reference_cache.json"


def test_an_explicit_data_dir_wins(tmp_path):
    settings = Settings(_env_file=None, data_dir=str(tmp_path))
    assert settings.data_path == tmp_path.resolve()
    assert settings.reference_cache_file == tmp_path.resolve() / "reference_cache.json"


def test_an_explicit_cache_path_wins_over_the_data_dir(tmp_path):
    settings = Settings(
        _env_file=None,
        data_dir=str(tmp_path),
        reference_cache_path=str(tmp_path / "elsewhere.json"),
    )
    assert settings.reference_cache_file == (tmp_path / "elsewhere.json").resolve()


def test_integrations_report_enabled_only_when_fully_configured():
    off = Settings(_env_file=None)
    assert not off.abdm_enabled
    assert not off.hospital_feed_enabled

    partial = Settings(_env_file=None, abdm_base_url="https://abdm.example")
    assert not partial.abdm_enabled

    on = Settings(
        _env_file=None,
        abdm_base_url="https://abdm.example",
        abdm_client_id="id",
        abdm_client_secret="secret",
        hospital_feed_url="https://feed.example",
    )
    assert on.abdm_enabled
    assert on.hospital_feed_enabled


def test_the_controlled_clock_is_set_from_outside():
    clock = ControlledClock(date(2026, 9, 25))
    assert clock.today() == date(2026, 9, 25)
    clock.set(date(2026, 10, 2))
    assert clock.today() == date(2026, 10, 2)
    assert clock.now().tzinfo is not None


def test_the_system_clock_reports_the_hospitals_date():
    clock = SystemClock("Asia/Kolkata")
    assert clock.now().utcoffset().total_seconds() == 5.5 * 3600
    assert clock.today() == clock.now().date()


def test_the_simulation_clock_moves_the_date_the_container_reads():
    from saathi.bootstrap.container import build_container

    container = build_container(Settings(_env_file=None), today=date(2026, 9, 25))
    assert container.clock.today() == date(2026, 9, 25)
    container.world.clock.advance(3)
    assert container.clock.today() == date(2026, 9, 28)
    assert container.world.today == container.clock.today()
