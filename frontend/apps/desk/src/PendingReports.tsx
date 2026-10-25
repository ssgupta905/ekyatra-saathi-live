import { useEffect, useState } from "react";
import { api, records, type CareStep, type Patient } from "@saathi/api-client";
import { Card } from "@saathi/ui-web";

import { IDENTITY } from "./identity";

interface Row {
  patient: Patient;
  step: CareStep;
}

/**
 * Reports the desk is still waiting on. Releasing one is the real-world form of
 * confirming a candidate: a person says it is ready, it is written to the
 * ledger, and the family's plan moves at once.
 */
export function PendingReports({ revision, onReleased }: { revision: number; onReleased: () => void }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const patients = await api.patients();
      const steps = await Promise.all(patients.map((p) => api.steps(p.id)));
      if (cancelled) return;
      setRows(
        patients.flatMap((patient, i) =>
          steps[i].filter((s) => s.status === "pending_result").map((step) => ({ patient, step })),
        ),
      );
    })().catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [revision]);

  const release = async (row: Row) => {
    setBusy(row.step.id);
    try {
      await records.release(row.step.id, IDENTITY.name);
      onReleased();
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card
      title="Reports waiting"
      hint={rows.length ? `${rows.length} not yet released` : "none"}
      flush={rows.length > 0}
    >
      {rows.length === 0 ? (
        <p className="empty">No report is waiting.</p>
      ) : (
        <table className="tbl">
          <tbody>
            {rows.map(({ patient, step }) => (
              <tr key={step.id}>
                <td>{patient.name || patient.id}</td>
                <td>{step.kind.replace(/_/g, " ")}</td>
                <td className="mono">{step.completed_on ? `sampled ${step.completed_on}` : ""}</td>
                <td style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    className="btn small"
                    disabled={busy === step.id}
                    onClick={() => release(row(patient, step))}
                  >
                    Mark released
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

const row = (patient: Patient, step: CareStep): Row => ({ patient, step });
