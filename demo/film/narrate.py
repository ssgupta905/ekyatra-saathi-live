"""The voice-over, spoken by Sarvam.

The same service the family's phone uses for read-aloud speaks the narration
here. That is deliberate: a film about a system whose voice is Sarvam should
not be narrated by something else.

One file per segment, named by segment id. A segment with no line is skipped
rather than written as silence; the assembler pads to length either way.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import wave

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "build/vo"
ROOT = HERE.parents[1]

sys.path.insert(0, str(ROOT / "backend"))


def plan() -> list[dict]:
    """Read the plan from its one home rather than restating it here."""
    script = (
        "import('./plan.mjs').then(m => "
        "console.log(JSON.stringify(m.PLAN.map(s => ({id: s.id, vo: s.vo, seconds: s.seconds})))))"
    )
    raw = subprocess.run(
        ["node", "-e", script], cwd=HERE, capture_output=True, text=True, check=True
    ).stdout
    return json.loads(raw)


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
        line = (seg["vo"] or "").strip()
        if not line:
            continue
        path = OUT / f"{seg['id']}.wav"
        utterance = speech.say(line, "en")
        if utterance is None:
            failed.append(seg["id"])
            print(f"  {seg['id']}: SILENT - sarvam refused")
            continue
        path.write_bytes(utterance.audio)
        with wave.open(str(path)) as handle:
            seconds = handle.getnframes() / handle.getframerate()
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
