import { useCallback, useEffect, useState } from "react";
import { live, type DeskCandidate } from "../lib/api";
import type { Persona } from "../lib/identity";
import { DeskQueue } from "./DeskQueue";
import { DisruptionReportForm } from "./DisruptionReportForm";
import { Card, Notice } from "../ui/primitives";

/**
 * A desk's two jobs, per the brief: one-tap status updates (confirming a
 * record the lab finished), and reporting when something they run goes down.
 * Both are *inputs* — nothing here decides a plan, a date, or an approval.
 */
export function DeskConsole({ persona }: { persona: Persona }) {
  const [queue, setQueue] = useState<DeskCandidate[]>([]);
  const [lastAffected, setLastAffected] = useState<string[] | null>(null);

  const refresh = useCallback(() => {
    live.deskQueue().then(setQueue).catch(() => undefined);
  }, []);

  useEffect(refresh, [refresh]);

  return (
    <div className="stage">
      <Card title={persona.title} hint={persona.name}>
        <p className="plain">
          Confirm records below, or report a resource you run as unavailable.
        </p>
      </Card>

      <div className="widget-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <DisruptionReportForm
            defaultResourceId={persona.deskResourceId}
            onReported={(affected) => {
              setLastAffected(affected);
              refresh();
            }}
          />
          {lastAffected && (
            <Notice tone="calm">
              {lastAffected.length} famil{lastAffected.length === 1 ? "y" : "ies"} affected:{" "}
              {lastAffected.join(", ") || "none"}
            </Notice>
          )}
        </div>

        <div className="widget-scroll">
          <DeskQueue queue={queue} onConfirmed={refresh} />
        </div>
      </div>
    </div>
  );
}
