import type { Alert } from "@saathi/api-client";
import { ALERT_LABELS, ALERT_MEANING, ALERT_TONE } from "../explain";
import { fmtStamp, humanize } from "../format";
import { Card, Chip, Disclosure } from "../primitives";

/**
 * Signals, not scores.
 *
 * There is no ranking number anywhere in this panel, and the data model has no
 * field to hold one. A navigator sees what changed and decides; the deliberate
 * absence is the point, so the card says so.
 */
export function AlertsPanel({
  alerts,
  onSelect,
}: {
  alerts: Alert[];
  onSelect?: (patientId: string) => void;
}) {
  return (
    <Card
      title="Needs a person"
      hint={`${alerts.length} open`}
      flush={alerts.length > 0}
      note="Ordered by when they were raised. No priority score — Saathi shows the signal and a navigator decides who to call first."
    >
      {alerts.length === 0 ? (
        <p className="empty">Nothing open. Every family is on a plan Saathi can state.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Family</th>
                <th>Signal</th>
                <th>What was observed</th>
                <th>Raised</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td>
                    {onSelect ? (
                      <button
                        type="button"
                        className="cite"
                        onClick={() => onSelect(a.patient_id)}
                        title={`Open ${a.patient_id}`}
                      >
                        {a.patient_id}
                      </button>
                    ) : (
                      <span className="mono">{a.patient_id}</span>
                    )}
                  </td>
                  <td>
                    <Chip tone={ALERT_TONE[a.kind] ?? "neutral"}>
                      <span className="dot" />
                      {ALERT_LABELS[a.kind] ?? humanize(a.kind)}
                    </Chip>
                  </td>
                  <td style={{ maxWidth: "46ch" }}>
                    <div style={{ color: "var(--ink)" }}>{a.detail}</div>
                    <Disclosure summary="Why this is a signal">
                      <div style={{ fontSize: 12.5, color: "var(--ink-3)", maxWidth: "58ch" }}>
                        {ALERT_MEANING[a.kind] ?? "Raised by the planner."}
                      </div>
                    </Disclosure>
                  </td>
                  <td style={{ color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                    {fmtStamp(a.raised_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
