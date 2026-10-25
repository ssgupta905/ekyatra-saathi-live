import { type ReportRow, type ReportState } from "@saathi/api-client";
import { Chip, Cite, fmtDate, stepName } from "@saathi/ui-web";

const STATE: Record<ReportState, { label: string; tone: "go" | "wait" | "uncertain" | "critical" | "neutral" }> = {
  overdue: { label: "overdue", tone: "critical" },
  due: { label: "due now", tone: "wait" },
  waiting: { label: "not due yet", tone: "neutral" },
  no_forecast: { label: "no forecast yet", tone: "uncertain" },
  no_window: { label: "no sample date", tone: "uncertain" },
  released: { label: "released", tone: "go" },
  cancelled: { label: "cancelled", tone: "neutral" },
};

/**
 * Reports as a desk tracks them: what, which queue, when the sample was taken,
 * the window it should land in, and — once it has — when and on whose word.
 * Status, timing and provenance only; there is nothing here about what a
 * report says, because the system holds nothing about that.
 */
export function ReportTable({
  rows,
  showFamily = true,
  onOpenFamily,
}: {
  rows: ReportRow[];
  showFamily?: boolean;
  onOpenFamily?: (patientId: string) => void;
}) {
  if (rows.length === 0) return <p className="empty">No reports match.</p>;
  return (
    <table className="audit-table cc-reports">
      <thead>
        <tr>
          {showFamily && <th>Family</th>}
          <th>Report</th>
          <th>Queue</th>
          <th>Sample taken</th>
          <th>Expected window</th>
          <th>Where it stands</th>
          <th>Released</th>
          <th>On whose word</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const state = STATE[r.state];
          return (
            <tr key={r.step_id}>
              {showFamily && (
                <td>
                  {onOpenFamily ? (
                    <button type="button" className="linkish" onClick={() => onOpenFamily(r.patient_id)}>
                      {r.patient_name || r.patient_id}
                    </button>
                  ) : (
                    r.patient_name || r.patient_id
                  )}
                  <div className="hint">{r.district} · {r.hospital_id}</div>
                </td>
              )}
              <td>{stepName(r.kind)}</td>
              <td className="mono">{r.queue ?? "—"}</td>
              <td>{r.sample_taken_on ? fmtDate(r.sample_taken_on) : "—"}</td>
              <td>
                {r.window ? (
                  r.window.calibrated ? (
                    <>
                      {fmtDate(r.window.earliest)} – {fmtDate(r.window.latest)}
                      <div className="hint">
                        {Math.round((1 - r.window.alpha) * 100)}% coverage · n={r.window.n_calibration}
                      </div>
                    </>
                  ) : (
                    <span className="hint">too few past reports (n={r.window.n_calibration})</span>
                  )
                ) : (
                  "—"
                )}
              </td>
              <td>
                <Chip tone={state.tone}>{state.label}</Chip>
              </td>
              <td>
                {r.released_on ? fmtDate(r.released_on) : "—"}
                {r.turnaround_days != null && <div className="hint">{r.turnaround_days} days</div>}
              </td>
              <td>
                {r.release ? (
                  <Cite ledgerId={r.release.ledger_id}>{r.release.by ?? "hospital feed"}</Cite>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
