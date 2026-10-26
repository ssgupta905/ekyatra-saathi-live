import type { CareStep, PlanResponse } from "@saathi/api-client";
import { fmtDate, isReportStep, stepName } from "@saathi/ui-web";

type State = "done" | "ready" | "waiting" | "booked" | "target" | "cancelled";

function stateOf(step: CareStep, targetId: string | null): State {
  if (step.id === targetId) return "target";
  if (step.status === "cancelled") return "cancelled";
  if (step.status === "completed") return "done";
  if (step.status === "result_available") return "ready";
  if (step.status === "pending_result") return "waiting";
  return "booked";
}

const LABEL: Record<State, string> = {
  done: "done",
  ready: "report ready",
  waiting: "waiting",
  booked: "booked",
  target: "the visit",
  cancelled: "cancelled",
};

/**
 * The family's journey as one line you can read in a second: what is done, what
 * is being waited for, and the visit everything leads to. The detail of each
 * step is one layer down; this is only the shape.
 */
export function JourneyStrip({ steps, response }: { steps: CareStep[]; response: PlanResponse | null }) {
  const targetId = response?.plan?.target_step_id ?? null;
  const ordered = [...steps]
    .filter((s) => s.status !== "cancelled")
    .sort((a, b) => (a.scheduled_for ?? a.completed_on ?? "9").localeCompare(b.scheduled_for ?? b.completed_on ?? "9"));
  if (ordered.length === 0) return <p className="empty">No steps on record yet.</p>;

  return (
    <ol className="journey-strip" aria-label="The journey">
      {ordered.map((step) => {
        const state = stateOf(step, targetId);
        const when = step.scheduled_for ?? step.completed_on;
        return (
          <li key={step.id} className={`js-step ${state}`} title={`${stepName(step.kind)} · ${LABEL[state]}`}>
            <span className="js-dot" aria-hidden>
              {state === "done" || state === "ready" ? "✓" : state === "waiting" ? "…" : ""}
            </span>
            <span className="js-name">{stepName(step.kind)}</span>
            <span className="js-when">
              {isReportStep(step.kind) && state === "waiting" ? "waiting" : when ? fmtDate(when) : "—"}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
