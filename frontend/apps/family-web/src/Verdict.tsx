import { useCallback, useEffect, useRef, useState } from "react";
import { speakMessage, type FamilyHome } from "@saathi/api-client";
import { localDate, type Lang, type Strings } from "@saathi/i18n";
import { Speaker } from "@saathi/ui-web";

/**
 * The whole screen, really. Everything else on the family app is detail.
 *
 * One word, one date, one sentence, in that order of size — because the
 * question a family opens this app with is "do we get on the bus or not", and
 * an answer they have to read twice has failed. The word is a label for
 * `plan.decision`; the sentence is the message the language layer wrote and
 * the guard passed. If the guard held it, the sentence is replaced by "someone
 * will call you", which is true, rather than by a substitute we invented here.
 */

const WORD = (decision: string | null, s: Strings) =>
  decision === "go" ? s.come : decision === "wait" ? s.wait : s.notYet;

/** Read it aloud.
 *
 *  For a caregiver who cannot read their own script this is not a convenience
 *  — it is the only way the message lands. It used to use the browser's own
 *  voice, which costs nothing and works offline, and which **has no Odia voice
 *  at all**: for an Odia family the button was a control that did nothing,
 *  silently, which is the worst way for an accessibility feature to fail.
 *
 *  So the server speaks instead, through a service that covers all three
 *  languages. The browser is still the fallback, because a working voice in
 *  two languages beats none in three, and because it keeps working offline.
 */
function useSpeech(patientId: string | undefined, text: string | null, lang: Lang) {
  const [speaking, setSpeaking] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const browserVoices = typeof window !== "undefined" && "speechSynthesis" in window;

  const stop = useCallback(() => {
    if (browserVoices) window.speechSynthesis.cancel();
    const playing = audioRef.current;
    if (playing) {
      playing.pause();
      URL.revokeObjectURL(playing.src);
      audioRef.current = null;
    }
    setSpeaking(false);
  }, [browserVoices]);

  // Stop talking if the screen goes away mid-sentence.
  useEffect(() => stop, [stop]);

  const speakInBrowser = () => {
    if (!browserVoices || !text) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = { hi: "hi-IN", bn: "bn-IN", or: "or-IN", en: "en-IN" }[lang];
    utterance.rate = 0.9;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
  };

  const speak = async () => {
    if (!text) return;
    if (speaking) return stop();
    setSpeaking(true);
    try {
      const audio = patientId ? await speakMessage(patientId, text, lang) : null;
      if (audio) {
        const element = new Audio(URL.createObjectURL(audio));
        audioRef.current = element;
        element.onended = () => setSpeaking(false);
        element.onerror = () => setSpeaking(false);
        await element.play();
        return;
      }
    } catch {
      // Fall through: a voice that could not be fetched is not a reason to
      // leave the family with nothing.
    }
    speakInBrowser();
    if (!browserVoices) setSpeaking(false);
  };

  return { canSpeak: !!text, speaking, speak };
}

export function Verdict({
  home,
  lang,
  s,
}: {
  home: FamilyHome | null;
  lang: Lang;
  s: Strings;
}) {
  const held = home?.message?.held ?? false;
  const sentence = held ? s.personCalling : (home?.message?.body ?? null);
  const { canSpeak, speaking, speak } = useSpeech(home?.patient.id, sentence, lang);

  if (!home || !home.decision) {
    return (
      <section className="fx-verdict loading">
        <span className="fx-word">·</span>
        <p className="fx-sentence">{s.noPlanYet}</p>
      </section>
    );
  }

  return (
    <section className={`fx-verdict ${home.decision}`}>
      <span className="fx-word">{WORD(home.decision, s)}</span>

      {home.decision === "go" && home.travel_on && (
        <span className="fx-date">
          <span className="fx-date-label">{s.travelOn}</span>
          {localDate(home.travel_on, lang)}
        </span>
      )}

      {sentence && (
        <p className={held ? "fx-sentence held" : "fx-sentence"} lang={lang}>
          {sentence}
        </p>
      )}

      {canSpeak && (
        <button
          type="button"
          className={speaking ? "fx-speak on" : "fx-speak"}
          onClick={speak}
          aria-label={s.speak}
        >
          <Speaker size={18} />
          {speaking ? s.reading : s.speak}
        </button>
      )}
    </section>
  );
}
