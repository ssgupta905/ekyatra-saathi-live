import { useCallback, useEffect, useState } from "react";
import { live, type DeskCandidate } from "@saathi/api-client";
import { DeskQueue } from "../desk/DeskQueue";
import { PendingReports } from "../desk/PendingReports";
import { useToast } from "../ui/kit";
import { useWorld } from "../world";

/**
 * Reports finishing in the lab are not the hospital knowing about them. In the
 * demo the lab's note waits here to be confirmed; on real records a person marks
 * the report released. Either way the family's plan moves the moment it's done.
 */
export function Releases() {
  const world = useWorld();
  const toast = useToast();
  const real = world.snapshot?.world === "real";
  const [queue, setQueue] = useState<DeskCandidate[]>([]);
  const [n, setN] = useState(0);

  const refresh = useCallback(() => {
    live.deskQueue().then(setQueue).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh, world.cohortRevision]);

  return real ? (
    <PendingReports
      revision={n + world.cohortRevision}
      onReleased={() => {
        setN((x) => x + 1);
        toast("Recorded as released. The family has been re-planned.");
      }}
    />
  ) : (
    <DeskQueue
      queue={queue}
      onConfirmed={() => {
        refresh();
        toast("Confirmed. The family has been re-planned.");
      }}
    />
  );
}
