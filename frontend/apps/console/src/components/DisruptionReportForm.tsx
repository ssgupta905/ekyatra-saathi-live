/**
 * A desk's one-tap report: a resource is unavailable for a window. This is
 * the whole of step 1 in the brief's disruption loop — everything after it
 * (the holding message, the re-solve, the ranked options) happens because
 * the runner reacted, not because this form decided anything.
 */

import { useCallback, useState } from "react";
import { disruptions, live, type DisruptionKind } from "@saathi/api-client";
import { Card, Notice } from "@saathi/ui-web";

/** `base` plus `days`, both as `YYYY-MM-DD`. Parsed as UTC so adding days
 *  never drifts across a local-timezone midnight. */
function addDays(base: string, days: number): string {
  const [y, m, d] = base.split("-").map(Number);
  const next = new Date(Date.UTC(y, m - 1, d + days));
  return next.toISOString().slice(0, 10);
}

const KINDS: { value: DisruptionKind; label: string }[] = [
  { value: "machine_down", label: "Machine down" },
  { value: "staff_unavailable", label: "Staff unavailable" },
  { value: "stock_delay", label: "Stock delay" },
];

export function DisruptionReportForm({
  defaultResourceId,
  onReported,
}: {
  defaultResourceId?: string;
  onReported: (affected: string[]) => void;
}) {
  const [resourceId, setResourceId] = useState(defaultResourceId ?? "");
  const [kind, setKind] = useState<DisruptionKind>("machine_down");
  const [note, setNote] = useState("");
  const [days, setDays] = useState(2);
  const [status, setStatus] = useState<string | null>(null);

  const report = useCallback(async () => {
    // The simulated world's date, not the operator's wall clock — a
    // disruption dated against real time would never overlap a step
    // scheduled against simulated time.
    const snapshot = await live.snapshot();
    const today = snapshot.current;
    const result = await disruptions.raise({
      resource_id: resourceId,
      kind,
      unavailable_from: today,
      unavailable_to: addDays(today, days),
      note,
    });
    setStatus(`Reported — ${result.affected_patient_ids.length} families affected`);
    onReported(result.affected_patient_ids);
  }, [resourceId, kind, note, days, onReported]);

  return (
    <Card title="Report an issue" hint="One tap: machine down, person away, stock late">
      <div className="disruption-form">
        <label>
          Resource
          <input value={resourceId} onChange={(e) => setResourceId(e.target.value)} />
        </label>
        <label>
          Kind
          <select value={kind} onChange={(e) => setKind(e.target.value as DisruptionKind)}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Days unavailable
          <input
            type="number"
            min={1}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          />
        </label>
        <label className="grow">
          Note
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. out of service until Saturday"
          />
        </label>
        <button type="button" onClick={report} disabled={!resourceId}>
          Report
        </button>
      </div>
      {status && <Notice tone="calm">{status}</Notice>}
    </Card>
  );
}
