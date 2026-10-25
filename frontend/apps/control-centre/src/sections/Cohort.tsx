import { useEffect, useState } from "react";
import { api, live, type Alert, type DeskCandidate, type Metrics } from "@saathi/api-client";
import { ActivityStrip, AlertsPanel, Card } from "@saathi/ui-web";
import { CohortPanel } from "../components/CohortPanel";
import { DeskQueue } from "../desk/DeskQueue";
import { useWorld } from "../world";

/**
 * The whole cohort: who needs a person, what is waiting on the desk, and (in the
 * demo, where ground truth exists) what the planner spared families against the
 * hospital's usual "come back in a week".
 */
export function Cohort({ onOpen }: { onOpen: (patientId: string) => void }) {
  const world = useWorld();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [desk, setDesk] = useState<DeskCandidate[]>([]);
  const real = world.snapshot?.world === "real";

  useEffect(() => {
    api.alerts().then(setAlerts).catch(() => undefined);
    if (!real) api.metrics().then(setMetrics).catch(() => undefined);
    live.deskQueue().then(setDesk).catch(() => undefined);
  }, [world.cohortRevision, real]);

  const counters = world.snapshot?.counters ?? {};

  return (
    <div className="widget-grid">
      <div className="widget-scroll tall">
        {real ? (
          <Card title="Cohort outcome">
            <p className="plain">
              The scorecard compares plans with what really happened, which only the simulated
              world knows. On real records no number is shown rather than a made-up one.
            </p>
          </Card>
        ) : (
          <CohortPanel metrics={metrics} />
        )}
      </div>
      <div className="widget-scroll tall">
        <AlertsPanel alerts={alerts} onSelect={onOpen} />
      </div>
      <div className="widget-scroll">
        <DeskQueue queue={desk} onConfirmed={world.refresh} onSelect={onOpen} />
      </div>
      <Card title="Work done" hint="since the world started">
        <table className="audit-table">
          <tbody>
            {Object.entries(counters).map(([key, n]) => (
              <tr key={key}>
                <td>{key.replace(/[_:]/g, " ")}</td>
                <td className="mono">{n}</td>
              </tr>
            ))}
            <tr>
              <td>families watched live</td>
              <td className="mono">{world.snapshot?.watched.length ?? 0}</td>
            </tr>
            <tr>
              <td>language layer</td>
              <td>{world.snapshot?.language_layer ?? "off"}</td>
            </tr>
          </tbody>
        </table>
      </Card>
      <div className="span-2">
        <ActivityStrip events={world.events} connected={world.connected} onSelect={onOpen} />
      </div>
    </div>
  );
}
