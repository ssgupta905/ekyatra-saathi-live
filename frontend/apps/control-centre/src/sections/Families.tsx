import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  boards,
  live,
  type Alert,
  type CareStep,
  type InboundMessage,
  type LedgerView,
  type Patient,
  type PlanBoard as Board,
  type PlanResponse,
} from "@saathi/api-client";
import {
  ActivityStrip,
  CiteContext,
  DecisionTrace,
  EvidenceLedger,
  InboundCard,
  Notice,
  PlanBoard,
  type Citation,
} from "@saathi/ui-web";
import { CallBrief } from "../components/CallBrief";
import { CallList } from "../components/CallList";
import { DecisionHero } from "../components/DecisionHero";
import { JourneyStepper } from "../components/JourneyStepper";
import { MessagePipeline } from "../components/MessagePipeline";
import { SegmentedControl } from "../components/SegmentedControl";
import { VisitChecklist } from "../components/VisitChecklist";
import { useWorld } from "../world";

const TABS = [
  { value: "why" as const, label: "Why" },
  { value: "pathway" as const, label: "Pathway" },
  { value: "timeline" as const, label: "Timeline" },
  { value: "checklist" as const, label: "Checklist" },
  { value: "message" as const, label: "Message" },
  { value: "family" as const, label: "Family" },
  { value: "ledger" as const, label: "Ledger" },
];
type Tab = (typeof TABS)[number]["value"];

/**
 * One family at a time, with everything behind the answer.
 *
 * The call list down the left (alerts first, then the furthest away; no score),
 * the answer and the brief to read before dialling, and the detail you choose:
 * why, the branching pathway, the timeline, what to bring, the message and the
 * four gates it passed, what the family wrote, and the ledger every claim cites.
 * The original console's navigator view, wide again.
 */
export function Families({
  patientId,
  tab,
  onOpen,
}: {
  patientId: string | null;
  tab: string | null;
  onOpen: (patientId: string, tab?: string) => void;
}) {
  const world = useWorld();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [steps, setSteps] = useState<CareStep[]>([]);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [ledger, setLedger] = useState<LedgerView | null>(null);
  const [inbound, setInbound] = useState<InboundMessage[]>([]);
  const [cited, setCited] = useState<Citation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [changedAt, setChangedAt] = useState(0);
  const lastDecision = useRef<string | null>(null);

  const { cohortRevision } = world;
  const detail: Tab = (TABS.find((t) => t.value === tab)?.value ?? "why") as Tab;

  useEffect(() => {
    api.patients().then(setPatients).catch((e: Error) => setError(e.message));
    api.alerts().then(setAlerts).catch(() => undefined);
  }, [cohortRevision]);

  const selected = useMemo(
    () => patients.find((p) => p.id === patientId) ?? patients[0] ?? null,
    [patients, patientId],
  );
  const revision = world.revisionFor(selected?.id ?? null);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    const id = selected.id;
    Promise.all([api.steps(id), api.plan(id), live.inbound(id), api.ledger(id), boards.one(id)])
      .then(([stepRows, planResponse, messages, ledgerView, boardView]) => {
        if (cancelled) return;
        setSteps(stepRows);
        setPlan(planResponse);
        setInbound(messages);
        setLedger(ledgerView);
        setBoard(boardView);
        setError(null);
        const key = `${id}:${planResponse.plan?.decision ?? null}`;
        if (lastDecision.current?.startsWith(`${id}:`) && lastDecision.current !== key) {
          setChangedAt(Date.now());
        }
        lastDecision.current = key;
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [selected, revision, cohortRevision]);

  const focusCitation = useCallback(
    (ledgerId: string) => {
      if (selected) onOpen(selected.id, "ledger");
      setCited((prev) => ({ id: ledgerId, n: (prev?.n ?? 0) + 1 }));
    },
    [selected, onOpen],
  );

  const targetKind = useMemo(() => {
    const id = plan?.plan?.target_step_id;
    return id ? (steps.find((s) => s.id === id)?.kind ?? null) : null;
  }, [plan, steps]);

  return (
    <CiteContext.Provider value={focusCitation}>
      <div className="cc-families">
        <CallList
          patients={patients}
          alerts={alerts}
          watched={world.snapshot?.watched ?? []}
          selectedId={selected?.id ?? null}
          onSelect={(p) => onOpen(p.id)}
        />

        <div className="cc-family">
          {error && <Notice tone="warn">{error}</Notice>}
          {!selected ? (
            !error && (
              <Notice tone="calm">
                No families on record yet.
                {world.snapshot?.world === "real" && " Register one from the Desk."}
              </Notice>
            )
          ) : (
            <div className="split">
              <div className="split-main">
                <DecisionHero
                  response={plan}
                  patient={selected}
                  targetKind={targetKind}
                  justChanged={Date.now() - changedAt < 2000}
                />
                <CallBrief patientId={selected.id} revision={revision} />
                <ActivityStrip
                  events={world.events}
                  connected={world.connected}
                  onSelect={(id) => onOpen(id)}
                />
              </div>
              <div className="split-aside">
                <SegmentedControl
                  options={TABS}
                  value={detail}
                  onChange={(next) => onOpen(selected.id, next)}
                  aria-label="Detail"
                />
                <div key={detail} className="panel-fade">
                  {detail === "why" && <DecisionTrace response={plan} steps={steps} patient={selected} />}
                  {detail === "pathway" &&
                    (board ? <PlanBoard board={board} /> : <Notice tone="calm">Loading the pathway…</Notice>)}
                  {detail === "timeline" && <JourneyStepper steps={steps} response={plan} />}
                  {detail === "checklist" && <VisitChecklist response={plan} />}
                  {detail === "message" && <MessagePipeline response={plan} patient={selected} />}
                  {detail === "family" && <InboundCard messages={inbound} language={selected.language} />}
                  {detail === "ledger" && <EvidenceLedger ledger={ledger} focused={cited} />}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </CiteContext.Provider>
  );
}
