import { useEffect, useState } from "react";
import { api, type Patient, type PlanResponse } from "../lib/api";
import { DECISION_PLAIN } from "../lib/explain";
import { fmtDate } from "../lib/format";
import { DecisionGlyph, Notice } from "../ui/primitives";

/**
 * "Simple mode": a feature phone has a voice and a keypad, nothing else. This
 * screen stands in for that — one sentence, one word, no navigation, no
 * chrome. Everything else in this console is the extra the brief says
 * WhatsApp and the web view are: useful, but not load-bearing.
 */
export function PatientSimpleView({ patientId }: { patientId: string }) {
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.plan(patientId), api.patients()])
      .then(([planResponse, patients]) => {
        if (cancelled) return;
        setPlan(planResponse);
        setPatient(patients.find((p) => p.id === patientId) ?? null);
      })
      .catch(() => undefined);
    const id = window.setInterval(() => {
      api.plan(patientId).then(setPlan).catch(() => undefined);
    }, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [patientId]);

  if (!plan?.plan) {
    return (
      <div className="simple-mode">
        <Notice tone="calm">Getting your plan…</Notice>
      </div>
    );
  }

  const { decision, travel_on } = plan.plan;

  return (
    <div className="simple-mode">
      <div className={`simple-verdict ${decision}`}>
        <DecisionGlyph decision={decision} size={64} />
        <span className="simple-word">
          {decision === "go" ? "Come" : decision === "wait" ? "Wait" : "Not yet"}
        </span>
      </div>
      <p className="simple-sentence">{DECISION_PLAIN[decision]}</p>
      {decision === "go" && travel_on && (
        <p className="simple-date">{fmtDate(travel_on)}</p>
      )}
      {patient && <p className="simple-caption">{patient.home_district}</p>}
    </div>
  );
}
