import { useCallback, useEffect, useState } from "react";
import { requests as requestsApi, type ReasoningLine, type ReasoningStep } from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { SkeletonRows } from "../ui/kit";

/**
 * The agent's working, in the order it happened.
 *
 * This is a view over the real event stream. Every line was published by the
 * code that did the work and carries the duration that work actually took —
 * nothing here is written to describe the work, because a description written
 * alongside the work is a thing that can disagree with it. A log claiming
 * "checked the hospital" when no request was made would be worse than no log.
 *
 * The one piece of judgement in this component is what it does *not* hide.
 * `[GUARD]` lines are the ones that look bad — a message held back, a question
 * refused, a clinical term blocked — and they are the strongest evidence the
 * system has that its own limits are real rather than described. They are
 * styled to stand out rather than filtered away. A reader who never sees a
 * refusal has no reason to believe refusals happen.
 *
 * Durations are shown only where they were measured. A missing one is left
 * missing rather than rendered as zero, which would read as instantaneous.
 */

/** Why each label exists, shown on hover so the vocabulary needs no legend. */
const MEANING: Record<ReasoningStep, string> = {
  EVENT: "Something happened that nobody here chose",
  CHECK: "A fact source was consulted",
  INFER: "A reading was made from what was found — a proposal, never a decision",
  SEARCH: "Options were enumerated",
  PLAN: "A plan was computed",
  GUARD: "Something was refused",
  HUMAN: "A person decided",
  WRITE: "A record was written",
  NOTIFY: "A family was told, or asked",
};

/** The design system's own vocabulary, not a parallel one. */
const TONE: Partial<Record<ReasoningStep, "uncertain" | "go" | "info">> = {
  // A refusal is the line a reader should notice, so it gets the colour that
  // draws the eye rather than being quietly neutral.
  GUARD: "uncertain",
  HUMAN: "go",
  INFER: "info",
};

export function ReasoningLog({
  patientId,
  revision,
}: {
  patientId?: string;
  revision: number;
}) {
  const [lines, setLines] = useState<ReasoningLine[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [only, setOnly] = useState<ReasoningStep | null>(null);

  const load = useCallback(() => {
    requestsApi
      .reasoning(patientId)
      .then(setLines)
      .catch((e: Error) => setError(e.message));
  }, [patientId]);

  useEffect(load, [load, revision]);

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (lines === null) return <SkeletonRows rows={4} />;

  const shown = only ? lines.filter((line) => line.step === only) : lines;
  const steps = [...new Set(lines.map((line) => line.step))];

  return (
    <Card
      title="How this was worked out"
      hint={
        patientId
          ? `Every step behind ${patientId}'s current answer, with what each one cost.`
          : "Every step the system has taken, with what each one cost."
      }
    >
      {steps.length > 1 && (
        <div className="log-filter">
          <button
            type="button"
            className={only === null ? "" : "ghost"}
            onClick={() => setOnly(null)}
          >
            everything
          </button>
          {steps.map((step) => (
            <button
              key={step}
              type="button"
              title={MEANING[step]}
              className={only === step ? "" : "ghost"}
              onClick={() => setOnly(step)}
            >
              {step.toLowerCase()}
            </button>
          ))}
        </div>
      )}

      {shown.length === 0 ? (
        <p className="muted">
          Nothing yet. The log fills as the system reads the hospital and plans.
        </p>
      ) : (
        <ol className="reasoning">
          {shown.map((line) => (
            <li key={`${line.seq}-${line.at}`} className={`step step-${line.step.toLowerCase()}`}>
              {/* `title` on the wrapper rather than the Chip: Chip takes a
                  tone and children, and widening it for a tooltip here would
                  change a shared primitive for one screen's benefit. */}
              <span title={MEANING[line.step]}>
                <Chip tone={TONE[line.step]}>{line.step}</Chip>
              </span>
              <span className="step-text">
                {line.summary}
                {line.repeated > 1 && <em className="step-again"> ×{line.repeated}</em>}
              </span>
              {/* Measured, or absent. Never a zero standing in for unknown. */}
              {line.duration_ms !== null && (
                <span className="step-cost">{Math.round(line.duration_ms)}ms</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
