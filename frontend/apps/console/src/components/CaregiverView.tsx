import { useEffect, useState } from "react";
import { api, live, type InboundMessage, type Patient, type PlanResponse } from "@saathi/api-client";
import type { Persona } from "../lib/identity";
import { DecisionHero } from "./DecisionHero";
import { MessagePipeline } from "./MessagePipeline";
import { InboundCard } from "./InboundCard";
import { Card, Notice } from "@saathi/ui-web";

/**
 * The caregiver's screen: WhatsApp for the family member who handles
 * everything. They can ask a question — a clinical one is routed to a
 * person, a process one ("what happens to dose 13?") gets answered without
 * ever touching report content.
 */
export function CaregiverView({ persona }: { persona: Persona }) {
  const patientId = persona.patientFocus!;
  const [patient, setPatient] = useState<Patient | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [inbound, setInbound] = useState<InboundMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [sent, setSent] = useState<string | null>(null);

  const refresh = () => {
    Promise.all([api.patients(), api.plan(patientId), live.inbound(patientId)]).then(
      ([patients, planResponse, messages]) => {
        setPatient(patients.find((p) => p.id === patientId) ?? null);
        setPlan(planResponse);
        setInbound(messages);
      },
    ).catch(() => undefined);
  };

  useEffect(refresh, [patientId]);

  const ask = async () => {
    if (!question.trim()) return;
    await live.inject(patientId, undefined, question);
    setSent(question);
    setQuestion("");
    window.setTimeout(refresh, 400);
  };

  if (!patient || !plan) {
    return <Notice tone="calm">Loading…</Notice>;
  }

  return (
    <div className="stage">
      <div className="screen-kicker">
        {persona.title} · <span className="hint">{persona.name}</span>
      </div>
      <DecisionHero response={plan} patient={patient} targetKind={null} />

      <MessagePipeline response={plan} patient={patient} />

      <div className="widget-grid">
        <Card title="Ask Saathi" hint='e.g. "what happens to dose 13?"'>
          <div className="disruption-form">
            <label className="grow">
              Your question
              <input value={question} onChange={(e) => setQuestion(e.target.value)} />
            </label>
            <button type="button" onClick={ask}>
              Send
            </button>
          </div>
          {sent && <Notice tone="calm">Sent: “{sent}”</Notice>}
        </Card>

        <div className="widget-scroll short">
          <InboundCard messages={inbound} patient={patient} />
        </div>
      </div>
    </div>
  );
}
