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
} from "./lib/api";
import { useLiveWorld } from "./lib/live";
import { setSimToday } from "./lib/format";
import { CallList } from "./components/CallList";
import { ClockBar } from "./components/ClockBar";
import { ActivityStrip } from "./components/ActivityStrip";
import { CallBrief } from "./components/CallBrief";
import { DecisionHero } from "./components/DecisionHero";
import { DecisionTrace } from "./components/DecisionTrace";
import { VisitChecklist } from "./components/VisitChecklist";
import { MessagePipeline } from "./components/MessagePipeline";
import { InboundCard } from "./components/InboundCard";
import { JourneyStepper } from "./components/JourneyStepper";
import { EvidenceLedger } from "./components/EvidenceLedger";
import { DeskQueue } from "./components/DeskQueue";
import { CohortPanel } from "./components/CohortPanel";
import { AlertsPanel } from "./components/AlertsPanel";
import { OperatorControls } from "./components/OperatorControls";
import { CiteContext, Notice } from "./ui/primitives";
import { Shield } from "./ui/icons";

type View = "journey" | "cohort";

/** The ledger row a citation points at. `n` counts clicks, so clicking the
 *  same citation twice replays the flash instead of doing nothing. */
export interface Citation {
  id: string;
  n: number;
}

export default function App() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selected, setSelected] = useState<Patient | null>(null);
  const [steps, setSteps] = useState<CareStep[]>([]);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [ledger, setLedger] = useState<LedgerView | null>(null);
  const [inbound, setInbound] = useState<InboundMessage[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [desk, setDesk] = useState<DeskCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("journey");
  const [cited, setCited] = useState<Citation | null>(null);
  const [changedAt, setChangedAt] = useState<number>(0);

  const world = useLiveWorld();
  const { cohortRevision } = world;

  // Every date on the page is read against the simulated day, not the operator's
  // wall clock: a travel date two simulated days out must say "in 2 days".
  setSimToday(world.snapshot?.current ?? null);
  const patientRevision = world.revisionFor(selected?.id ?? null);
  const lastDecision = useRef<string | null>(null);

  useEffect(() => {
    api
      .patients()
      .then((rows) => {
        setPatients(rows);
        setSelected((current) => current ?? rows[0] ?? null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // Cohort-wide state follows the world rather than a poll: the backend says
  // what changed, and only then does anything refetch.
  useEffect(() => {
    api.alerts().then(setAlerts).catch(() => undefined);
    api.metrics().then(setMetrics).catch(() => undefined);
    live.deskQueue().then(setDesk).catch(() => undefined);
  }, [cohortRevision]);

  // One family's page. Refetched when an event names that family *and* on every
  // tick of the clock: the runner re-plans everyone every simulated day, so a
  // page that only reloaded on a decision change would keep showing a travel
  // date and a "recomputed" stamp from several simulated days ago.
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
        // Flag a genuine change of answer for this family, not the first load
        // and not a change of selection.
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
  }, [selected, patientRevision, cohortRevision]);

  /** A citation anywhere on the page focuses its ledger row. */
  const focusCitation = useCallback((ledgerId: string) => {
    setView("journey");
    setCited((prev) => ({ id: ledgerId, n: (prev?.n ?? 0) + 1 }));
  }, []);

  const openForPatient = useCallback(
    (patientId: string) => {
      const match = patients.find((row) => row.id === patientId);
      if (match) {
        setSelected(match);
        setView("journey");
      }
    },
    [patients],
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
      <header className="chrome">
        <div className="wordmark">
          <span className="name">Saathi</span>
          <span className="sub">Navigator console</span>
        </div>

        <ClockBar snapshot={world.snapshot} connected={world.connected} />

        <div className="segmented" role="group" aria-label="View">
          <button
            type="button"
            aria-pressed={view === "journey"}
            onClick={() => setView("journey")}
          >
            One family
          </button>
          <button
            type="button"
            aria-pressed={view === "cohort"}
            onClick={() => setView("cohort")}
          >
            Cohort
          </button>
        </div>

        <span className="spacer" />

        <span className="boundary" title="The scope boundary, enforced in code">
          <Shield size={14} />
          Logistics only · no results, no diagnosis, no advice
        </span>
      </header>

      <div className="layout">
        <CallList
          patients={patients}
          alerts={alerts}
          watched={watched}
          selectedId={selected?.id ?? null}
          onSelect={setSelected}
        />

        <main className="stage">
          {error && (
            <Notice tone="stop">
              <strong>The console cannot reach the planner.</strong> {error} — start the
              API with <span className="mono">make api</span>.
            </Notice>
          )}

          <ActivityStrip
            events={world.events}
            connected={world.connected}
            onSelect={openForPatient}
          />

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
                <DecisionTrace response={plan} steps={steps} patient={selected} />
                <VisitChecklist response={plan} />
                <MessagePipeline response={plan} patient={selected} />
                <InboundCard messages={inbound} patient={selected} />
                <JourneyStepper steps={steps} response={plan} />
                <EvidenceLedger ledger={ledger} focused={cited} />
              </>
            ) : (
              !error && <Notice tone="calm">Loading families…</Notice>
            )
          ) : (
            <>
              <OperatorControls
                snapshot={world.snapshot}
                patients={patients}
                onChange={refreshCohort}
              />
              <DeskQueue queue={desk} onConfirmed={refreshCohort} onSelect={openForPatient} />
              <CohortPanel metrics={metrics} />
              <AlertsPanel alerts={alerts} onSelect={openForPatient} />
            </>
          )}
        </main>
      </div>
    </CiteContext.Provider>
  );
}
