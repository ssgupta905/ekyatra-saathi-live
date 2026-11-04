import { type Patient, type PlanResponse, LANGUAGE_NAMES, fmtAgo, fmtMs } from "@saathi/api-client";
import { DECISION_PLAIN, fmtDate, fmtWhen, stepName, Badge, Chip, DecisionGlyph, Pin, Wave } from "@saathi/ui-web";

/**
 * The answer, before the reasoning.
 *
 * A navigator on a call has seconds, so the verdict is the largest thing on the
 * page and it is a word, not a score. The trace below it is what they read when
 * the family asks "why".
 */
export function DecisionHero({
  response,
  patient,
  targetKind,
  justChanged,
}: {
  response: PlanResponse | null;
  patient: Patient;
  targetKind: string | null;
  /** True when this answer changed while the page was open. */
  justChanged?: boolean;
}) {
  if (!response?.plan) {
    return (
      <section className="card">
        <div className="hero">
          <div className="kicker">Visit decision</div>
          <div className="verdict">
            <div className="skeleton" style={{ width: 180, height: 38 }} />
          </div>
          <p className="plain" style={{ color: "var(--ink-4)" }}>
            Planning {patient.id}…
          </p>
        </div>
      </section>
    );
  }

  const { decision, travel_on, bundled_step_ids } = response.plan;

  return (
    <section className="card">
      <div className={`hero ${decision}${justChanged ? " just-changed" : ""}`}>
        <div className="kicker">
          Visit decision · {targetKind ? stepName(targetKind) : "next travel step"}
        </div>

        <div className="verdict">
          <span className="glyph" style={{ display: "flex" }}>
            <DecisionGlyph decision={decision} size={34} />
          </span>
          <span className="word">
            {decision === "go" ? "Go" : decision === "wait" ? "Wait" : decision === "replan" ? "Re-plan" : "Uncertain"}
          </span>
        </div>

        <p className="plain">{DECISION_PLAIN[decision]}</p>

        <div className="facts">
          {travel_on ? (
            <Badge tone="go" solid icon={<Pin size={13} />}>
              Travel {fmtDate(travel_on)} · {fmtWhen(travel_on)}
            </Badge>
          ) : (
            <Chip>No travel date promised</Chip>
          )}
          <Chip>
            {patient.home_district} · {Math.round(patient.home_distance_km)} km each way
          </Chip>
          <Chip>Family hears {LANGUAGE_NAMES[patient.language]}</Chip>
          {bundled_step_ids.length > 0 && (
            <Chip tone="go">
              {bundled_step_ids.length} step{bundled_step_ids.length === 1 ? "" : "s"} bundled
              into one journey
            </Chip>
          )}
        </div>

        {/* Where this answer came from, and what it cost — so the page never
            implies a decision is instantaneous or eternal. */}
        {response.computed_at && (
          <div className="stamp">
            <span style={{ display: "inline-flex", color: "var(--ink-4)" }}>
              <Wave size={13} />
            </span>
            <span>
              decided on {response.sim_date ? fmtDate(response.sim_date) : "—"}, recomputed{" "}
              {fmtAgo(response.computed_at)}
            </span>
            {response.plan_ms != null && (
              <span className="mono">planner {fmtMs(response.plan_ms)}</span>
            )}
            {response.render_ms != null && (
              <span className="mono">
                {response.rendered_by ?? "render"} {fmtMs(response.render_ms)}
              </span>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
