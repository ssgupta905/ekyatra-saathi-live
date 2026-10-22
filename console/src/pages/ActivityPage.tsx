import { useCallback, useEffect, useState } from "react";
import { live, type DeskCandidate, type Patient } from "../lib/api";
import type { LiveWorldState } from "../lib/live";
import { PageHeader } from "../components/shell/AppShell";
import { SegmentedControl } from "../components/SegmentedControl";
import { ActivityStrip } from "../components/ActivityStrip";
import { DeskQueue } from "../components/DeskQueue";
import { OperatorControls } from "../components/OperatorControls";

type Tab = "feed" | "desk" | "controls";

/**
 * What the system has just done, and the two inputs that make it do anything:
 * the desk confirming a record, and the clock moving.
 */
export function ActivityPage({
  world,
  patients,
  onOpenFamily,
}: {
  world: LiveWorldState;
  patients: Patient[];
  onOpenFamily: (patientId: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("feed");
  const [desk, setDesk] = useState<DeskCandidate[]>([]);

  const refreshDesk = useCallback(() => {
    live.deskQueue().then(setDesk).catch(() => undefined);
  }, []);

  useEffect(refreshDesk, [refreshDesk, world.cohortRevision]);

  return (
    <div className="page">
      <PageHeader
        title="Activity"
        question="What has the system just done?"
        aside={
          <SegmentedControl
            aria-label="Activity view"
            value={tab}
            onChange={setTab}
            options={[
              { value: "feed", label: "Live feed" },
              { value: "desk", label: `At the desk · ${desk.length}` },
              { value: "controls", label: "World controls" },
            ]}
          />
        }
      />

      <div key={tab} className="panel-fade">
        {tab === "feed" && (
          <ActivityStrip events={world.events} connected={world.connected} onSelect={onOpenFamily} />
        )}
        {tab === "desk" && (
          <DeskQueue
            queue={desk}
            onConfirmed={() => {
              refreshDesk();
              world.refresh();
            }}
            onSelect={onOpenFamily}
          />
        )}
        {tab === "controls" && (
          <OperatorControls snapshot={world.snapshot} patients={patients} onChange={world.refresh} />
        )}
      </div>
    </div>
  );
}
