import { useCallback, useEffect, useState } from "react";
import { api, type CareStep, type LedgerView, type Patient, type PlanResponse } from "../lib/api";
import type { Citation } from "../lib/citation";
import { DecisionTrace } from "../components/DecisionTrace";
import { EvidenceLedger } from "../components/EvidenceLedger";
import { CiteContext, Notice } from "../ui/primitives";

/**
 * Why this family got this answer, all the way down to the sources.
 *
 * The three-pane worklist answers *who needs me*; this answers *why*, and it
 * is the half of the console a navigator needs when a family argues with the
 * decision or when a supervisor asks how it was reached. The chain is: the
 * decision, the claims that produced it, and the ledger rows those claims came
 * from — clicking a citation lands on its row.
 *
 * Opening this page does not plan, re-render, or write anything. Invariant 5:
 * the ledger grows only when a fact changes, and reading is not a change.
 */
export function ExplainPane({ patientId }: { patientId: string }) {
  const [patient, setPatient] = useState<Patient | null>(null);
  const [steps, setSteps] = useState<CareStep[]>([]);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [ledger, setLedger] = useState<LedgerView | null>(null);
  const [cited, setCited] = useState<Citation | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCited(null);
    Promise.all([
      api.patients(),
      api.steps(patientId),
      api.plan(patientId),
      api.ledger(patientId),
    ])
      .then(([patients, stepRows, planResponse, ledgerView]) => {
        if (cancelled) return;
        setPatient(patients.find((p) => p.id === patientId) ?? null);
        setSteps(stepRows);
        setPlan(planResponse);
        setLedger(ledgerView);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  // A click counter, so clicking the same citation twice replays the jump
  // instead of doing nothing.
  const cite = useCallback(
    (ledgerId: string) =>
      setCited((previous) => ({ id: ledgerId, n: (previous?.n ?? 0) + 1 })),
    [],
  );

  if (!patient) return <Notice tone="calm">Loading {patientId}…</Notice>;

  return (
    <CiteContext.Provider value={cite}>
      <DecisionTrace response={plan} steps={steps} patient={patient} />
      <EvidenceLedger ledger={ledger} focused={cited} />
    </CiteContext.Provider>
  );
}
