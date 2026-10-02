import { useEffect, useState } from "react";
import { admin } from "../lib/api";
import { Badge, Card } from "../ui/primitives";

interface AuditRow {
  id: string;
  patient_id: string;
  source: string;
  source_record_id: string;
  claim: string;
  recorded_at: string;
  entry_hash: string;
}

/**
 * Every action and its source, across every patient — the admin's audit
 * trail. Reads the same hash-chained ledger every other view does; nothing
 * new is stored for this screen, only a cross-patient filter over it.
 */
export function AuditLog() {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [intact, setIntact] = useState<boolean | null>(null);

  useEffect(() => {
    admin
      .ledger()
      .then((body) => {
        setRows(body.entries as unknown as AuditRow[]);
        setIntact(body.intact);
      })
      .catch(() => undefined);
  }, []);

  return (
    <Card
      title="Audit log"
      hint="Every action and its source"
      aside={intact !== null && <Badge tone={intact ? "go" : "critical"}>{intact ? "chain intact" : "BROKEN"}</Badge>}
      flush
    >
      <table className="audit-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Patient</th>
            <th>Source</th>
            <th>Claim</th>
            <th>Hash</th>
          </tr>
        </thead>
        <tbody>
          {rows
            .slice()
            .reverse()
            .slice(0, 200)
            .map((row) => (
              <tr key={row.id}>
                <td className="mono">{new Date(row.recorded_at).toLocaleString()}</td>
                <td>{row.patient_id}</td>
                <td>
                  <Badge tone="info">{row.source}</Badge>
                </td>
                <td>{row.claim}</td>
                <td className="mono">{row.entry_hash}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </Card>
  );
}
