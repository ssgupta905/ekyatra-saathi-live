import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  boards,
  disruptions,
  live,
  reports,
  LANGUAGE_NAMES,
  type Alert,
  type CareStep,
  type InboundMessage,
  type LedgerView,
  type Patient,
  type PendingOption,
  type PlanBoard as Board,
  type PlanResponse,
  type ReportRow,
} from "@saathi/api-client";
import {
  CiteContext,
  DecisionTrace,
  EvidenceLedger,
  InboundCard,
  PlanBoard,
  type Citation,
} from "@saathi/ui-web";
import { CallBrief } from "../components/CallBrief";
import { DecisionHero } from "../components/DecisionHero";
import { FamilyList } from "../components/FamilyList";
import { JourneyStepper } from "../components/JourneyStepper";
import { JourneyStrip } from "../components/JourneyStrip";
import { MessagePipeline } from "../components/MessagePipeline";
import { RecordEditor } from "../components/RecordEditor";
import { ReportTable } from "../components/ReportTable";
import { VisitChecklist } from "../components/VisitChecklist";
import { usePersona } from "../session";
import { Drawer, EmptyState, Layer, Pill, SkeletonRows, useOpenLayers } from "../ui/kit";
import * as I from "../ui/icons";
import { useWorld } from "../world";

/**
 * One family, in layers.
 *
 * First the answer and the shape of the journey, which is what a person needs
 * in the first second. Then, only when asked, why; the reports; what to bring;
 * what the family was told and what they said; the pathway; the evidence. Each
 * layer says in one line whether it is worth opening, and loads only when open.
 */
export function Families({
  patientId,
  layer,
  onOpen,
}: {
  patientId: string | null;
  layer: string | null;
  onOpen: (patientId: string, layer?: string) => void;
}) {
  const world = useWorld();
  const { persona } = usePersona();
  const [patients, setPatients] = useState<Patient[] | null>(null);
  const [cohort, setCohort] = useState<Board[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [pending, setPending] = useState<PendingOption[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.patients().then(setPatients).catch((e: Error) => setError(e.message));
    boards.all({ everyone: true }).then((r) => setCohort(r.boards)).catch(() => undefined);
    api.alerts().then(setAlerts).catch(() => undefined);
    disruptions.pending().then(setPending).catch(() => undefined);
  }, [world.cohortRevision]);

  const selected = useMemo(
    () => patients?.find((p) => p.id === patientId) ?? patients?.[0] ?? null,
    [patients, patientId],
  );

  return (
    <div className="fam">
      <FamilyList
        patients={patients ?? []}
        boards={cohort}
        alerts={alerts}
        pending={pending}
        selectedId={selected?.id ?? null}
        today={world.snapshot?.current ?? null}
        onSelect={(id) => onOpen(id)}
      />
      <div className="fam-main">
        {error && <div className="notice warn">{error}</div>}
        {patients === null ? (
          <SkeletonRows rows={6} />
        ) : !selected ? (
          <EmptyState title="No families on record yet" icon={<I.Users />}>
            {world.snapshot?.world === "real" ? "Register one from Enter records." : ""}
          </EmptyState>
        ) : (
          <FamilyWorkspace
            key={selected.id}
            patient={selected}
            focus={layer}
            canEdit={world.snapshot?.world === "real" && ["desk", "navigator", "admin"].includes(persona.role)}
            alerted={alerts.some((a) => a.patient_id === selected.id)}
            deciding={pending.some((p) => p.patient_id === selected.id)}
            onLayer={(l) => onOpen(selected.id, l)}
          />
        )}
      </div>
    </div>
  );
}

