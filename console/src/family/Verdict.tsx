import { useEffect, useState } from "react";
import type { FamilyHome } from "../lib/api";
import { localDate, type Lang, type Strings } from "../lib/i18n";
import { Speaker } from "../ui/icons";

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

/** Read it aloud. For a caregiver who cannot read their own script, this is
 *  not a convenience — it is the only way the message lands. Browser-native,
 *  so it costs nothing and works offline; absent voices simply do nothing. */
function useSpeech(text: string | null, lang: Lang) {
  const [speaking, setSpeaking] = useState(false);
  const voices = typeof window !== "undefined" && "speechSynthesis" in window;

  // Stop talking if the screen goes away mid-sentence.
  useEffect(
    () => () => {
      if (voices) window.speechSynthesis.cancel();
    },
    [voices],
  );

  const speak = () => {
    if (!voices || !text) return;
    window.speechSynthesis.cancel();
    if (speaking) {
      setSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = { hi: "hi-IN", bn: "bn-IN", or: "or-IN", en: "en-IN" }[lang];
    utterance.rate = 0.9;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  return { canSpeak: voices && !!text, speaking, speak };
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
  const { canSpeak, speaking, speak } = useSpeech(sentence, lang);

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
