import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  boards,
  disruptions as disruptionApi,
  live,
  useLiveWorld,
  type Alert,
  type InboundMessage,
  type PendingOption,
  type PlanBoard as Board,
} from "@saathi/api-client";
import {
  ActivityStrip,
  AgentStatus,
  AlertsPanel,
  AppShell,
  Bell,
  Chip,
  DecisionGlyph,
  ExplainPane,
  InboundCard,
  Notice,
  OptionsApprovalCard,
  PlanBoard,
  fmtDate,
} from "@saathi/ui-web";
import { IDENTITY } from "./identity";

/**
 * The navigator's screen: the families, and what each one needs from a person.
 *
 * Ordered by what a navigator actually asks, in the order they ask it: *what
 * needs me*, *what did the family say*, *what changed*, and only then *why*. A
 * branching pathway is what you open when a family argues with the decision; it
 * is not what you need on a bad morning, so it and the decision trace are
 * collapsed by default.
 *
 * Reporting an outage is the desk's job and lives in the desk app. A navigator
 * sees the consequence: families the planner picked up, holding messages already
 * sent, and the ranked options waiting for a person to choose.
 *
 * Invariant 8 holds here as everywhere: this app reflects the world and never
 * causes it. Nothing on this page computes a decision, a date or a ranking. The
 * one control that writes anything is a human approving one of the options the
 * planner ranked.
 */

