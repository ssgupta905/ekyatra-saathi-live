import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  live,
  type Alert,
  type CareStep,
  type DeskCandidate,
  type InboundMessage,
  type LedgerView,
  type Metrics,
  type Patient,
  type PlanResponse,
} from "../lib/api";
import type { LiveWorldState } from "../lib/live";
import { setSimToday } from "../lib/format";
import type { Persona } from "../lib/identity";
import { CallList } from "./CallList";
import { ActivityStrip } from "./ActivityStrip";
import { CallBrief } from "./CallBrief";
import { DecisionHero } from "./DecisionHero";
import { DecisionTrace } from "./DecisionTrace";
import { VisitChecklist } from "./VisitChecklist";
import { MessagePipeline } from "./MessagePipeline";
import { InboundCard } from "./InboundCard";
import { JourneyStepper } from "./JourneyStepper";
import { EvidenceLedger } from "./EvidenceLedger";
import { DeskQueue } from "./DeskQueue";
import { CohortPanel } from "./CohortPanel";
import { AlertsPanel } from "./AlertsPanel";
import { OperatorControls } from "./OperatorControls";
import { PendingApprovalsQueue } from "./PendingApprovalsQueue";
import { PlanBoardList } from "./PlanBoardList";
import { SegmentedControl } from "./SegmentedControl";
import { CiteContext, Notice } from "../ui/primitives";
import type { Citation } from "../App";

type View = "journey" | "boards" | "cohort" | "disruptions";
const VIEW_OPTIONS = [
  { value: "journey" as const, label: "One family" },
  // The board view answers the question a list cannot: what is waiting on what.
  { value: "boards" as const, label: "Plan boards" },
  { value: "cohort" as const, label: "Cohort" },
  { value: "disruptions" as const, label: "Disruptions" },
];

type DetailTab = "why" | "checklist" | "message" | "family" | "timeline" | "ledger";
const DETAIL_TABS = [
  { value: "why" as const, label: "Why" },
  { value: "checklist" as const, label: "Checklist" },
  { value: "message" as const, label: "Message" },
  { value: "family" as const, label: "Family" },
  { value: "timeline" as const, label: "Timeline" },
  { value: "ledger" as const, label: "Ledger" },
];

/**
 * The navigator's console: one family at a time, the whole cohort, or the
 * call list of families currently waiting on a decision. This is the
 * console the original prototype shipped with — other personas each get a
 * narrower screen built for what the brief says that role actually does.
 */