function FamilyWorkspace({
  patient,
  focus,
  canEdit,
  alerted,
  deciding,
  onLayer,
}: {
  patient: Patient;
  focus: string | null;
  canEdit: boolean;
  alerted: boolean;
  deciding: boolean;
  onLayer: (layer: string) => void;
}) {
  const world = useWorld();
  const revision = world.revisionFor(patient.id);
  const [steps, setSteps] = useState<CareStep[]>([]);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [reportRows, setReportRows] = useState<ReportRow[]>([]);
  const [edits, setEdits] = useState(0);
  const [brief, setBrief] = useState(false);
  const [cited, setCited] = useState<Citation | null>(null);
  const [changedAt, setChangedAt] = useState(0);
  const last = useRef<string | null>(null);
  const [open, toggle, ensure] = useOpenLayers("family", []);

  useEffect(() => {
    if (focus) ensure(focus);
  }, [focus, ensure]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.steps(patient.id), api.plan(patient.id), reports.list({ patient_id: patient.id })])
      .then(([s, p, r]) => {
        if (cancelled) return;
        setSteps(s);
        setPlan(p);
        setReportRows(r.reports);
        const key = p.plan?.decision ?? null;
        if (last.current !== null && last.current !== key) setChangedAt(Date.now());
        last.current = key;
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [patient.id, revision, world.cohortRevision, edits]);

  const focusCitation = useCallback(
    (ledgerId: string) => {
      ensure("evidence");
      setCited((prev) => ({ id: ledgerId, n: (prev?.n ?? 0) + 1 }));
      window.setTimeout(() => document.querySelector('[data-layer="evidence"]')?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    },
    [ensure],
  );

  const targetKind = useMemo(() => {
    const id = plan?.plan?.target_step_id;
    return id ? (steps.find((s) => s.id === id)?.kind ?? null) : null;
  }, [plan, steps]);

  const decision = plan?.plan?.decision ?? null;
  const urgentReports = reportRows.filter((r) => r.state === "overdue" || r.state === "due").length;
  const pendingReports = reportRows.filter((r) => r.status === "pending_result").length;
  const blockers = plan?.plan?.blocked_by.length ?? 0;
  const bring = plan?.plan?.what_to_bring.length ?? 0;
  const held = plan?.routed_to_care_team;
  const onToggle = (id: string) => {
    toggle(id);
    if (!open.has(id)) onLayer(id);
  };

  return (
    <CiteContext.Provider value={focusCitation}>
      <header className="fam-head">
        <div className="fam-id">
          <span className="fam-avatar">{(patient.name || patient.id).replace(/^P-?/, "").slice(0, 2).toUpperCase()}</span>
          <div>
            <h1>{patient.name || patient.id}</h1>
            <p>
              {patient.name && <span className="mono">{patient.id} · </span>}
              {patient.home_district} · {Math.round(patient.home_distance_km)} km from {patient.hospital_id} · hears {LANGUAGE_NAMES[patient.language]}
            </p>
          </div>
        </div>
        <div className="fam-head-flags">
          {deciding && <Pill tone="wait">Needs a decision</Pill>}
          {alerted && <Pill tone="critical">Needs a call</Pill>}
          <button type="button" className="btn" onClick={() => setBrief(true)}>
            <I.FileText size={15} /> Before you call
          </button>
        </div>
      </header>

      <div className="fam-summary">
        <DecisionHero response={plan} patient={patient} targetKind={targetKind} justChanged={Date.now() - changedAt < 2500} />
        <section className="ui-panel fam-journey">
          <header>
            <div>
              <h2>The journey</h2>
              <p>Done, waiting, and the visit it all leads to</p>
            </div>
          </header>
          <div className="ui-panel-body">
            <JourneyStrip steps={steps} response={plan} />
          </div>
        </section>
      </div>

      <div className="fam-layers">
        <Layer id="why" title="Why this answer" icon={<I.Graph size={16} />} open={open.has("why")} onToggle={onToggle}
          summary={decision ? `${blockers ? `${blockers} thing${blockers > 1 ? "s" : ""} in the way` : "nothing in the way"} · every claim cited` : "…"}>
          {() => <DecisionTrace response={plan} steps={steps} patient={patient} />}
        </Layer>
        <Layer id="reports" title="Reports" icon={<I.FileText size={16} />} open={open.has("reports")} onToggle={onToggle}
          tone={urgentReports ? "wait" : "neutral"}
          summary={reportRows.length ? `${pendingReports} pending${urgentReports ? ` · ${urgentReports} due or overdue` : ""} · ${reportRows.length - pendingReports} released` : "none"}>
          {() => <div className="cc-flush"><ReportTable rows={reportRows} showFamily={false} /></div>}
        </Layer>
        <Layer id="timeline" title="Every step" icon={<I.Ledger size={16} />} open={open.has("timeline")} onToggle={onToggle}
          summary={`${steps.length} on record`}>
          {() => <JourneyStepper steps={steps} response={plan} />}
        </Layer>
        <Layer id="checklist" title="What to bring, where to go" icon={<I.Inbox size={16} />} open={open.has("checklist")} onToggle={onToggle}
          summary={decision === "go" ? `${bring} items · first stop ${plan?.plan?.where_to_go_first ?? "—"}` : "only once they are cleared to travel"}>
          {() => <VisitChecklist response={plan} />}
        </Layer>
        <Layer id="message" title="What the family was told" icon={<I.Approve size={16} />} open={open.has("message")} onToggle={onToggle}
          tone={held ? "wait" : "neutral"}
          summary={held ? "held by the guard for a person" : plan?.message_body ? "sent, after four checks" : "no message written yet"}>
          {() => <MessagePipeline response={plan} patient={patient} />}
        </Layer>
        <Layer id="family" title="What the family said" icon={<I.Users size={16} />} open={open.has("family")} onToggle={onToggle}
          tone={alerted ? "critical" : "neutral"} summary={alerted ? "a question needs a person" : "their messages, as the guard read them"}>
          {() => <InboundLayer patient={patient} revision={revision} />}
        </Layer>
        <Layer id="pathway" title="Pathway diagram" icon={<I.Graph size={16} />} open={open.has("pathway")} onToggle={onToggle}
          summary="what waits on what">
          {() => <BoardLayer patientId={patient.id} revision={revision} />}
        </Layer>
        <Layer id="evidence" title="Evidence" icon={<I.Ledger size={16} />} open={open.has("evidence")} onToggle={onToggle}
          summary="the hash-chained record behind every claim">
          {() => <LedgerLayer patientId={patient.id} revision={revision} cited={cited} />}
        </Layer>
        {canEdit && (
          <Layer id="record" title="Edit the record" icon={<I.UserPlus size={16} />} open={open.has("record")} onToggle={onToggle}
            summary="the family's details and steps">
            {() => <RecordEditor patient={patient} steps={steps} onChanged={() => setEdits((n) => n + 1)} />}
          </Layer>
        )}
      </div>

      <Drawer open={brief} title="Before you call" onClose={() => setBrief(false)} width={480}>
        <CallBrief patientId={patient.id} revision={revision} />
      </Drawer>
    </CiteContext.Provider>
  );
}

function InboundLayer({ patient, revision }: { patient: Patient; revision: number }) {
  const [rows, setRows] = useState<InboundMessage[] | null>(null);
  useEffect(() => {
    live.inbound(patient.id).then(setRows).catch(() => setRows([]));
  }, [patient.id, revision]);
  if (!rows) return <SkeletonRows />;
  return <InboundCard messages={rows} language={patient.language} />;
}

function BoardLayer({ patientId, revision }: { patientId: string; revision: number }) {
  const [board, setBoard] = useState<Board | null>(null);
  useEffect(() => {
    boards.one(patientId).then(setBoard).catch(() => setBoard(null));
  }, [patientId, revision]);
  return board ? <PlanBoard board={board} /> : <SkeletonRows rows={4} />;
}

function LedgerLayer({ patientId, revision, cited }: { patientId: string; revision: number; cited: Citation | null }) {
  const [ledger, setLedger] = useState<LedgerView | null>(null);
  useEffect(() => {
    api.ledger(patientId).then(setLedger).catch(() => setLedger(null));
  }, [patientId, revision]);
  return ledger ? <EvidenceLedger ledger={ledger} focused={cited} /> : <SkeletonRows />;
}
