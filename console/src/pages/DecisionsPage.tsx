import { useEffect, useState } from "react";
import { api, disruptions, type Alert, type Role } from "../lib/api";
import type { LiveWorldState } from "../lib/live";
import { PageHeader } from "../components/shell/AppShell";
import { SegmentedControl } from "../components/SegmentedControl";
import { PendingApprovalsQueue } from "../components/PendingApprovalsQueue";
import { AlertsPanel } from "../components/AlertsPanel";

type Tab = "approve" | "person";

/**
 * Everything waiting on a human, in two piles: options a disruption produced
 * that someone has to pick between, and families the guard or the engagement
 * monitor handed to a person.
 */
export function DecisionsPage({
  world,
  approverRole,
  approverName,
  onlyRequiringDoctor = false,
  question,
  onOpenFamily,
}: {
  world: LiveWorldState;
  approverRole: Role;
  approverName: string;
  onlyRequiringDoctor?: boolean;
  question: string;
  onOpenFamily: (patientId: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("approve");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    api.alerts().then(setAlerts).catch(() => undefined);
    disruptions
      .pending()
      .then((rows) =>
        setPending((onlyRequiringDoctor ? rows.filter((r) => r.requires_doctor) : rows).length),
      )
      .catch(() => undefined);
  }, [world.cohortRevision, onlyRequiringDoctor]);

  const showAlerts = !onlyRequiringDoctor;

  return (
    <div className="page">
      <PageHeader
        title="Decisions"
        question={question}
        aside={
          showAlerts ? (
            <SegmentedControl
              aria-label="Which pile"
              value={tab}
              onChange={setTab}
              options={[
                { value: "approve", label: `To approve · ${pending}` },
                { value: "person", label: `Needs a person · ${alerts.length}` },
              ]}
            />
          ) : undefined
        }
      />

      <div key={tab} className="panel-fade">
        {tab === "approve" || !showAlerts ? (
          <PendingApprovalsQueue
            approverRole={approverRole}
            approverName={approverName}
            onlyRequiringDoctor={onlyRequiringDoctor}
            revision={world.cohortRevision}
          />
        ) : (
          <AlertsPanel alerts={alerts} onSelect={onOpenFamily} />
        )}
      </div>
    </div>
  );
}
