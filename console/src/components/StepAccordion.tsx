import type { ReactNode } from "react";
import { Chevron } from "../ui/icons";

export type StepState = "done" | "active" | "waiting" | "blocked" | "neutral";

export interface Step {
  id: string;
  title: string;
  /** One line that answers the step without opening it. */
  summary: ReactNode;
  state?: StepState;
  /** Rendered only when the step is open. */
  content: ReactNode;
}

/**
 * A process as a numbered list. Every step is visible at once as a single
 * line, so the whole process is covered; any one step opens in place for the
 * detail, and only one is open at a time, so the screen never piles up.
 */
export function StepAccordion({
  steps,
  open,
  onOpen,
}: {
  steps: Step[];
  open: string | null;
  onOpen: (id: string | null) => void;
}) {
  return (
    <ol className="steps">
      {steps.map((step, index) => {
        const isOpen = open === step.id;
        return (
          <li key={step.id} className={`step ${step.state ?? "neutral"}${isOpen ? " open" : ""}`}>
            <button
              type="button"
              className="step-head"
              aria-expanded={isOpen}
              onClick={() => onOpen(isOpen ? null : step.id)}
            >
              <span className="step-num">{index + 1}</span>
              <span className="step-text">
                <span className="step-title">{step.title}</span>
                <span className="step-summary">{step.summary}</span>
              </span>
              <Chevron size={12} className="step-chevron" />
            </button>
            {isOpen && <div className="step-body panel-fade">{step.content}</div>}
          </li>
        );
      })}
    </ol>
  );
}
