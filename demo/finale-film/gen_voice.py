"""Voice every scene with Kokoro, one continuous take each, and write durations."""
import json, re, sys
from pathlib import Path
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).parent
MODEL = Path.home() / ".cache/kokoro"
SAY = [
    (r"\bEKYATRA\b", "Ek-yaatra"), (r"\bSaathi\b", "Saathee"), (r"\bFHIR\b", "fire"),
    (r"\bIRCTC\b", "I. R. C. T. C."), (r"\bOpenEMR\b", "Open E M R"), (r"\bOdia\b", "Oriya"),
    (r"\bJan Aushadhi\b", "Jun Aushadhee"), (r"\bGaya\b", "Gayaa"), (r"\bKamla\b", "Kumla"),
    (r"\bdharamshala\b", "dharam-shaala"), (r"\bBeckn\b", "Beckon"),
]

def spoken(text: str) -> str:
    for pat, rep in SAY:
        text = re.sub(pat, rep, text)
    return text

def main(only=None):
    d = json.loads((HERE / "narration.json").read_text())
    k = Kokoro(str(MODEL / "kokoro-v1.0.onnx"), str(MODEL / "voices-v1.0.bin"))
    out = HERE / "public/audio"; out.mkdir(parents=True, exist_ok=True)
    durations = json.loads((HERE / "src/durations.json").read_text()) if (HERE / "src/durations.json").exists() else {}
    for s in d["scenes"]:
        if only and s["id"] not in only:
            continue
        audio, sr = k.create(spoken(s["text"]), voice=d["voice"], speed=d["speed"], lang="en-us")
        sf.write(out / f"{s['id']}.wav", audio, sr)
        durations[s["id"]] = round(len(audio) / sr, 3)
        print(s["id"], durations[s["id"]], flush=True)
    (HERE / "src/durations.json").write_text(json.dumps(durations, indent=1))
    print("total", round(sum(durations.values()), 1))

if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
