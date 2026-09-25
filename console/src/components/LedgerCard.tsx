import type { LedgerView } from "../lib/api";

/**
 * The provenance view. Every claim Saathi has made about this patient, and the
 * record it came from. `intact` is the hash-chain check — if it ever shows
 * false, the ledger has been altered and nothing below it can be trusted.
 */
export function LedgerCard({ ledger }: { ledger: LedgerView | null }) {
  if (!ledger) {
    return (
      <section className="card">
        <h2>Evidence ledger</h2>
        <p className="empty">Nothing recorded yet.</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>
        Evidence ledger{" "}
        {ledger.intact ? (
          <span style={{ color: "var(--go)" }}>· chain intact</span>
        ) : (
          <span className="error">· CHAIN BROKEN</span>
        )}
      </h2>
      {ledger.entries.length === 0 ? (
        <p className="empty">No entries for this patient yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Claim</th>
              <th>Source</th>
              <th>Record</th>
              <th>Hash</th>
            </tr>
          </thead>
          <tbody>
            {ledger.entries.map((entry) => (
              <tr key={entry.id}>
                <td>{entry.claim}</td>
                <td>{entry.source}</td>
                <td className="mono">{entry.source_record_id}</td>
                <td className="mono">{entry.entry_hash}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