function WorklistRow({
  board,
  selected,
  needsDecision,
  onSelect,
}: {
  board: Board;
  selected: boolean;
  needsDecision: boolean;
  onSelect: () => void;
}) {
  const decision = board.decision;
  const blocking = board.waiting_on.length;

  return (
    <button
      type="button"
      className={`hx-row${selected ? " on" : ""}${needsDecision ? " needs" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="hx-row-top">
        <span className="hx-row-id">{board.patient.id}</span>
        {decision && (
          <span className={`hx-row-dot ${decision}`}>
            <DecisionGlyph decision={decision} size={12} />
          </span>
        )}
      </span>
      <span className="hx-row-where">
        {board.patient.district} · {board.patient.distance_km} km
      </span>
      <span className="hx-row-why">
        {needsDecision ? (
          <span className="hx-needs">
            <Bell size={11} /> needs a decision
          </span>
        ) : decision === "go" && board.travel_on ? (
          `travel ${fmtDate(board.travel_on)}`
        ) : blocking > 0 ? (
          `waiting on ${board.waiting_on[0].label.toLowerCase()}`
        ) : (
          "nothing in the way"
        )}
      </span>
    </button>
  );
}

export default function App() {
  const world = useLiveWorld();
  const [rows, setRows] = useState<Board[]>([]);
  const [pending, setPending] = useState<PendingOption[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [inbound, setInbound] = useState<InboundMessage[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Two ways to read one family: the pathway (what is waiting on what) and the
  // trace (why this answer, down to the ledger rows). Both are about the same
  // family, so they are a tab on one pane rather than two places to navigate.
  const [lens, setLens] = useState<"pathway" | "why" | null>(null);
  const detailRef = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(() => {
    boards
      .all()
      .then((result) => {
        setRows(result.boards);
        setSelected((current) => current ?? result.boards[0]?.patient.id ?? null);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
    disruptionApi.pending().then(setPending).catch(() => undefined);
    api.alerts().then(setAlerts).catch(() => undefined);
  }, []);

  useEffect(refresh, [refresh, world.cohortRevision]);

  // Opening the detail puts it below the live feed, so without this the press
  // appears to do nothing on a short window.
  useEffect(() => {
    if (lens) detailRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [lens]);

  const waiting = useMemo(
    () => new Map(pending.map((row) => [row.patient_id, row])),
    [pending],
  );

  // Families needing a human first. The order is a consequence of two facts
  // anyone can check — is a decision waiting, and how far would they travel —
  // not a priority score. There is no field here that could hold one.
  const ordered = useMemo(
    () =>
      [...rows].sort((a, b) => {
        const pa = waiting.has(a.patient.id) ? 0 : 1;
        const pb = waiting.has(b.patient.id) ? 0 : 1;
        return pa - pb || b.patient.distance_km - a.patient.distance_km;
      }),
    [rows, waiting],
  );

  const board = ordered.find((row) => row.patient.id === selected) ?? ordered[0] ?? null;
  const decide = board ? waiting.get(board.patient.id) : undefined;

  // What this family wrote in, re-read whenever something names them.
  const familyId = board?.patient.id ?? null;
  const familyRevision = world.revisionFor(familyId);
  useEffect(() => {
    if (!familyId) return setInbound([]);
    live.inbound(familyId).then(setInbound).catch(() => setInbound([]));
  }, [familyId, familyRevision]);

  return (
    <AppShell
      app="Navigator"
      identity={IDENTITY}
      snapshot={world.snapshot}
      connected={world.connected}
      status={
        pending.length > 0 && (
          <Chip tone="wait">
            <Bell size={12} />
            {pending.length} waiting on a person
          </Chip>
        )
      }
    >
      <AgentStatus working={world.working} events={world.events} />

      <div className="hx-panes">
        {/* who needs me */}
        <aside className="hx-worklist">
          <div className="hx-pane-head">
            <span>Families</span>
            <span className="hint">{ordered.length} watched</span>
          </div>
          <div className="hx-worklist-scroll">
            {ordered.map((row) => (
              <WorklistRow
                key={row.patient.id}
                board={row}
                selected={row.patient.id === board?.patient.id}
                needsDecision={waiting.has(row.patient.id)}
                onSelect={() => setSelected(row.patient.id)}
              />
            ))}
            {ordered.length === 0 && <Notice tone="calm">No families yet.</Notice>}
          </div>
        </aside>

        {/* what needs me, what the family said, what changed */}
        <main className="hx-work">
          {error && <Notice tone="warn">{error}</Notice>}

          {decide && !decide.requires_doctor && (
            <OptionsApprovalCard
              disruptionId={decide.disruption_id}
              patientId={decide.patient_id}
              approverRole={IDENTITY.role}
              approverName={IDENTITY.name}
              onApproved={refresh}
            />
          )}
          {decide?.requires_doctor && (
            <Notice tone="warn">
              {decide.option_count} options are ready for {decide.patient_id}, but they touch
              treatment, so a doctor has to choose. They are waiting in the doctor app.
            </Notice>
          )}

          <AlertsPanel alerts={alerts} onSelect={setSelected} />

          {board && <InboundCard messages={inbound} language={board.patient.language} />}

          <ActivityStrip events={world.events} connected={world.connected} onSelect={setSelected} />

          {/* Why, when you need it — not in the way when you do not. */}
          {board && (
            <div className="hx-detail" ref={detailRef}>
              <div className="hx-lens">
                <div className="segmented" role="group" aria-label="Look closer at this family">
                  <button
                    type="button"
                    aria-pressed={lens === "pathway"}
                    onClick={() => setLens(lens === "pathway" ? null : "pathway")}
                  >
                    Pathway
                  </button>
                  <button
                    type="button"
                    aria-pressed={lens === "why"}
                    onClick={() => setLens(lens === "why" ? null : "why")}
                  >
                    Why this answer
                  </button>
                </div>
                <span className="hint">
                  {lens === "pathway"
                    ? `what is waiting on what, for ${board.patient.id}`
                    : lens === "why"
                      ? `every claim behind ${board.patient.id}'s answer, and its source`
                      : `look closer at ${board.patient.id}`}
                </span>
                {lens && (
                  <button type="button" className="btn hx-close" onClick={() => setLens(null)}>
                    Close
                  </button>
                )}
              </div>

              {lens === "pathway" && <PlanBoard board={board} compact />}
              {lens === "why" && <ExplainPane patientId={board.patient.id} />}
            </div>
          )}
        </main>
      </div>
    </AppShell>
  );
}
