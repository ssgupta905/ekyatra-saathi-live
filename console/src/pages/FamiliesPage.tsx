import { useEffect, useState } from "react";
import { api, type Alert, type Patient } from "../lib/api";
import type { LiveWorldState } from "../lib/live";
import { CallList } from "../components/CallList";
import { FamilyDetail } from "./FamilyDetail";
import { Notice } from "../ui/primitives";

/**
 * Pick a family on the left, read it on the right. Two panes and nothing
 * else — the list is the only navigation this page needs.
 */
export function FamiliesPage({
  patients,
  world,
  focusId,
}: {
  patients: Patient[];
  world: LiveWorldState;
  /** A family another page asked us to open, e.g. from a tile on Today. */
  focusId: string | null;
}) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(focusId);

  useEffect(() => {
    if (focusId) setSelectedId(focusId);
  }, [focusId]);

  useEffect(() => {
    api.alerts().then(setAlerts).catch(() => undefined);
  }, [world.cohortRevision]);

  const watched = world.snapshot?.watched ?? [];
  const selected =
    patients.find((p) => p.id === selectedId) ??
    patients.find((p) => p.id === watched[0]) ??
    patients[0] ??
    null;

  return (
    <div className="families">
      <CallList
        patients={patients}
        alerts={alerts}
        watched={watched}
        selectedId={selected?.id ?? null}
        onSelect={(p) => setSelectedId(p.id)}
      />
      <div className="families-detail">
        {selected ? (
          <div key={selected.id} className="panel-fade">
            <FamilyDetail patient={selected} world={world} />
          </div>
        ) : (
          <Notice tone="calm">Loading families…</Notice>
        )}
      </div>
    </div>
  );
}
