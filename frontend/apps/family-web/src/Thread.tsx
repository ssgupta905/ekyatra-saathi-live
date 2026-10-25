import { useEffect, useRef } from "react";
import type { ThreadEntry } from "@saathi/api-client";
import type { Lang, Strings } from "@saathi/i18n";
import { Shield } from "@saathi/ui-web";

/**
 * One conversation, both directions.
 *
 * Not "your notifications" and "your replies" as two lists — a family does not
 * experience it that way, and reading a holding message directly above their
 * own reply to it is the entire reason to show it. Newest at the bottom, like
 * every messaging app anyone has ever used.
 *
 * A clinical question is shown with the note that a person will answer it. That
 * is not an apology for a limitation; it is the product working. Saathi never
 * answers a question about a result, and the family should be able to see that
 * their question was received and routed rather than ignored.
 *
 * Older messages keep the language they were sent in, and say so. A family that
 * switches to Bengali on Tuesday did not retroactively receive Monday's message
 * in Bengali, and rewriting the thread to pretend otherwise would make the one
 * record of what this family was actually told untrue. Without the label the
 * mix reads as a bug; with it, it reads as a receipt.
 */

const SCRIPT_NAME: Record<string, string> = {
  hi: "हिन्दी",
  bn: "বাংলা",
  or: "ଓଡ଼ିଆ",
  en: "English",
};

const time = (iso: string, lang: Lang) =>
  new Intl.DateTimeFormat(lang === "en" ? "en-IN" : `${lang}-IN`, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));

export function Thread({
  entries,
  lang,
  s,
}: {
  entries: ThreadEntry[];
  lang: Lang;
  s: Strings;
}) {
  const boxRef = useRef<HTMLDivElement | null>(null);

  // Stick to the newest message by scrolling *this box* — never
  // `scrollIntoView`, which walks up to whatever ancestor can scroll and on
  // first paint took the whole phone with it, pushing the verdict (the one
  // thing this screen exists to show) above the fold.
  useEffect(() => {
    const box = boxRef.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [entries.length]);

  if (entries.length === 0) return null;

  return (
    <section className="fx-card">
      <h2 className="fx-h2">{s.messages}</h2>
      <div className="fx-thread" ref={boxRef}>
        {entries.map((entry) => {
          // The moment the family changed language, drawn as a divider. This is
          // what turns a thread of two scripts from something that looks broken
          // into something that reads as a record.
          if (entry.kind === "language") {
            return (
              <div className="fx-divider" key={entry.id}>
                <span>
                  {s.languageChanged} · {SCRIPT_NAME[entry.language] ?? entry.body}
                </span>
              </div>
            );
          }
          const mine = entry.direction === "from_family";
          // Only when it differs: labelling every bubble with the language it
          // is plainly written in is noise.
          const sentIn = entry.language && entry.language !== lang ? entry.language : null;
          return (
            <div
              key={entry.id}
              className={`fx-bubble ${mine ? "mine" : "theirs"}${entry.held ? " held" : ""}`}
            >
              <p lang={mine ? lang : (entry.language as Lang)}>{entry.body}</p>
              <span className="fx-bubble-foot">
                <span>{mine ? s.you : "Saathi"}</span>
                <span>{time(entry.sent_at, lang)}</span>
                {sentIn && (
                  <span className="fx-sent-in">{SCRIPT_NAME[sentIn] ?? sentIn}</span>
                )}
              </span>
              {entry.answerable === false && (
                <span className="fx-routed">
                  <Shield size={12} />
                  {s.aPersonWillReply}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
