import { useCallback, useEffect, useState } from "react";
import { api, live, type InboundMessage, type Patient, type PlanResponse } from "../lib/api";
import type { Persona } from "../lib/identity";
import type { LiveWorldState } from "../lib/live";
import { DecisionHero } from "../components/DecisionHero";
import { VisitChecklist } from "../components/VisitChecklist";
import { MessagePipeline } from "../components/MessagePipeline";
import { InboundCard } from "../components/InboundCard";
import { StepAccordion, type Step } from "../components/StepAccordion";
import { Notice } from "../ui/primitives";

/**
 * What the family member who handles everything sees: the answer, then four
 * things they might want, each one line until opened. They can ask a
 * question — a clinical one goes to a person, a process one ("what happens to
 * dose 13?") gets answered without touching report content.
 */
export function CaregiverPage({ persona, world }: { persona: Persona; world: LiveWorldState }) {
  const patientId = persona.patientFocus!;
  const [patient, setPatient] = useState<Patient | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [inbound, setInbound] = useState<InboundMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const refresh = useCallback(() => {
    Promise.all([api.patients(), api.plan(patientId), live.inbound(patientId)])
      .then(([patients, planResponse, messages]) => {
        setPatient(patients.find((p) => p.id === patientId) ?? null);
        setPlan(planResponse);
        setInbound(messages);
      })
      .catch(() => undefined);
  }, [patientId]);

  useEffect(refresh, [refresh, world.revisionFor(patientId)]);

  const ask = async () => {
    if (!question.trim()) return;
    await live.inject(patientId, undefined, question);
    setSent(question);
    setQuestion("");
    setOpen("sent");
    window.setTimeout(refresh, 400);
  };

  if (!patient || !plan) return <div className="page narrow"><Notice tone="calm">Loading…</Notice></div>;

  const go = plan.plan?.decision === "go";
  const steps: Step[] = [
    {
      id: "bring",
      title: "What to bring",
      state: go ? "done" : "neutral",
      summary: go ? `${plan.plan!.what_to_bring.length} things` : "Comes with your travel date",
      content: <VisitChecklist response={plan} />,
    },
    {
      id: "message",
      title: "Message from Saathi",
      state: plan.message_body ? "done" : "neutral",
      summary: plan.message_body ? "In your language" : "No message yet",
      content: <MessagePipeline response={plan} patient={patient} />,
    },
    {
      id: "ask",
      title: "Ask a question",
      state: "neutral",
      summary: "About dates, places or documents",
      content: (
        <div className="ask">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder='e.g. "what happens to dose 13?"'
          />
          <button type="button" className="btn primary" onClick={ask} disabled={!question.trim()}>
            Send
          </button>
          {sent && <p className="hint">Sent: “{sent}”</p>}
        </div>
      ),
    },
    {
      id: "sent",
      title: "What you've sent",
      state: inbound.length ? "done" : "neutral",
      summary: inbound.length ? `${inbound.length} message${inbound.length === 1 ? "" : "s"}` : "Nothing yet",
      content: <InboundCard messages={inbound} patient={patient} />,
    },
  ];

  return (
    <div className="page narrow">
      <div className="greeting">
        <span>{persona.name}</span> · for {patient.id}
      </div>
      <DecisionHero response={plan} patient={patient} targetKind={null} />
      <StepAccordion steps={steps} open={open} onOpen={setOpen} />
    </div>
  );
}
