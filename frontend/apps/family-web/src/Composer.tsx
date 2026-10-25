import { useRef, useState } from "react";
import { family } from "@saathi/api-client";
import type { Lang, Strings } from "@saathi/i18n";
import { Spark, Wave } from "@saathi/ui-web";

/**
 * How the family says something back: type it, or speak it.
 *
 * Voice is not a nice-to-have here. A caregiver who cannot read their own
 * script has no other way in, and dictating a question in Bhojpuri-accented
 * Hindi is the realistic case, not the exotic one. So the mic is the same size
 * as the send button, not a small icon beside it.
 *
 * Speech and sending are deliberately two steps. `/voice/transcribe` hands back
 * words and nothing else; those words land in the box for the family to read
 * and correct before anything is sent. A mis-heard date in a script the
 * operator cannot read is not a mistake anyone downstream would catch.
 */

type Phase = "idle" | "recording" | "transcribing" | "sending";

export function Composer({
  patientId,
  lang,
  s,
  onSent,
}: {
  patientId: string;
  lang: Lang;
  s: Strings;
  onSent: () => void;
}) {
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [fromVoice, setFromVoice] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const stopRecording = () => {
    recorderRef.current?.stop();
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    recorderRef.current = null;
  };

  const record = async () => {
    if (phase === "recording") {
      stopRecording();
      return;
    }
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        setPhase("transcribing");
        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          const result = await family.transcribe(patientId, blob, lang);
          setText(result.text);
          setFromVoice(true);
        } catch (e) {
          setError(e instanceof Error ? e.message : "could not transcribe");
        } finally {
          setPhase("idle");
        }
      };
      recorder.start();
      recorderRef.current = recorder;
      setPhase("recording");
    } catch {
      // No microphone, or permission refused. Typing still works, and saying
      // so is better than a mic button that silently does nothing.
      setError("microphone unavailable");
    }
  };

  const send = async () => {
    const body = text.trim();
    if (!body) return;
    setPhase("sending");
    setError(null);
    try {
      await family.say(patientId, body);
      setText("");
      setFromVoice(false);
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not send");
    } finally {
      setPhase("idle");
    }
  };

  const busy = phase === "sending" || phase === "transcribing";

  return (
    <div className="fx-composer">
      {fromVoice && text && (
        <span className="fx-voice-note">{s.checkBeforeSending}</span>
      )}
      {error && <span className="fx-composer-error">{error}</span>}

      <div className="fx-composer-row">
        <button
          type="button"
          className={phase === "recording" ? "fx-mic on" : "fx-mic"}
          onClick={record}
          disabled={busy}
          aria-label={s.speak}
        >
          <Wave size={18} />
        </button>

        {phase === "recording" ? (
          <span className="fx-input listening" aria-live="polite">
            <span className="fx-wave" aria-hidden="true">
              <span /><span /><span /><span /><span />
            </span>
            {s.listening}
          </span>
        ) : (
          <input
            className="fx-input"
            value={text}
            lang={lang}
            placeholder={phase === "transcribing" ? s.transcribing : s.askPlaceholder}
            onChange={(event) => {
              setText(event.target.value);
              setFromVoice(false);
            }}
            onKeyDown={(event) => event.key === "Enter" && send()}
            disabled={busy}
          />
        )}

        <button
          type="button"
          className="fx-send"
          onClick={send}
          disabled={busy || !text.trim()}
        >
          {phase === "sending" ? <Spark size={15} /> : s.send}
        </button>
      </div>
    </div>
  );
}
