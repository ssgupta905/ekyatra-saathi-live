"""The voice-over, spoken by Sarvam.

The same service the family's phone uses for read-aloud speaks the narration
here. That is deliberate: a film about a system whose voice is Sarvam should
not be narrated by something else.

Two kinds of audio come out of this.

`<id>.wav` is the English narration. `<id>.hi.wav` is the Hindi the phone
itself was speaking at that moment — the source recordings have no audio track
at all, because `adb screenrecord` captures none, so the read-aloud a viewer
can see happening was never recorded. It is re-spoken here by the same model
(`bulbul:v3`, hi-IN) saying the exact words on the screen, transcribed from
the frames. That is as close to the captured thing as it is possible to get
without the device audio, and it is the real voice saying the real sentence.

A segment with no line is skipped rather than written as silence; the
assembler pads to length either way.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import wave

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "build" / os.environ.get("SAATHI_FILM", "plan") / "vo"
ROOT = HERE.parents[1]

sys.path.insert(0, str(ROOT / "backend"))

#: Two different people, and the difference is the point.
#:
#: The first cut used the service's default voice for both the narration and
#: the phone's read-aloud, so the Hindi sounded like the narrator switching
#: language rather than like a device speaking in the room. A viewer who does
#: not attribute the voice to the phone on screen reads it as badly timed,
#: however well it is timed.
#:
#: The narrator was `ashutosh` and read flat. Sampling ten voices on the same
#: sentence and measuring the spread of their fundamental frequency — a drone
#: has little, a delivery has more — put `anand` half again as varied (46 Hz
#: against 31) while staying clear of the phone's voice. The three most varied
#: overall were female and would have sat on top of `shreya` at 223 Hz, which
#: is the one thing the narrator must not do.
#:
#: Override either without touching this file: SAATHI_NARRATOR, SAATHI_PHONE.
#: The narrator is a US English voice from the operating system, and the
#: family's phone is still Sarvam. That split is deliberate twice over: the
#: film wants a narrator who is clearly not the product, and Sarvam only ships
#: Indian voices — every one of its speakers reads Indian English, which is
#: right for the phone and wrong for a voice-over sitting beside it.
#:
#: `say` rather than a hosted service because there is no other text-to-speech
#: credential in this project: the one hosted option on the existing key was
#: retired by its provider. Samantha is the only US female voice installed.
NARRATOR_VOICE = os.environ.get("SAATHI_NARRATOR_VOICE", "Samantha")
NARRATOR_WPM = os.environ.get("SAATHI_NARRATOR_WPM", "178")
PHONE = os.environ.get("SAATHI_PHONE", "shreya")
PHONE = os.environ.get("SAATHI_PHONE", "shreya")


def plan() -> list[dict]:
    """Read the plan from its one home rather than restating it here."""
    script = (
        f"import('./{os.environ.get('SAATHI_FILM', 'plan')}.mjs').then(m => "
        "console.log(JSON.stringify(m.PLAN.map(s => "
        "({id: s.id, vo: s.vo, seconds: s.seconds, hindi: s.hindi ?? null})))))"
    )
    raw = subprocess.run(
        ["node", "-e", script], cwd=HERE, capture_output=True, text=True, check=True
    ).stdout
    return json.loads(raw)


def _narrate(text: str, path: pathlib.Path) -> float | None:
    """The English voice-over, spoken by the operating system.

    Written straight to a 22 kHz mono WAV because that is what the assembler
    resamples from anyway, and because an AIFF left lying around is one more
    intermediate nobody cleans up.
    """
    aiff = path.with_suffix(".aiff")
    subprocess.run(
        ["say", "-v", NARRATOR_VOICE, "-r", NARRATOR_WPM, "-o", str(aiff), text],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(aiff),
         "-ar", "22050", "-ac", "1", str(path)],
        check=True,
    )
    aiff.unlink(missing_ok=True)
    with wave.open(str(path)) as handle:
        return handle.getnframes() / handle.getframerate()


def _speak(
    speech,
    text: str,
    language: str,
    path: pathlib.Path,
    *,
    speaker: str | None = None,
    pace: float | None = None,
) -> float | None:
    """Say one line and write it down. Returns its length, or None if refused."""
    utterance = speech.say(text, language, speaker=speaker, pace=pace)
    if utterance is None:
        return None
    path.write_bytes(utterance.audio)
    with wave.open(str(path)) as handle:
        return handle.getnframes() / handle.getframerate()


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    key = os.environ.get("SARVAM_KEY", "")
    if not key:
        print("no SARVAM_KEY in .env", file=sys.stderr)
        return 1

    from saathi.adapters.speech.sarvam import SarvamSpeech

    speech = SarvamSpeech(key, timeout=120.0)
    OUT.mkdir(parents=True, exist_ok=True)

    failed: list[str] = []
    for seg in plan():
        hindi = seg.get("hindi")
        if hindi:
            said = _speak(
                speech, hindi["text"], "hi", OUT / f"{seg['id']}.hi.wav", speaker=PHONE
            )
            if said is None:
                failed.append(f"{seg['id']} (hi)")
                print(f"  {seg['id']:14s} SILENT - sarvam refused the Hindi")
            else:
                print(f"  {seg['id']:14s} {said:5.1f}s  hindi, from {hindi['at']}s")

        line = (seg["vo"] or "").strip()
        if not line:
            continue
        seconds = _narrate(line, OUT / f"{seg['id']}.wav")
        if seconds is None:
            failed.append(seg["id"])
            print(f"  {seg['id']:14s} SILENT - sarvam refused")
            continue
        fit = "ok" if seconds <= seg["seconds"] else "OVERRUNS"
        print(f"  {seg['id']:14s} {seconds:5.1f}s / {seg['seconds']:5.1f}s  {fit}")

    if failed:
        # A missing line is a hole in the film, not a cosmetic problem: the
        # picture would run on in silence and the viewer would assume the
        # recording was broken.
        print(f"\n{len(failed)} segment(s) have no voice: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
