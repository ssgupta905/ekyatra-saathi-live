import { useState } from "react";
import { ExplainPane, PendingApprovalsQueue } from "@saathi/ui-web";
import { usePersona } from "../session";
import { Drawer } from "../ui/kit";
import { Graph } from "../ui/icons";
import { useWorld } from "../world";

/**
 * The re-plans waiting on a person. Pick a family, see its ranked options and what
 * each costs the family, approve one. "Why" opens beside it rather than pushing
 * the options off the screen. A navigator sees what a navigator may approve; a
 * doctor sees what only a doctor may. The server enforces both.
 */
export function Approvals() {
  const { persona } = usePersona();
  const world = useWorld();
  const [family, setFamily] = useState<string | null>(null);
  const [why, setWhy] = useState(false);
  const approver = persona.role === "doctor" ? "doctor" : "navigator";

  return (
    <div className="stack">
      {family && (
        <div className="approvals-bar">
          <span>
            Looking at <strong>{family}</strong>
          </span>
          <button type="button" className="btn" onClick={() => setWhy(true)}>
            <Graph size={15} /> Why this family's plan is what it is
          </button>
        </div>
      )}
      <PendingApprovalsQueue
        approverRole={approver}
        approverName={persona.name}
        onlyRequiringDoctor={persona.role === "doctor"}
        revision={world.cohortRevision}
        onSelect={setFamily}
      />
      <Drawer open={why && family !== null} title={`Why · ${family ?? ""}`} onClose={() => setWhy(false)} width={600}>
        {family && <ExplainPane patientId={family} />}
      </Drawer>
    </div>
  );
}
