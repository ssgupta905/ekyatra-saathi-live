import { useCallback, useEffect, useState } from "react";
import { live, type DeskCandidate } from "@saathi/api-client";
import { Notice } from "@saathi/ui-web";
import { AddStep } from "../desk/AddStep";
import { DeskQueue } from "../desk/DeskQueue";
import { ImportRecords } from "../desk/ImportRecords";
import { IssueReporter } from "../desk/IssueReporter";
import { PendingReports } from "../desk/PendingReports";
import { RegisterFamily } from "../desk/RegisterFamily";
import { useWorld } from "../world";

/**
 * The desk's work: say what went wrong, confirm what was released, and (on real
 * records) put families and their steps on record. Every one of these is an input,
 * never a decision: what follows happens because the planner reacted.
 */
export function Desk() {
  const world = useWorld();
  const [queue, setQueue] = useState<DeskCandidate[]>([]);
  const [affected, setAffected] = useState<string[] | null>(null);
  const [entered, setEntered] = useState(0);
  const real = world.snapshot?.world === "real";
  const changed = () => setEntered((n) => n + 1);

  const refresh = useCallback(() => {
    live.deskQueue().then(setQueue).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh, world.cohortRevision]);

  return (
    <div className="widget-grid">
      <div className="span-2">
        <IssueReporter
          onReported={(ids) => {
            setAffected(ids);
            refresh();
          }}
        />
        {affected && (
          <Notice tone="calm">
            {affected.length} famil{affected.length === 1 ? "y" : "ies"} picked up by the planner.
            Holding messages went out before any new date was worked out.
          </Notice>
        )}
      </div>

      {real ? (
        <>
          <div className="span-2">
            <PendingReports revision={entered + world.cohortRevision} onReleased={changed} />
          </div>
          <RegisterFamily onRegistered={changed} />
          <AddStep revision={entered} onAdded={changed} />
          <div className="span-2">
            <ImportRecords onImported={changed} />
          </div>
        </>
      ) : (
        <div className="span-2">
          <DeskQueue queue={queue} onConfirmed={refresh} />
        </div>
      )}
    </div>
  );
}
