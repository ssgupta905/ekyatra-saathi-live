import { useState } from "react";
import { ExplainPane, PendingApprovalsQueue } from "@saathi/ui-web";
import { usePersona } from "../session";
import { Drawer } from "../ui/kit";
import { Graph } from "../ui/icons";
import { useWorld } from "../world";
import { BudgetQueue } from "../components/BudgetQueue";
import { ReasoningLog } from "../components/ReasoningLog";
import { RequestQueue } from "../components/RequestQueue";

/**
 * Everything waiting on a person, in the order a day actually works.
 *
 * First what families have *asked for* — a reading of their own words that
 * nothing acts on until somebody agrees with it. Then what they said they can
 * manage. Then the re-plans: pick a family, see its ranked options and what
 * each costs them, approve one. "Why" opens beside it rather than pushing the
 * options off the screen, and now carries the step-by-step working as well as
 * the evidence, because "why the 3rd" and "how did you get to the 3rd" are
 * different questions and a judge asks the second one.
 *
 * A navigator sees what a navigator may approve; a doctor sees what only a
 * doctor may. The server enforces both.
 */
export function Approvals() {
  const { persona } = usePersona();
  const world = useWorld();
  const [family, setFamily] = useState<string | null>(null);
  const [why, setWhy] = useState(false);
  const approver = persona.role === "doctor" ? "doctor" : "navigator";

  return (
    <div className="stack">
      {/* Highest first: a reading nobody has agreed to is blocking a re-plan
          that cannot be computed until it is agreed. Below it, a family who
          answered and was never confirmed has been asked for nothing. */}
      <RequestQueue revision={world.cohortRevision} />
      <BudgetQueue revision={world.cohortRevision} />
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
        {family && (
          <div className="stack">
            <ExplainPane patientId={family} />
            {/* The working, under the evidence. The evidence says what was
                relied on; this says what was done, in order, with what each
                step cost. */}
            <ReasoningLog patientId={family} revision={world.cohortRevision} />
          </div>
        )}
      </Drawer>
    </div>
  );
}
