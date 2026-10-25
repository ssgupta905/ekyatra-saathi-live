import type { CareStep, PlanResponse } from "@saathi/api-client";
import { fmtDate, fmtWhen, isReportStep, isSatisfied, queueLabel, statusLabel, statusTone, stepName, Badge, Card, Chip, CheckCircle, Clock, Doc, Pin } from "@saathi/ui-web";

/**
 * The journey as a family experiences it: which steps are behind them, which
 * one is being decided, and which of them are results that nobody travels for.
 */

const legGlyph = (step: CareStep) => {
  if (isSatisfied(step)) return <CheckCircle size={15} className="go" />;
  if (step.status === "pending_result") return <Clock size={15} />;
  return isReportStep(step.kind) ? <Doc size={15} /> : <Pin size={15} />;
};

export function JourneyStepper({
  steps,
  response,
}: {
  steps: CareStep[];
  response: PlanResponse | null;
}) {
  const targetId = response?.plan?.target_step_id ?? null;
  const bundled = new Set(response?.plan?.bundled_step_ids ?? []);

  return (
    <Card
      title="Journey"
      hint={`${steps.filter(isSatisfied).length} of ${steps.length} steps behind them`}
      flush
      note="Report steps are marked “no journey” — their result reaches the family without anyone travelling for it."
    >
      <div className="journey">
        {steps.map((step) => {
          const tone = statusTone(step.status);
          const when = step.scheduled_for ?? step.completed_on ?? step.result_available_on;
          return (
            <div
              key={step.id}
              className={`leg${step.id === targetId ? " is-target" : ""}`}
              style={{ color: isSatisfied(step) ? "var(--go)" : undefined }}
            >
              <div className="mark" style={{ color: tone === "go" ? "var(--go)" : "var(--ink-4)" }}>
                {legGlyph(step)}
              </div>
              <div style={{ color: "var(--ink)" }}>
                <div className="name">
                  {stepName(step.kind)}
                  {step.id === targetId && (
                    <span style={{ marginLeft: 8 }}>
                      <Chip tone="info">being decided</Chip>
                    </span>
                  )}
                  {bundled.has(step.id) && (
                    <span style={{ marginLeft: 8 }}>
                      <Chip tone="go">same journey</Chip>
                    </span>
                  )}
                </div>
                <div className="when">
                  {when ? `${fmtDate(when)} · ${fmtWhen(when)}` : "no date on record"}
                  {step.queue && <> · {queueLabel(step.queue)} queue</>}
                  {isReportStep(step.kind) && <> · no journey</>}
                </div>
              </div>
              <div className="right">
                <Badge tone={tone === "critical" ? "critical" : tone === "go" ? "go" : tone === "wait" ? "wait" : "neutral"}>
                  {statusLabel(step.status)}
                </Badge>
                <span className="mono" style={{ color: "var(--ink-4)", fontSize: 11 }}>
                  {step.id}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
