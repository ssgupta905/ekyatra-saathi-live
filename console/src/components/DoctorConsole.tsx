import type { Persona } from "../lib/identity";
import { PendingApprovalsQueue } from "./PendingApprovalsQueue";
import { Card } from "../ui/primitives";

/**
 * A doctor approves anything that touches treatment or dose timing — the
 * brief's structural split from a navigator's approval. The filter here is
 * a convenience; the actual gate is enforced server-side regardless of it.
 */
export function DoctorConsole({ persona }: { persona: Persona }) {
  return (
    <div className="stage">
      <Card title={persona.title} hint={persona.name}>
        <p className="plain">
          Options that touch treatment or a dose date wait for you here. A navigator
          cannot approve these — Saathi rejects it structurally, the same way the
          model is never allowed to decide whether a family travels.
        </p>
      </Card>
      <PendingApprovalsQueue approverRole="doctor" approverName={persona.name} onlyRequiringDoctor />
    </div>
  );
}
