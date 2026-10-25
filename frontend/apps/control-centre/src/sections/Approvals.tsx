import { useEffect, useState } from "react";
import { disruptions, type Disruption } from "@saathi/api-client";
import { Card, Chip, ExplainPane, PendingApprovalsQueue, fmtDate } from "@saathi/ui-web";
import { usePersona } from "../session";
import { useWorld } from "../world";

const KIND = { machine_down: "machine down", staff_unavailable: "person away", stock_delay: "stock late" };

/**
 * What is broken today, and the re-plans waiting on a person.
 *
 * A navigator approves what does not touch treatment; a doctor sees only what
 * does. The filter is a courtesy. The gate is on the server: an approval that
 * touches treatment from anyone but a doctor is refused there, whatever this
 * screen offered.
 */
export function Approvals() {
  const { persona } = usePersona();
  const world = useWorld();
  const [open, setOpen] = useState<Disruption[]>([]);
  const [family, setFamily] = useState<string | null>(null);

  useEffect(() => {
    disruptions.list().then(setOpen).catch(() => undefined);
  }, [world.cohortRevision]);

  const approver = persona.role === "doctor" ? "doctor" : "navigator";

  return (
    <div className="widget-grid">
      <div className="span-2">
        <Card title="Outages in force" hint={open.length ? `${open.length} open` : "none"} flush={open.length > 0}>
          {open.length === 0 ? (
            <p className="empty">Nothing is down today.</p>
          ) : (
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>What</th>
                  <th>From</th>
                  <th>Until</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {open.map((d) => (
                  <tr key={d.id}>
                    <td className="mono">{d.resource_id}</td>
                    <td>
                      <Chip tone="wait">{KIND[d.kind as keyof typeof KIND] ?? d.kind}</Chip>
                    </td>
                    <td>{fmtDate(d.unavailable_from)}</td>
                    <td>{d.unavailable_to ? fmtDate(d.unavailable_to) : "until further notice"}</td>
                    <td>{d.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div className="span-2">
        <PendingApprovalsQueue
          approverRole={approver}
          approverName={persona.name}
          onlyRequiringDoctor={persona.role === "doctor"}
          revision={world.cohortRevision}
          onSelect={setFamily}
        />
      </div>

      {family && (
        <div className="span-2">
          <ExplainPane patientId={family} />
        </div>
      )}
    </div>
  );
}
