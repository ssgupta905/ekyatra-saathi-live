import { useState } from "react";
import { useLiveWorld } from "@saathi/api-client";
import { AgentStatus, AppShell, Card, ExplainPane, PendingApprovalsQueue } from "@saathi/ui-web";
import { useIdentity } from "@saathi/auth";
import { IDENTITY as PERSONA } from "./identity";

/**
 * The doctor's screen: the decisions only a doctor may make.
 *
 * A re-plan that touches treatment or a dose date waits here. A navigator cannot
 * approve it — Saathi rejects that structurally, the same way the model is never
 * allowed to decide whether a family travels. The filter on this list is a
 * convenience; the actual gate is enforced on the server whatever this screen shows.
 *
 * Beside the options, *why*: every claim behind the family's current answer and
 * the source of each, so a doctor is approving with the reasoning in front of them.
 */
export default function App() {
  const IDENTITY = useIdentity(PERSONA);
  const world = useLiveWorld();
  const [family, setFamily] = useState<string | null>(null);

  return (
    <AppShell
      app="Doctor"
      identity={IDENTITY}
      snapshot={world.snapshot}
      connected={world.connected}
    >
      <AgentStatus working={world.working} events={world.events} />

      <div className="hx-panes single">
        <main className="hx-work">
          <Card title={IDENTITY.title} hint={IDENTITY.name}>
            <p className="plain">
              Options that touch treatment or a dose date wait for you here. Pick a family to
              see them ranked, with what each one costs the family in nights, trips and delay.
            </p>
          </Card>

          <PendingApprovalsQueue
            approverRole={IDENTITY.role}
            approverName={IDENTITY.name}
            onlyRequiringDoctor
            revision={world.cohortRevision}
            onSelect={setFamily}
          />

          {family && <ExplainPane patientId={family} />}
        </main>
      </div>
    </AppShell>
  );
}
