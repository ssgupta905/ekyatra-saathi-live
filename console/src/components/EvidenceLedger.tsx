import { useEffect, useRef } from "react";
import type { Citation } from "../lib/citation";
import type { LedgerView } from "../lib/api";
import { fmtStamp, sourceLabel } from "../lib/format";
import { Badge, Card, Notice } from "../ui/primitives";
import { CheckCircle, Shield, Stop } from "../ui/icons";

/**
 * Provenance, in the order it was written.
 *
 * Entries are hash-chained, so `intact` is a check rather than a claim: if it
 * ever reads broken, an entry was altered after the fact and nothing above it
 * on the page can be trusted. Clicking a citation anywhere in the console
 * scrolls the matching row here and flashes it.
 */
export function EvidenceLedger({
  ledger,
  focused,
}: {
  ledger: LedgerView | null;
  focused: Citation | null;
}) {
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());

  useEffect(() => {
    if (!focused) return;
    // Jump rather than animate: smooth scrolling is frame-driven and silently
    // does nothing in a background tab, and a cited source should always land.
    rowRefs.current.get(focused.id)?.scrollIntoView({ block: "center" });
  }, [focused]);

  return (
    <Card
      title="Evidence ledger"
      hint="append-only, hash-chained"
      flush={Boolean(ledger?.entries.length)}
      aside={
        ledger ? (
          ledger.intact ? (
            <Badge tone="go" icon={<CheckCircle size={13} />}>
              Chain intact
            </Badge>
          ) : (
            <Badge tone="critical" solid icon={<Stop size={13} />}>
              Chain broken
            </Badge>
          )
        ) : undefined
      }
      note={
        <>
          Each row’s hash covers the row before it. Every message Saathi sends carries
          the ids of the rows it rests on — and a sentence with no row behind it is not
          sent.
        </>
      }
    >
      {!ledger ? (
        <p className="empty">Loading provenance…</p>
      ) : !ledger.intact ? (
        <Notice tone="stop">
          <strong>The chain does not verify.</strong> An entry was altered or removed
          after it was written. Treat every decision on this page as unsourced until the
          ledger is restored.
        </Notice>
      ) : ledger.entries.length === 0 ? (
        <p className="empty">Nothing recorded for this patient yet.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Claim</th>
                <th>Where it came from</th>
                <th>Record</th>
                <th>Written</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {ledger.entries.map((e) => (
                <tr
                  // Keying on the click count remounts the row, so the flash
                  // replays even when the same citation is clicked twice.
                  key={focused?.id === e.id ? `${e.id}-${focused.n}` : e.id}
                  ref={(el) => {
                    if (el) rowRefs.current.set(e.id, el);
                    else rowRefs.current.delete(e.id);
                  }}
                  className={focused?.id === e.id ? "flash" : undefined}
                >
                  <td style={{ color: "var(--ink)" }}>{e.claim}</td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <Shield size={12} />
                      {sourceLabel(e.source)}
                    </span>
                  </td>
                  <td className="mono">{e.source_record_id}</td>
                  <td style={{ color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                    {fmtStamp(e.recorded_at)}
                  </td>
                  <td className="mono" style={{ color: "var(--ink-4)" }}>
                    {e.entry_hash}
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
