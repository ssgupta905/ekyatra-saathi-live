"""Narration for the film, spoken by Kokoro — or Sarvam when it cannot be.

    python demo/narrate.py                 # every line
    python demo/narrate.py --part compact  # only that cut's lines

**Why the compact cut is read by Sarvam on purpose.** Kokoro is American
English, and this film is full of words it has no idea about: Gaya,
Muzaffarpur, Nalanda, dharamshala, Kamla Devi, ABHA, Tata Memorial. It says
them the way an American reads them off a page, which is distracting at best
and, for an Indian audience, slightly insulting. Sarvam's `en-IN` voices are
built for exactly this and get them right, so the ten-minute cut is read by
one and the engine is pinned rather than left to a fallback.

One WAV per line, written to `demo/film/public/vo/<id>.wav`, with a JSON index
beside them carrying each line's duration so the composition can lay picture
against speech without anybody timing it by hand.

**Kokoro first, Sarvam second, and the film says which.** Kokoro runs offline
and sounds better for long English narration; Sarvam is already wired, already
paid for, and has read every take this week. Falling back is a normal outcome,
not a failure, and it is recorded in the index so a listener is never told the
film used one when it used the other.

Nothing here reads the vernacular. The app's own voice — Hindi, Bengali, Tamil
through Sarvam's `bulbul:v3` — is the thing being demonstrated, and it is
recorded from the handset inside the clips. Narration explains in English and
stays out of the way of it.
"""

from __future__ import annotations

import json
import os
import sys
import wave
from pathlib import Path

HERE = Path(__file__).parent
VO = HERE / "film" / "public" / "vo"
SCRIPT = HERE / "film" / "src" / "script.json"


def _seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def _with_kokoro(lines: list[dict]) -> str | None:
    """Speak every line with Kokoro. Returns the engine name, or None."""
    try:
        import soundfile as sf
        from kokoro import KPipeline
    except Exception as exc:  # noqa: BLE001 - any import problem is a fallback
        print(f"  kokoro unavailable ({type(exc).__name__}), falling back")
        return None

    try:
        # `a` is American English. `bf_emma`/`am_michael` read long-form better
        # than the default; a demo narrator reading for nine minutes needs a
        # voice that does not tire the ear.
        pipeline = KPipeline(lang_code="a")
        voice = os.environ.get("KOKORO_VOICE", "am_michael")
        # Brisk, not hurried. At 0.98 the read was measured and slightly
        # ponderous over nine minutes; 1.08 keeps every word distinct while
        # giving the film pace. Past about 1.15 the clause breaks disappear
        # and it starts to sound like a disclaimer being read out.
        speed = float(os.environ.get("KOKORO_SPEED", "1.08"))
        for line in lines:
            out = VO / f"{line['id']}.wav"
            chunks = [audio for _, _, audio in pipeline(line["text"], voice=voice, speed=speed)]
            if not chunks:
                raise RuntimeError(f"kokoro produced nothing for {line['id']}")
            import numpy as np

            sf.write(out, np.concatenate(chunks), 24000)
            print(f"    {line['id']}  {_seconds(out):5.1f}s  {line['text'][:58]}")
        return f"kokoro · {voice}"
    except Exception as exc:  # noqa: BLE001
        print(f"  kokoro failed partway ({type(exc).__name__}: {exc}), falling back")
        return None


def _with_sarvam(lines: list[dict]) -> str:
    """Speak every line with Sarvam, in Indian English."""
    import httpx

    key = os.environ.get("SARVAM_KEY")
    if not key:
        raise SystemExit("  neither Kokoro nor SARVAM_KEY is available; no narration possible")

    # `anand` reads long-form at a measured pace and handles the place names
    # this film is made of. Pace 1.15 is where the voice stops being leisurely
    # and before it starts clipping its own consonants; past about 1.25 the
    # model ignores the increase anyway.
    speaker = os.environ.get("SARVAM_SPEAKER", "anand")
    pace = float(os.environ.get("SARVAM_PACE", "1.15"))

    for line in lines:
        out = VO / f"{line['id']}.wav"
        response = httpx.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={"api-subscription-key": key},
            json={
                "inputs": [line["text"]],
                "target_language_code": "en-IN",
                "speaker": speaker,
                "model": "bulbul:v3",
                "speech_sample_rate": 24000,
                "pace": pace,
            },
            timeout=180,
        )
        response.raise_for_status()
        import base64

        out.write_bytes(base64.b64decode(response.json()["audios"][0]))
        print(f"    {line['id']}  {_seconds(out):5.1f}s  {line['text'][:58]}")
    return f"sarvam · bulbul:v3 · {speaker} · en-IN"


def main() -> None:
    if not SCRIPT.exists():
        raise SystemExit(f"  no script at {SCRIPT}")
    script = json.loads(SCRIPT.read_text(encoding="utf-8"))
    VO.mkdir(parents=True, exist_ok=True)

    # One cut at a time, so re-reading the compact script does not re-record
    # nineteen minutes of narration the long film has already been cut against.
    part = None
    if "--part" in sys.argv:
        part = sys.argv[sys.argv.index("--part") + 1]
    lines = [
        line
        for line in script["lines"]
        if part is None or (line.get("part") or "main") == part
    ]
    if not lines:
        raise SystemExit(f"  no lines with part={part!r}")
    if part:
        print(f"  speaking {len(lines)} line(s) of the {part} cut")

    forced = os.environ.get("NARRATOR", "").lower()
    engine = None
    if forced != "sarvam":
        engine = _with_kokoro(lines)
    if engine is None:
        engine = _with_sarvam(lines)

    # Durations go back into the script so the composition lays picture against
    # speech from measurement rather than guesswork. A caption timed by hand
    # drifts the moment a line is reworded.
    for line in lines:
        line["seconds"] = round(_seconds(VO / f"{line['id']}.wav"), 3)
    # Keyed by cut, so one engine's name never stands for a reel it did not read.
    script.setdefault("engines", {})[part or "main"] = engine
    script["total_seconds"] = round(sum(line["seconds"] for line in lines), 2)
    SCRIPT.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")

    total = script["total_seconds"]
    print(f"\n  {len(lines)} lines, {total / 60:.1f} min of narration, spoken by {engine}\n")


if __name__ == "__main__":
    sys.exit(main())