export function NavigatorConsole({
  persona,
  world,
  patients,
  error,
  setError,
}: {
  persona: Persona;
  world: LiveWorldState;
  patients: Patient[];
  error: string | null;
  setError: (e: string | null) => void;
}) {
  const [selected, setSelected] = useState<Patient | null>(null);
  const [steps, setSteps] = useState<CareStep[]>([]);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [ledger, setLedger] = useState<LedgerView | null>(null);
  const [inbound, setInbound] = useState<InboundMessage[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [desk, setDesk] = useState<DeskCandidate[]>([]);
  const [view, setView] = useState<View>("journey");
  const [detailTab, setDetailTab] = useState<DetailTab>("why");
  const [cited, setCited] = useState<Citation | null>(null);
  const [changedAt, setChangedAt] = useState<number>(0);

  const { cohortRevision } = world;
  setSimToday(world.snapshot?.current ?? null);
  const patientRevision = world.revisionFor(selected?.id ?? null);
  const lastDecision = useRef<string | null>(null);

  useEffect(() => {
    setSelected((current) => current ?? patients[0] ?? null);
  }, [patients]);

  useEffect(() => {
    api.alerts().then(setAlerts).catch(() => undefined);
    api.metrics().then(setMetrics).catch(() => undefined);
    live.deskQueue().then(setDesk).catch(() => undefined);
  }, [cohortRevision]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    const patientId = selected.id;

    Promise.all([api.steps(patientId), api.plan(patientId), live.inbound(patientId)])
      .then(([stepRows, planResponse, messages]) => {
        if (cancelled) return;
        setSteps(stepRows);
        setPlan(planResponse);
        setInbound(messages);

        const decision = planResponse.plan?.decision ?? null;
        const key = `${patientId}:${decision}`;
        if (lastDecision.current?.startsWith(`${patientId}:`) && lastDecision.current !== key) {
          setChangedAt(Date.now());
        }
        lastDecision.current = key;
        return api.ledger(patientId);
      })
      .then((view) => {
        if (!cancelled && view) setLedger(view);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });

    return () => {
      cancelled = true;
    };
  }, [selected, patientRevision, cohortRevision, setError]);

  const focusCitation = useCallback((ledgerId: string) => {
    setView("journey");
    setDetailTab("ledger");
    setCited((prev) => ({ id: ledgerId, n: (prev?.n ?? 0) + 1 }));
  }, []);

  const selectPatient = useCallback((patient: Patient) => {
    setSelected(patient);
    setDetailTab("why");
  }, []);

  const openForPatient = useCallback(
    (patientId: string) => {
      const match = patients.find((row) => row.id === patientId);
      if (match) {
        selectPatient(match);
        setView("journey");
      }
    },
    [patients, selectPatient],
  );

  const refreshCohort = useCallback(() => {
    world.refresh();
    live.deskQueue().then(setDesk).catch(() => undefined);
    api.alerts().then(setAlerts).catch(() => undefined);
  }, [world]);

  const targetKind = useMemo(() => {
    const id = plan?.plan?.target_step_id;
    return id ? (steps.find((s) => s.id === id)?.kind ?? null) : null;
  }, [plan, steps]);

  const watched = world.snapshot?.watched ?? [];
  const justChanged = Date.now() - changedAt < 2000;

  return (
    <CiteContext.Provider value={focusCitation}>
      <div className="view-tabs">
        <SegmentedControl
          options={VIEW_OPTIONS}
          value={view}
          onChange={setView}
          aria-label="View"
        />
      </div>

      <div className="layout">
        <CallList
          patients={patients}
          alerts={alerts}
          watched={watched}
          selectedId={selected?.id ?? null}
          onSelect={selectPatient}
        />

        <main className="stage">
          {error && (
            <Notice tone="stop">
              <strong>The console cannot reach the planner.</strong> {error} — start the API
              with <span className="mono">make api</span>.
            </Notice>
          )}

          <ActivityStrip events={world.events} connected={world.connected} onSelect={openForPatient} />

          {view === "journey" ? (
            selected ? (
              <>
                <CallBrief patientId={selected.id} revision={patientRevision} />
                <DecisionHero
                  response={plan}
                  patient={selected}
                  targetKind={targetKind}
                  justChanged={justChanged}
                />
                <SegmentedControl
                  options={DETAIL_TABS}
                  value={detailTab}
                  onChange={setDetailTab}
                  aria-label="Detail"
                />
                <div key={detailTab} className="panel-fade">
                  {detailTab === "why" && (
                    <DecisionTrace response={plan} steps={steps} patient={selected} />
                  )}
                  {detailTab === "checklist" && <VisitChecklist response={plan} />}
                  {detailTab === "message" && (
                    <MessagePipeline response={plan} patient={selected} />
                  )}
                  {detailTab === "family" && (
                    <InboundCard messages={inbound} patient={selected} />
                  )}
                  {detailTab === "timeline" && (
                    <JourneyStepper steps={steps} response={plan} />
                  )}
                  {detailTab === "ledger" && (
                    <EvidenceLedger ledger={ledger} focused={cited} />
                  )}
                </div>
              </>
            ) : (
              !error && <Notice tone="calm">Loading families…</Notice>
            )
          ) : view === "boards" ? (
            <PlanBoardList revision={world.cohortRevision} />
          ) : view === "cohort" ? (
            <div className="widget-grid">
              <div className="span-2">
                <OperatorControls
                  snapshot={world.snapshot}
                  patients={patients}
                  onChange={refreshCohort}
                />
              </div>
              <div className="widget-scroll">
                <DeskQueue queue={desk} onConfirmed={refreshCohort} onSelect={openForPatient} />
              </div>
              <div className="widget-grid-col">
                <CohortPanel metrics={metrics} />
                <div className="widget-scroll short">
                  <AlertsPanel alerts={alerts} onSelect={openForPatient} />
                </div>
              </div>
            </div>
          ) : (
            <PendingApprovalsQueue
              approverRole="navigator"
              approverName={persona.name}
              revision={cohortRevision}
            />
          )}
        </main>
      </div>
    </CiteContext.Provider>
  );
}
