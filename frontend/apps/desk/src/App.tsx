import { useCallback, useEffect, useState } from "react";
import { live, useLiveWorld, type DeskCandidate } from "@saathi/api-client";
import { ActivityStrip, AgentStatus, AppShell, Chip, Notice } from "@saathi/ui-web";
import { DeskQueue } from "./DeskQueue";
import { IssueReporter } from "./IssueReporter";
import { IDENTITY } from "./identity";

/**
 * The desk's screen. Two jobs, and nothing else.
 *
 * *Say what went wrong*, in the words the ward already writes it in, and *confirm
 * what was released*. Both are inputs, not decisions: reporting an outage starts
 * the planner, confirming a report lets the family's plan move. Everything that
 * follows happens because the system reacted, not because this page said so.
 *
 * Who needs a call, and which option to choose, are the navigator's and the
 * doctor's. A desk that could approve a re-plan would be a desk deciding whether
 * a family travels.
 */
export default function App() {
  const world = useLiveWorld();
  const [queue, setQueue] = useState<DeskCandidate[]>([]);
  const [affected, setAffected] = useState<string[] | null>(null);

  const refresh = useCallback(() => {
    live.deskQueue().then(setQueue).catch(() => undefined);
  }, []);

  useEffect(refresh, [refresh, world.cohortRevision]);

  return (
    <AppShell
      app="Desk"
      identity={IDENTITY}
      snapshot={world.snapshot}
      connected={world.connected}
      status={queue.length > 0 && <Chip tone="wait">{queue.length} to confirm</Chip>}
    >
      <AgentStatus working={world.working} events={world.events} />

      <div className="hx-panes single">
        <main className="hx-work">
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

          <DeskQueue queue={queue} onConfirmed={refresh} />

          <ActivityStrip events={world.events} connected={world.connected} />
        </main>
      </div>
    </AppShell>
  );
}
