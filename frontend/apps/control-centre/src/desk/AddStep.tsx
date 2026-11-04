import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  records,
  type Forecast,
  type Patient,
  type StepStatus,
} from "@saathi/api-client";
import { Card, Notice } from "@saathi/ui-web";

const KINDS = [
  "consult",
  "biopsy",
  "bloods",
  "scan",
  "pet_ct",
  "pathology_report",
  "radiology_report",
  "review_consult",
  "joint_clinic",
  "treatment",
  "maintenance_dose",
  "echo_review",
  "dialysis_session",
  "nephrology_review",
  "discharge_review",
  "wound_check",
] as const;
const REPORTS = new Set(["pathology_report", "radiology_report"]);
const STATUSES: StepStatus[] = ["not_scheduled", "scheduled", "completed", "pending_result", "cancelled"];

/**
 * One step of a family's journey: a visit, or a report they are waiting on.
 *
 * A pending report needs two things the planner cannot invent: which lab queue
 * it sits in, and the day the sample was taken. The form asks for exactly those
 * and the server says, on entry, whether it can forecast that queue yet.
 */
export function AddStep({ revision, onAdded }: { revision: number; onAdded: () => void }) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientId, setPatientId] = useState("");
  const [kind, setKind] = useState<string>("pathology_report");
  const [status, setStatus] = useState<StepStatus>("pending_result");
  const [scheduledFor, setScheduledFor] = useState("");
  const [completedOn, setCompletedOn] = useState("");
  const [queue, setQueue] = useState("pathology_report");
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.patients().then((rows) => {
      setPatients(rows);
      setPatientId((current) => current || rows[0]?.id || "");
    });
  }, [revision]);

  const isReport = REPORTS.has(kind);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setForecast(null);
    try {
      const result = await records.addStep(patientId, {
        kind,
        status,
        scheduled_for: scheduledFor || null,
        completed_on: completedOn || null,
        queue: queue || null,
      });
      setForecast(result.forecast);
      onAdded();
    } catch (e) {
      setError(e instanceof ApiError && typeof e.detail === "string" ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Add a step" hint="a visit, or a report they are waiting on">
      {patients.length === 0 ? (
        <p className="empty">Register a family first.</p>
      ) : (
        <>
          <div className="iss-fields">
            <label>
              Family
              <select value={patientId} onChange={(e) => setPatientId(e.target.value)}>
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name ? `${p.name} · ${p.id}` : p.id}
                  </option>
                ))}
              </select>
            </label>
            <label>
              What
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  if (REPORTS.has(e.target.value)) setQueue(e.target.value);
                  else setQueue(e.target.value);
                }}
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Status
              <select value={status} onChange={(e) => setStatus(e.target.value as StepStatus)}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Scheduled for
              <input type="date" value={scheduledFor} onChange={(e) => setScheduledFor(e.target.value)} />
            </label>
            <label>
              {isReport ? "Sample taken on" : "Done on"}
              <input type="date" value={completedOn} onChange={(e) => setCompletedOn(e.target.value)} />
            </label>
            <label>
              Queue
              <input value={queue} onChange={(e) => setQueue(e.target.value)} />
            </label>
          </div>
          <div className="iss-actions" style={{ marginTop: 10 }}>
            <button type="button" className="btn primary" disabled={busy || !patientId} onClick={submit}>
              {busy ? "saving…" : "Add step"}
            </button>
          </div>
        </>
      )}
      {error && <Notice tone="warn">{error}</Notice>}
      {forecast?.note && <Notice tone="warn">{forecast.note}</Notice>}
      {forecast && !forecast.note && (
        <Notice tone="calm">
          Forecast for {forecast.queue} is calibrated on {forecast.observations} past reports.
        </Notice>
      )}
    </Card>
  );
}
