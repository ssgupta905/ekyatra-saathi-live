import { useCallback, useEffect, useMemo, useState } from "react";
import { network, type NetworkBoard, type NetworkFamily, type StageKind, type StageState } from "@saathi/api-client";
import { Card, Chip } from "@saathi/ui-web";
import { errorText } from "../components/RecordForm";
import { EmptyState, SkeletonRows } from "../ui/kit";
import { Graph } from "../ui/icons";
import { useWorld } from "../world";

/** The columns, in the order a journey meets them, in words a navigator says. */
const COLUMNS: { kind: StageKind; label: string }[] = [
  { kind: "tests", label: "Tests" },
  { kind: "reports", label: "Reports" },
  { kind: "insurance", label: "Scheme" },
  { kind: "pharmacy", label: "Pharmacy" },
  { kind: "ride", label: "Ride" },
  { kind: "stay", label: "Stay" },
  { kind: "documents", label: "Papers" },
  { kind: "visit", label: "Visit" },
];

const MARK: Record<StageState, { sign: string; word: string; tone: "go" | "wait" | "critical" | "neutral" }> = {
  done: { sign: "✓", word: "done", tone: "go" },
  waiting: { sign: "…", word: "in progress", tone: "wait" },
  problem: { sign: "!", word: "problem", tone: "critical" },
  upcoming: { sign: "·", word: "not started", tone: "neutral" },
};

/**
 * Every family against every stage of its journey, so a navigator sees at a
 * glance who is holding each one up. A family with a failed party comes first;
 * the right-hand list says how many journeys each party is holding.
 */
export function Network({ onOpen }: { onOpen: (patientId: string) => void }) {
  const world = useWorld();
  const [board, setBoard] = useState<NetworkBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyStuck, setOnlyStuck] = useState(false);

  const load = useCallback(() => {
    network.board().then(setBoard).catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load, world.cohortRevision]);
  // Simulated organisations answer on their own clock, so look again now and then.
  useEffect(() => {
    const id = window.setInterval(load, 10_000);
    return () => window.clearInterval(id);
  }, [load]);

  const rows = useMemo(
    () => (board?.families ?? []).filter((f) => !onlyStuck || f.stuck),
    [board, onlyStuck],
  );

  if (error) return <p className="auth-error" role="alert">{error}</p>;
  if (!board) return <SkeletonRows rows={6} />;
  if (board.families.length === 0) {
    return (
      <EmptyState title="No journeys to show yet" icon={<Graph />}>
        A family appears here once they have steps on record.
      </EmptyState>
    );
  }

  const cell = (family: NetworkFamily, kind: StageKind) => {
    const stage = family.stages.find((s) => s.kind === kind);
    if (!stage) return <span className="hint" aria-label="not part of this journey">–</span>;
    const m = MARK[stage.state];
    return (
      <span title={stage.detail || undefined}>
        <Chip tone={m.tone}>
          <span aria-hidden>{m.sign}</span>
          <span className="sr-only"> {m.word}</span>
        </Chip>
        {stage.party && <span className="hint" style={{ display: "block", fontSize: 11 }}>{stage.party}</span>}
      </span>
    );
  };

  return (
    <div className="stack">
      <Card
        title="Every journey"
        hint={`${board.families.length} families · ${board.families.filter((f) => f.stuck).length} stuck`}
        aside={
          <label className="cc-check" style={{ margin: 0 }}>
            <input type="checkbox" checked={onlyStuck} onChange={(e) => setOnlyStuck(e.target.checked)} /> Only the stuck
          </label>
        }
      >
        {rows.length === 0 ? (
          <p className="empty">Nothing is stuck. Every journey is moving.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Family</th>
                  {COLUMNS.map((c) => <th key={c.kind}>{c.label}</th>)}
                  <th>Progress</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((f) => (
                  <tr key={f.patient_id}>
                    <td>
                      <button type="button" className="btn small" onClick={() => onOpen(f.patient_id)}>
                        {f.name}
                      </button>
                      <div className="hint">{f.district}</div>
                    </td>
                    {COLUMNS.map((c) => <td key={c.kind}>{cell(f, c.kind)}</td>)}
                    <td>{f.done} of {f.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Who is holding journeys" hint="Journeys each party has yet to finish">
        {board.parties.length === 0 ? (
          <p className="empty">Nobody is holding anything up.</p>
        ) : (
          <table className="audit-table">
            <thead>
              <tr><th>Party</th><th>In progress</th><th>Problem</th></tr>
            </thead>
            <tbody>
              {board.parties.map((p) => (
                <tr key={p.party}>
                  <td>{p.party}</td>
                  <td>{p.waiting}</td>
                  <td>{p.problem > 0 ? <Chip tone="critical">{p.problem}</Chip> : 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
