import { useEffect, useState } from "react";
import { disruptions, type Disruption } from "@saathi/api-client";
import { fmtDate } from "@saathi/ui-web";
import { IssueReporter } from "../desk/IssueReporter";
import { EmptyState, Panel, Pill, SkeletonRows, useToast } from "../ui/kit";
import { Alert } from "../ui/icons";
import { useWorld } from "../world";

const KIND: Record<string, string> = { machine_down: "machine down", staff_unavailable: "person away", stock_delay: "stock late" };

/** Say what went wrong; see what is still down. One job, one screen. */
export function Issues() {
  const world = useWorld();
  const toast = useToast();
  const [open, setOpen] = useState<Disruption[] | null>(null);

  useEffect(() => {
    disruptions.list().then(setOpen).catch(() => setOpen([]));
  }, [world.cohortRevision]);

  return (
    <div className="stack">
      <IssueReporter
        onReported={(ids) => {
          toast(`Reported. ${ids.length} famil${ids.length === 1 ? "y was" : "ies were"} told not to travel yet.`);
          disruptions.list().then(setOpen).catch(() => undefined);
        }}
      />
      <Panel title="Still down" hint="Outages in force today" flush>
        {open === null ? (
          <div className="pad"><SkeletonRows /></div>
        ) : open.length === 0 ? (
          <EmptyState title="Nothing is down" icon={<Alert />} />
        ) : (
          <table className="audit-table">
            <thead>
              <tr><th>Resource</th><th>What</th><th>From</th><th>Until</th><th>Note</th></tr>
            </thead>
            <tbody>
              {open.map((d) => (
                <tr key={d.id}>
                  <td className="mono">{d.resource_id}</td>
                  <td><Pill tone="wait">{KIND[d.kind] ?? d.kind}</Pill></td>
                  <td>{fmtDate(d.unavailable_from)}</td>
                  <td>{d.unavailable_to ? fmtDate(d.unavailable_to) : "until further notice"}</td>
                  <td>{d.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
