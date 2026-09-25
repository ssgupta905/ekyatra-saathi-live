import type { PlanResponse } from "../lib/api";

/**
 * The plan as a navigator needs to read it: the decision, why, and — when the
 * answer is "wait" — the calibrated window they can quote to the family.
 */
export function PlanCard({ plan }: { plan: PlanResponse | null }) {
  if (!plan?.plan) {
    return (
      <section className="card">
        <h2>Plan</h2>
        <p className="empty">No plan yet.</p>
      </section>
    );
  }

  const { decision, travel_on, rationale, blocked_by, what_to_bring, where_to_go_first } =
    plan.plan;

  return (
    <section className="card">
      <h2>Plan</h2>
      <div className="decision">
        <span className={`badge ${decision}`}>{decision.toUpperCase()}</span>
        {travel_on && <strong>travel {travel_on}</strong>}
        {decision !== "go" && <span className="empty">no date promised</span>}
      </div>
      <p className="rationale">{rationale}</p>

      {blocked_by.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Waiting on</th>
              <th>Status</th>
              <th>Expected ready</th>
            </tr>
          </thead>
          <tbody>
            {blocked_by.map((b) => (
              <tr key={b.step_id}>
                <td>{b.kind.replace(/_/g, " ")}</td>
                <td>
                  <span className={`status ${b.status}`}>{b.status.replace(/_/g, " ")}</span>
                </td>
                <td>
                  {b.expected_ready ? (
                    b.expected_ready.calibrated ? (
                      <>
                        {b.expected_ready.earliest} – {b.expected_ready.latest}{" "}
                        <span className="empty">
                          ({Math.round((1 - b.expected_ready.alpha) * 100)}% coverage, n=
                          {b.expected_ready.n_calibration})
                        </span>
                      </>
                    ) : (
                      <span className="empty">
                        not enough history to give a window (n={b.expected_ready.n_calibration})
                      </span>
                    )
                  ) : (
                    <span className="empty">unknown</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {where_to_go_first && (
        <p style={{ marginTop: 14 }}>
          <strong>Go first to:</strong> {where_to_go_first}
        </p>
      )}

      {what_to_bring.length > 0 && (
        <>
          <p style={{ marginBottom: 4 }}>
            <strong>Bring:</strong>
          </p>
          <ul className="plain">
            {what_to_bring.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}

      {plan.escalation && (
        <p className="notice" style={{ marginTop: 14, marginBottom: 0 }}>
          Escalated to a navigator: {plan.escalation}
        </p>
      )}
    </section>
  );
}
