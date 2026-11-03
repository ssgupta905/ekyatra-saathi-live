import { useCallback, useEffect, useState } from "react";
import { boards as boardApi, type PlanBoard as Board } from "@saathi/api-client";
import { Card, Chip, Notice, PlanBoard } from "@saathi/ui-web";

/**
 * Every board a navigator is holding, worst first.
 *
 * Ordered by what is in the family's way and then by how far they would have to
 * travel. That is not a score and there is no field to put one in — it is two
 * facts a navigator can see and check, arranged so the family who would lose
 * the most from a wasted journey is the one at the top of the screen.
 */
export function PlanBoardList({ revision }: { revision: number }) {
  const [rows, setRows] = useState<Board[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const refresh = useCallback(() => {
    boardApi
      .all()
      .then((result) => {
        setRows(result.boards);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(refresh, [refresh, revision]);

  if (error) return <Notice tone="stop">Could not load the boards: {error}</Notice>;
  if (!rows) {
    return (
      <Card title="Plan boards" hint="loading…">
        <div style={{ display: "grid", gap: 10 }}>
          <div className="skeleton" style={{ height: 52 }} />
          <div className="skeleton" style={{ height: 52, width: "84%" }} />
        </div>
      </Card>
    );
  }

  const selected = rows.find((row) => row.patient.id === open) ?? null;

  return (
    <>
      <Card
        title="Plan boards"
        hint={`${rows.length} families`}
        flush
        note="Ordered by what is in the family's way, then by distance from the hospital. No priority score exists — the order is two facts you can check."
      >
        <div className="board-list">
          {rows.map((row) => {
            const blocked = row.waiting_on.length;
            const tone =
              row.decision === "go" ? "go" : row.decision === "wait" || row.decision === "replan" ? "wait" : "uncertain";
            return (
              <button
                type="button"
                className="board-row"
                key={row.patient.id}
                aria-pressed={open === row.patient.id}
                onClick={() => setOpen(open === row.patient.id ? null : row.patient.id)}
              >
                <span className="br-id">{row.patient.id}</span>
                <span className="br-where">
                  {row.patient.district} · {row.patient.distance_km} km
                </span>
                <span className="br-flow">
                  {row.nodes.map((node) => (
                    <span
                      key={node.id}
                      className={
                        "br-pip" +
                        (node.satisfied ? " done" : "") +
                        (node.is_blocking && !node.satisfied ? " blocking" : "") +
                        (node.is_target ? " target" : "")
                      }
                      title={`${node.label} — ${node.status.replace(/_/g, " ")}`}
                    />
                  ))}
                </span>
                <Chip tone={tone}>
                  {row.decision?.toUpperCase() ?? "—"}
                  {blocked > 0 && ` · ${blocked} in the way`}
                </Chip>
              </button>
            );
          })}
        </div>
      </Card>

      {selected && <PlanBoard board={selected} />}
    </>
  );
}
