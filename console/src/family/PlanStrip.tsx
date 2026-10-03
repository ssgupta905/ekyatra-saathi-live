import type { FamilyStep } from "../lib/api";
import { localDateShort, stepWord, type Lang, type Strings } from "../lib/i18n";
import { CheckCircle, Clock, Doc, Pin } from "../ui/icons";

/**
 * The journey as a single vertical line, oldest at the top.
 *
 * The hospital's own board draws this as a branching graph, because a
 * navigator needs to see what is waiting on what. A family does not: they need
 * to know what is behind them, what is being waited for, and what is next. So
 * this is the same care pathway with the branches collapsed into time order —
 * three states, one line, no graph to read.
 *
 * A step nobody travels for is marked as such. A family that packs a bag for a
 * report has lost two days and a fare for nothing, and that is exactly the
 * mistake this whole project exists to stop.
 */

const ICON = (step: FamilyStep) => {
  if (step.state === "done") return <CheckCircle size={14} />;
  if (step.state === "waiting") return <Clock size={14} />;
  return step.travels ? <Pin size={14} /> : <Doc size={14} />;
};

export function PlanStrip({
  steps,
  lang,
  s,
}: {
  steps: FamilyStep[];
  lang: Lang;
  s: Strings;
}) {
  if (steps.length === 0) return null;
  const label = { done: s.done, waiting: s.waiting, ahead: s.ahead };

  return (
    <section className="fx-card">
      <h2 className="fx-h2">{s.plan}</h2>
      <ol className="fx-steps">
        {steps.map((step) => (
          <li
            key={step.id}
            className={`${step.state}${step.is_next ? " next" : ""}`}
          >
            <span className="fx-step-rail">
              <span className="fx-step-dot">{ICON(step)}</span>
            </span>
            <span className="fx-step-body">
              <span className="fx-step-what">{stepWord(step.kind, step.what, lang)}</span>
              <span className="fx-step-meta">
                {step.when ? localDateShort(step.when, lang) : "—"}
                <span className="fx-step-state">{label[step.state]}</span>
                {!step.travels && (
                  <span className="fx-step-tag">{s.noTravelNeeded}</span>
                )}
              </span>
            </span>
            {step.is_next && <span className="fx-step-next">{s.nextVisit}</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}
