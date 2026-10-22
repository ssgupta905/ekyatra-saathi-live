import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  live,
  LANGUAGE_NAMES,
  type CareStep,
  type InboundMessage,
  type LedgerView,
  type Patient,
  type PlanResponse,
} from "../lib/api";
import type { LiveWorldState } from "../lib/live";
import { stepName } from "../lib/format";
import { CallBrief } from "../components/CallBrief";
import { DecisionHero } from "../components/DecisionHero";
import { DecisionTrace } from "../components/DecisionTrace";
import { VisitChecklist } from "../components/VisitChecklist";
import { MessagePipeline } from "../components/MessagePipeline";
import { InboundCard } from "../components/InboundCard";
import { JourneyStepper } from "../components/JourneyStepper";
import { EvidenceLedger } from "../components/EvidenceLedger";
import { StepAccordion, type Step } from "../components/StepAccordion";
import { CiteContext, Notice } from "../ui/primitives";
import type { Citation } from "../App";

const DONE = new Set(["completed", "result_available"]);

/** Step 2 in one line, from the blockers themselves rather than the planner's log text. */
function whySummary(response: PlanResponse | null): string {
  const plan = response?.plan;
  if (!plan) return "Planning…";
  const names = plan.blocked_by.map((b) => stepName(b.kind).toLowerCase());
  const list = names.length > 2 ? `${names.slice(0, 2).join(", ")} and ${names.length - 2} more` : names.join(" and ");
  if (plan.decision === "go") {
    const extra = plan.bundled_step_ids.length;
    return extra
      ? `Everything it depends on is ready · ${extra + 1} steps in one trip`
      : "Everything it depends on is ready";
  }
  const many = names.length > 1;
  if (plan.decision === "wait") {
    return `Waiting on the ${list} — ${many ? "each has" : "it has"} a reliable ready window`;
  }
  return names.length
    ? `No date yet — the ${list} ${many ? "aren't done and have" : "isn't done and has"} no reliable estimate`
    : "No date yet — a step it depends on has no record";
}

/**
 * One family: the answer first, then the process that produced it as six
 * numbered steps. Each step is one line until it's opened, so a navigator on
 * a call reads the verdict in a second and opens only the step the family is
 * asking about.
 */
export function FamilyDetail({
  patient,
  world,
}: {
  patient: Patient;
  world: LiveWorldState;
}) {
  const [steps, setSteps] = useState<CareStep[]>([]);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [ledger, setLedger] = useState<LedgerView | null>(null);
  const [inbound, setInbound] = useState<InboundMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [cited, setCited] = useState<Citation | null>(null);
  const [changedAt, setChangedAt] = useState(0);
  const lastDecision = useRef<string | null>(null);

  const revision = world.revisionFor(patient.id);
  const { cohortRevision } = world;

  useEffect(() => {
    setOpen(null);
  }, [patient.id]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.steps(patient.id), api.plan(patient.id), live.inbound(patient.id)])
      .then(([stepRows, planResponse, messages]) => {
        if (cancelled) return;
        setSteps(stepRows);
        setPlan(planResponse);
        setInbound(messages);
        setError(null);
        const key = `${patient.id}:${planResponse.plan?.decision ?? null}`;
        if (lastDecision.current?.startsWith(`${patient.id}:`) && lastDecision.current !== key) {
          setChangedAt(Date.now());
        }
        lastDecision.current = key;
        return api.ledger(patient.id);
      })
      .then((view) => {
        if (!cancelled && view) setLedger(view);
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [patient.id, revision, cohortRevision]);

  const focusCitation = useCallback((ledgerId: string) => {
    setOpen("evidence");
    setCited((prev) => ({ id: ledgerId, n: (prev?.n ?? 0) + 1 }));
  }, []);

  const targetKind = useMemo(() => {
    const id = plan?.plan?.target_step_id;
    return id ? (steps.find((s) => s.id === id)?.kind ?? null) : null;
  }, [plan, steps]);

  const decision = plan?.plan?.decision ?? null;
  const done = steps.filter((s) => DONE.has(s.status)).length;
  const next = steps.find((s) => !DONE.has(s.status));
  const blocked = inbound.filter((m) => !m.answerable).length;
  const language = LANGUAGE_NAMES[patient.language];

  const process: Step[] = [
    {
      id: "journey",
      title: "Where they are",
      state: done === steps.length && steps.length > 0 ? "done" : "active",
      summary: steps.length
        ? `${done} of ${steps.length} steps done${next ? ` · next: ${stepName(next.kind)}` : ""}`
        : "Loading…",
      content: <JourneyStepper steps={steps} response={plan} />,
    },
    {
      id: "why",
      title: "Why this decision",
      state: decision === "go" ? "done" : decision === "wait" ? "waiting" : decision ? "blocked" : "neutral",
      summary: whySummary(plan),
      content: <DecisionTrace response={plan} steps={steps} patient={patient} />,
    },
    {
      id: "checklist",
      title: "What to bring",
      state: decision === "go" ? "done" : "neutral",
      summary:
        decision === "go" && plan?.plan
          ? `${plan.plan.what_to_bring.length} things · go first to ${plan.plan.where_to_go_first ?? "reception"}`
          : "Sent with the travel date — there isn't one yet",
      content: <VisitChecklist response={plan} />,
    },
    {
      id: "message",
      title: "Message to the family",
      state: plan?.message_body ? "done" : plan?.routed_to_care_team ? "blocked" : "neutral",
      summary: plan?.message_body
        ? `Written in ${language}, checked by the guard`
        : plan?.routed_to_care_team
          ? "Held by the guard — routed to a person"
          : `${language} · language layer off, the decision stands without it`,
      content: <MessagePipeline response={plan} patient={patient} />,
    },
    {
      id: "family",
      title: "What the family said",
      state: blocked ? "blocked" : inbound.length ? "done" : "neutral",
      summary: inbound.length
        ? `${inbound.length} message${inbound.length === 1 ? "" : "s"}${blocked ? ` · ${blocked} routed to the care team` : ""}`
        : "Nothing yet",
      content: <InboundCard messages={inbound} patient={patient} />,
    },
    {
      id: "evidence",
      title: "Evidence behind it",
      state: ledger ? (ledger.intact ? "done" : "blocked") : "neutral",
      summary: ledger
        ? `${ledger.entries.length} ledger row${ledger.entries.length === 1 ? "" : "s"} · chain ${ledger.intact ? "intact" : "BROKEN"}`
        : "Loading…",
      content: <EvidenceLedger ledger={ledger} focused={cited} />,
    },
  ];

  return (
    <CiteContext.Provider value={focusCitation}>
      <div className="family-detail">
        <div className="family-head">
          <div>
            <h1>{patient.id}</h1>
            <p>
              {patient.home_district} · {Math.round(patient.home_distance_km)} km from the
              hospital · hears {language}
            </p>
          </div>
        </div>

        {error && <Notice tone="stop">{error}</Notice>}

        <DecisionHero
          response={plan}
          patient={patient}
          targetKind={targetKind}
          justChanged={Date.now() - changedAt < 2000}
        />

        <CallBrief patientId={patient.id} revision={revision} />

        <div className="section-label">How Saathi got here</div>
        <StepAccordion steps={process} open={open} onOpen={setOpen} />
      </div>
    </CiteContext.Provider>
  );
}
