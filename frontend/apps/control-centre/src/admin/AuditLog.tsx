import { useEffect, useState } from "react";
import { config, type AuditPage } from "@saathi/api-client";
import { Badge, Card } from "@saathi/ui-web";

const SOURCES = ["", "hospital_feed", "abdm", "navigator", "caregiver_reply", "derived"];
const PAGE = 100;

/**
 * Every fact the system has asserted, across every family and the registry,
 * newest first. Filter by source or family, search the claim, page through.
 * Reads the same hash-chained ledger every other view does; nothing new is
 * stored for this screen.
 */
export function AuditLog() {
  const [page, setPage] = useState<AuditPage | null>(null);
  const [source, setSource] = useState("");
  const [patient, setPatient] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      config
        .audit({ source, patient_id: patient.trim(), q: q.trim(), limit: PAGE, offset })
        .then(setPage)
        .catch(() => undefined);
    }, 200);
    return () => clearTimeout(timer);
  }, [source, patient, q, offset]);

  useEffect(() => setOffset(0), [source, patient, q]);

  const total = page?.total ?? 0;

  return (
    <Card
      title="Audit log"
      hint={page ? `${total} entries${total > PAGE ? ` · ${offset + 1}–${Math.min(offset + PAGE, total)}` : ""}` : "loading…"}
      aside={page && <Badge tone={page.intact ? "go" : "critical"}>{page.intact ? "chain intact" : "BROKEN"}</Badge>}
      flush
    >
      <div className="iss-fields cc-audit-filters">
        <label>
          Source
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {s ? s.replace(/_/g, " ") : "any"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Family (or "registry")
          <input value={patient} placeholder="e.g. P-ANITA" onChange={(e) => setPatient(e.target.value)} />
        </label>
        <label>
          Search claims
          <input value={q} placeholder="e.g. released, centre" onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>
      <table className="audit-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Family</th>
            <th>Source</th>
            <th>Claim</th>
            <th>By</th>
            <th>Hash</th>
          </tr>
        </thead>
        <tbody>
          {(page?.entries ?? []).map((row) => {
            const by = (row.metadata.by ?? row.metadata.confirmed_by ?? row.metadata.chosen_by) as string | undefined;
            return (
              <tr key={row.id}>
                <td className="mono">{new Date(row.recorded_at).toLocaleString()}</td>
                <td>{row.patient_id}</td>
                <td>
                  <Badge tone="neutral">{row.source.replace(/_/g, " ")}</Badge>
                </td>
                <td>{row.claim}</td>
                <td>{by ?? "—"}</td>
                <td className="mono">{row.entry_hash}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {total > PAGE && (
        <div className="iss-actions cc-pager">
          <button type="button" className="btn small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Newer
          </button>
          <button type="button" className="btn small" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
            Older
          </button>
        </div>
      )}
    </Card>
  );
}
