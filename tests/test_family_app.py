"""The family's own surface: one screen's worth of data, and their language.

The phone is a separate application from the hospital console, so it has its
own endpoints and its own guarantees. Two matter enough to pin here: the home
payload must never be able to carry a clinical finding, and choosing a language
must be a change to the family's record rather than a translation of the view.

Credential-free like the rest of the suite — no Groq key, so no render happens
and the language change is proven by the record and the ledger, which is where
it actually lives.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.domain.enums import Language
from saathi.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def patient_id(client) -> str:
    return client.get("/api/patients").json()[0]["id"]


def test_home_is_one_call_with_everything_the_phone_shows(client, patient_id):
    body = client.get(f"/api/patients/{patient_id}/home").json()

    # One round trip. The phone is opened on a 2G connection, and five calls
    # means five chances to paint a half-built page.
    assert body["patient"]["id"] == patient_id
    for key in ("decision", "travel_on", "waiting_for", "steps", "message", "sim_date"):
        assert key in body, f"the phone reads {key} and it is missing"


def test_home_carries_timing_and_status_but_no_finding(client, patient_id):
    body = client.get(f"/api/patients/{patient_id}/home").json()

    # Invariant 6, at the one endpoint a family reads. There is no field here
    # that could hold a result, and this fails if one is ever added.
    allowed_step_keys = {"id", "kind", "what", "when", "state", "travels", "is_next"}
    for step in body["steps"]:
        assert set(step) == allowed_step_keys, "a new field reached the family's screen"
        assert step["state"] in {"done", "waiting", "ahead"}

    allowed_wait_keys = {"kind", "what", "earliest", "latest", "certain"}
    for wait in body["waiting_for"]:
        assert set(wait) == allowed_wait_keys


def test_a_booked_date_is_told_apart_from_a_forecast(client, patient_id):
    body = client.get(f"/api/patients/{patient_id}/home").json()

    for wait in body["waiting_for"]:
        if wait["certain"]:
            # A booking is a fact the hospital committed to: one date, not a
            # range. Showing a family a range here would invent doubt.
            assert wait["earliest"] == wait["latest"]


def test_a_family_cleared_to_travel_is_told_what_to_bring_and_where_to_go(client):
    ids = [p["id"] for p in client.get("/api/patients").json()]
    homes = [client.get(f"/api/patients/{pid}/home").json() for pid in ids]
    going = [h for h in homes if h["decision"] == "go"]
    waiting = [h for h in homes if h["decision"] != "go"]

    assert going, "the demo cohort has families cleared to travel"
    assert all(h["what_to_bring"] and h["where_to_go_first"] for h in going)
    # Nobody packs a bag for a trip they have not been told to take.
    assert all(h["what_to_bring"] == [] and h["where_to_go_first"] is None for h in waiting)


def test_home_404s_for_a_patient_that_does_not_exist(client):
    assert client.get("/api/patients/NOBODY/home").status_code == 404


def test_choosing_a_language_changes_the_record_not_the_view(client, patient_id):
    before = client.get("/api/patients").json()
    original = next(p for p in before if p["id"] == patient_id)["language"]
    target = "bn" if original != "bn" else "or"

    result = client.patch(
        f"/api/patients/{patient_id}/language",
        json={"language": target, "chosen_by": "Vikash"},
    )
    assert result.status_code == 200
    assert result.json()["changed"] is True

    # The record itself moved — every message from here on is rendered in the
    # new language because the renderer reads the patient, not a request field.
    after = client.get("/api/patients").json()
    assert next(p for p in after if p["id"] == patient_id)["language"] == target
    assert client.get(f"/api/patients/{patient_id}/home").json()["patient"]["language"] == target


def test_the_family_asking_is_logged_as_a_fact_they_asserted(client, patient_id):
    client.patch(f"/api/patients/{patient_id}/language", json={"language": "or"})

    entries = client.get(f"/api/ledger/{patient_id}").json()["entries"]
    rows = [e for e in entries if "Odia" in e["claim"]]
    assert rows, "the family's own request left no trace in the ledger"
    # Who said it matters: this is the family's assertion, not the hospital's.
    assert rows[-1]["source"] == "caregiver_reply"
    assert client.get(f"/api/ledger/{patient_id}").json()["intact"] is True


def test_picking_the_language_you_already_have_costs_nothing(client, patient_id):
    current = client.get(f"/api/patients/{patient_id}/home").json()["patient"]["language"]
    size_before = len(client.get(f"/api/ledger/{patient_id}").json()["entries"])

    result = client.patch(f"/api/patients/{patient_id}/language", json={"language": current})

    assert result.json()["changed"] is False
    # No re-render, and no ledger row: a no-op must not cost an API call or
    # bury the entries that do assert something new (invariant 5).
    after = len(client.get(f"/api/ledger/{patient_id}").json()["entries"])
    assert after == size_before


def test_an_unsupported_language_is_refused_rather_than_guessed(client, patient_id):
    assert client.patch(
        f"/api/patients/{patient_id}/language", json={"language": "fr"}
    ).status_code == 422


def test_language_404s_for_a_patient_that_does_not_exist(client):
    response = client.patch("/api/patients/NOBODY/language", json={"language": "hi"})
    assert response.status_code == 404


def test_every_supported_language_round_trips(client, patient_id):
    for language in Language:
        client.patch(f"/api/patients/{patient_id}/language", json={"language": language.value})
        body = client.get(f"/api/patients/{patient_id}/home").json()
        assert body["patient"]["language"] == language.value


def test_transcription_refuses_to_answer_without_a_key(client, patient_id):
    # Credential-free, so speech-to-text cannot run. It must say so plainly
    # rather than returning an empty transcript, which would read as "the
    # family said nothing" — a different and much worse claim.
    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("reply.webm", b"0" * 2000, "audio/webm")},
        data={"patient_id": patient_id},
    )
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_a_too_short_recording_is_refused_before_it_is_paid_for(client, patient_id):
    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("reply.webm", b"0" * 10, "audio/webm")},
        data={"patient_id": patient_id},
    )
    assert response.status_code in {422, 503}


@pytest.mark.parametrize(
    ("name", "content_type", "expected"),
    [
        ("reply.m4a", "audio/m4a", "reply.m4a"),
        ("reply.webm", "audio/webm", "reply.webm"),
        ("REPLY.M4A", None, "REPLY.M4A"),
        # A phone recorder with no usable name: the content type decides.
        (None, "audio/m4a", "reply.m4a"),
        ("recording", "audio/mp4", "reply.m4a"),
        ("clip.bin", "audio/aac", "reply.m4a"),
        ("clip", "audio/webm;codecs=opus", "reply.webm"),
        # Nothing to go on: the browser default, as before.
        (None, None, "reply.webm"),
    ],
)
def test_whisper_is_told_the_format_even_when_the_upload_has_no_useful_name(
    name, content_type, expected
):
    from saathi.api.family import audio_filename

    assert audio_filename(name, content_type) == expected


def test_a_phone_can_reach_the_api_from_the_dev_ports_it_uses(client):
    # Native apps are not bound by CORS; the browsers are: the staff apps, the
    # demo stage and the family app's Expo web build.
    for origin in ("http://localhost:5173", "http://localhost:5174", "http://localhost:8081"):
        response = client.options(
            "/api/health",
            headers={"origin": origin, "access-control-request-method": "GET"},
        )
        assert response.headers.get("access-control-allow-origin") == origin, origin


def test_a_phone_recording_keeps_its_file_name_on_the_way_to_the_service(
    client, patient_id, monkeypatch
):
    """The Android app uploads AAC in an m4a container.

    Both services read the format from the file name, so the name has to arrive
    intact — a recording renamed to `.webm` on the way is simply rejected, and
    the family is told their voice could not be heard for a reason nobody can
    see. Checked with a stand-in, since the suite never touches the network.
    """
    from saathi.api import family
    from saathi.ports.speech import Transcript

    seen: dict = {}

    class Listener:
        def describe(self) -> str:
            return "stand-in"

        def transcribe(self, audio, filename, language):
            seen.update(audio=audio, filename=filename, language=language)
            return Transcript(text="कल की तारीख़ क्या है", language=language, heard_by="stand-in")

    monkeypatch.setattr(family, "_listeners", lambda settings: [Listener()])

    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("reply.m4a", b"0" * 2000, "audio/m4a")},
        data={"patient_id": patient_id, "language": "hi"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "कल की तारीख़ क्या है"
    assert body["sent"] is False  # words handed back for the family to check, nothing sent
    assert seen["filename"] == "reply.m4a"
    assert seen["language"] == "hi"


def test_a_second_listener_is_asked_when_the_first_hears_nothing(
    client, patient_id, monkeypatch
):
    """Sarvam leads; Whisper is behind it, not instead of it.

    A service that returns nothing is not the same as a family that said
    nothing, so the next one is asked before anyone gives up.
    """
    from saathi.api import family
    from saathi.ports.speech import Transcript

    asked: list[str] = []

    class Deaf:
        def describe(self) -> str:
            return "deaf"

        def transcribe(self, audio, filename, language):
            asked.append("deaf")
            return None

    class Hears:
        def describe(self) -> str:
            return "hears"

        def transcribe(self, audio, filename, language):
            asked.append("hears")
            return Transcript(text="सुन लिया", language=language, heard_by="hears")

    monkeypatch.setattr(family, "_listeners", lambda settings: [Deaf(), Hears()])

    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("reply.m4a", b"0" * 2000, "audio/m4a")},
        data={"patient_id": patient_id, "language": "hi"},
    )

    assert asked == ["deaf", "hears"]
    assert response.json()["text"] == "सुन लिया"
    assert response.json()["model"] == "hears", "the screen should name who actually heard it"


def test_reading_aloud_needs_a_voice_and_says_so_plainly(client, patient_id):
    """No browser ships an Odia voice, so without Sarvam there is no voice at
    all — and a button that does nothing is worse than one that is absent."""
    response = client.post(
        f"/api/patients/{patient_id}/voice/say",
        json={"text": "अभी घर पर रहें।"},
    )

    assert response.status_code == 503
    assert "SARVAM_KEY" in response.json()["detail"]


def test_reading_aloud_hands_back_audio_in_the_family_s_language(
    client, patient_id, monkeypatch
):
    from saathi.api import family
    from saathi.ports.speech import Utterance

    said: dict = {}

    class Voice:
        def describe(self) -> str:
            return "stand-in voice"

        def say(self, text, language):
            said.update(text=text, language=language)
            return Utterance(
                audio=b"RIFF....", media_type="audio/wav", language=language,
                spoken_by="stand-in voice",
            )

    monkeypatch.setattr(family, "_speaker", lambda settings: Voice())

    response = client.post(
        f"/api/patients/{patient_id}/voice/say",
        json={"text": "अभी घर पर रहें।"},
    )

    assert response.status_code == 200
    assert response.content == b"RIFF...."
    assert response.headers["content-type"].startswith("audio/")
    assert response.headers["x-spoken-by"] == "stand-in voice"
    # The family's own language, taken from their record rather than a guess.
    assert said["language"] == "hi"
