import { useEffect, useState } from "react";
import { ApiError, records, type CareStep, type Patient, type StepStatus } from "@saathi/api-client";
import { Card, Chip, Notice, fmtDate, stepName } from "@saathi/ui-web";
import { usePersona } from "../session";

const REPORTS = new Set(["pathology_report", "radiology_report"]);
const STATUSES: StepStatus[] = ["not_scheduled", "scheduled", "completed", "pending_result", "cancelled"];

const detail = (e: unknown) =>
  e instanceof ApiError && typeof e.detail === "string" ? e.detail : String(e);

/**
 * One family's record, editable where a person is the source of the fact.
 *
 * A report is never marked available by editing its status: it goes through
 * "Mark released", which writes the ledger row and re-plans the family. Only a
 * desk (or an administrator) may do that; the server refuses anyone else.
 */
export function RecordEditor({
  patient,
  steps,
  onChanged,
}: {
  patient: Patient;
  steps: CareStep[];
  onChanged: () => void;
}) {
  const { persona } = usePersona();
  const canRelease = persona.role === "desk" || persona.role === "admin";
  const [form, setForm] = useState({
    name: patient.name ?? "",
    home_district: patient.home_district,
    home_distance_km: String(patient.home_distance_km),
    caregiver_phone: patient.caregiver_phone,
  });
  const [message, setMessage] = useState<{ tone: "calm" | "warn"; text: string } | null>(null);

  useEffect(() => {
    setForm({
      name: patient.name ?? "",
      home_district: patient.home_district,
      home_distance_km: String(patient.home_distance_km),
      caregiver_phone: patient.caregiver_phone,
    });
  }, [patient]);

  const run = async (work: () => Promise<unknown>, done: string) => {
    setMessage(null);
    try {
      await work();
      setMessage({ tone: "calm", text: done });
      onChanged();
    } catch (e) {
      setMessage({ tone: "warn", text: detail(e) });
    }
  };

  return (
    <>
      <Card title="The family" hint={patient.id}>
        <div className="iss-fields">
          <label>
            Family name
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label>
            District
            <input value={form.home_district} onChange={(e) => setForm({ ...form, home_district: e.target.value })} />
          </label>
          <label>
            Distance (km)
            <input
              type="number"
              min={0}
              value={form.home_distance_km}
              onChange={(e) => setForm({ ...form, home_distance_km: e.target.value })}
            />
          </label>
          <label>
            Caregiver phone
            <input value={form.caregiver_phone} onChange={(e) => setForm({ ...form, caregiver_phone: e.target.value })} />
          </label>
        </div>
        <div className="iss-actions" style={{ marginTop: 10 }}>
          <button
            type="button"
            className="btn primary"
            onClick={() =>
              run(
                () =>
                  records.editPatient(patient.id, {
                    name: form.name,
                    home_district: form.home_district,
                    home_distance_km: Number(form.home_distance_km),
                    caregiver_phone: form.caregiver_phone,
                  }),
                "Saved, and the family re-planned.",
              )
            }
          >
            Save
          </button>
        </div>
      </Card>

      <Card title="Their steps" hint={`${steps.length} on record`} flush={steps.length > 0}>
        {steps.length === 0 ? (
          <p className="empty">No steps yet. Add them from the Desk.</p>
        ) : (
          <table className="audit-table">
            <thead>
              <tr>
                <th>Step</th>
                <th>Status</th>
                <th>Scheduled</th>
                <th>Done / sampled</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {steps.map((step) => (
                <tr key={step.id}>
                  <td>
                    {stepName(step.kind)}
                    <div className="hint mono">{step.queue ?? ""}</div>
                  </td>
                  <td>
                    {step.status === "result_available" ? (
                      <Chip tone="go">released</Chip>
                    ) : (
                      <select
                        value={step.status}
                        onChange={(e) =>
                          run(
                            () => records.editStep(step.id, { status: e.target.value as StepStatus }),
                            "Status changed, and the family re-planned.",
                          )
                        }
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>
                            {s.replace(/_/g, " ")}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td>
                    <input
                      type="date"
                      value={step.scheduled_for ?? ""}
                      onChange={(e) =>
                        run(
                          () => records.editStep(step.id, { scheduled_for: e.target.value || null }),
                          "Date changed, and the family re-planned.",
                        )
                      }
                    />
                  </td>
                  <td>{step.completed_on ? fmtDate(step.completed_on) : "—"}</td>
                  <td style={{ textAlign: "right" }}>
                    {REPORTS.has(step.kind) && step.status === "pending_result" && canRelease && (
                      <button
                        type="button"
                        className="btn small"
                        onClick={() =>
                          run(() => records.release(step.id, persona.name), "Recorded as released.")
                        }
                      >
                        Mark released
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
    </>
  );
}
