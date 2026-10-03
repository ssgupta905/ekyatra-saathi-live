import type { FamilyWait } from "../lib/api";
import { localDateShort, stepWord, type Lang, type Strings } from "../lib/i18n";
import { CheckCircle, Clock } from "../ui/icons";

/**
 * Why the answer is the answer, in the only form that is useful to a family:
 * *what* is being waited for, and *when* it is expected.
 *
 * No probability, no coverage level, no score. A booked date is shown as one
 * date and called confirmed; a forecast is shown as a range and never dressed
 * up as a promise. That distinction is the backend's `certain` flag, which is
 * true only when the window came from a booking rather than the predictor —
 * so the difference the family sees is a difference that actually exists.
 */
export function Why({
  waits,
  lang,
  s,
}: {
  waits: FamilyWait[];
  lang: Lang;
  s: Strings;
}) {
  if (waits.length === 0) return null;

  return (
    <section className="fx-card">
      <h2 className="fx-h2">{s.why}</h2>
      <ul className="fx-waits">
        {waits.map((wait) => (
          <li key={wait.kind} className={wait.certain ? "certain" : ""}>
            <span className="fx-wait-icon">
              {wait.certain ? <CheckCircle size={16} /> : <Clock size={16} />}
            </span>
            <span className="fx-wait-what">{stepWord(wait.kind, wait.what, lang)}</span>
            <span className="fx-wait-when">
              {wait.certain
                ? `${s.onThisDay} · ${localDateShort(wait.earliest, lang)}`
                : wait.earliest && wait.latest
                  ? `${s.expectedBetween} ${localDateShort(wait.earliest, lang)} – ${localDateShort(wait.latest, lang)}`
                  : "—"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
