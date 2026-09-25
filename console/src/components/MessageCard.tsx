import type { PlanResponse, Patient } from "../lib/api";
import { LANGUAGE_NAMES } from "../lib/api";

/**
 * What was actually sent to the family — or, when the guard blocked it, what
 * was withheld and why. A navigator should never have to guess which happened.
 */
export function MessageCard({
  plan,
  patient,
}: {
  plan: PlanResponse | null;
  patient: Patient;
}) {
  return (
    <section className="card">
      <h2>Message to caregiver · {LANGUAGE_NAMES[patient.language]}</h2>

      {plan?.routed_to_care_team ? (
        <p className="notice" style={{ margin: 0 }}>
          <strong>Not sent.</strong> Routed to the care team
          {plan.escalation ? `: ${plan.escalation}` : "."}
        </p>
      ) : plan?.message_body ? (
        <blockquote style={{ margin: 0, fontSize: 16, lineHeight: 1.6 }}>
          {plan.message_body}
        </blockquote>
      ) : (
        <p className="empty">
          No message composed — the language layer is off (ANTHROPIC_API_KEY unset). The
          plan above was still decided in full.
        </p>
      )}
    </section>
  );
}
