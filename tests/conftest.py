"""Test-wide isolation from credentials.

The suite's job is to prove the decision path works with **no** external
service: no planner call, no guard check and no ledger write may depend on a
key being present. Once a developer puts a real `GROQ_API_KEY` in `.env`,
`get_settings()` would pick it up here too, and the tests would quietly start
spending tokens and making network calls — slow, flaky, and no longer a test of
the thing they claim to test.

So the environment is blanked before any `Settings` is constructed. A test that
wants a language layer or an actor supplies a stub explicitly.
"""

from __future__ import annotations

import os

import pytest

# Environment variables beat `.env` in pydantic-settings' precedence, and an
# empty string is falsy — which is exactly "not configured" to every call site.
#
# Every key, not just the model ones. SARVAM_KEY was added to `.env` and this
# list was not, so the speech endpoints quietly started reaching the real
# service during the suite: a test that had never made a network call began
# making one, and said nothing about it.
for _key in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "SARVAM_KEY", "BREVO_API_KEY"):
    os.environ[_key] = ""


@pytest.fixture(autouse=True, scope="session")
def _settings_are_credential_free():
    from saathi.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert not settings.language_layer_enabled, (
        "the test suite picked up real credentials — it must run credential-free"
    )
    assert not settings.actors_enabled
    assert not settings.sarvam_api_key, (
        "SARVAM_KEY reached the suite — speech tests would hit the real service"
    )
    yield
    get_settings.cache_clear()
