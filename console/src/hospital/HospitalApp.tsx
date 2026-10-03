import { useCallback, useEffect, useMemo, useState } from "react";
import {
  boards,
  disruptions as disruptionApi,
  stories as storyApi,
  type PendingOption,
  type PlanBoard as Board,
  type Story,
} from "../lib/api";
import { useLiveWorld } from "../lib/live";
import { useIdentity } from "../lib/identity";
import { fmtDate } from "../lib/format";
import { ClockBar } from "../components/ClockBar";
import { StoryBar } from "../components/StoryBar";
import { AgentStatus } from "../components/AgentStatus";
import { PlanBoard } from "../components/PlanBoard";
import { OptionsApprovalCard } from "../components/OptionsApprovalCard";
import { IssueReporter } from "./IssueReporter";
import { ActivityStrip } from "../components/ActivityStrip";
import { ExplainPane } from "./ExplainPane";
import { PersonaSwitcher } from "../components/PersonaSwitcher";
import { Chip, DecisionGlyph, Notice } from "../ui/primitives";
import { Bell, Shield } from "../ui/icons";
import { DemoNav } from "../ui/DemoNav";

/**
 * The hospital's screen. A separate application from the family's phone.
 *
 * Ordered by what a navigator actually asks, in the order they ask it:
 * *what happened*, *what needs me*, *what changed* — and only then *why*.
 *
 * An earlier version had this backwards. The pathway diagram held the middle
 * of the screen and the two things a navigator reaches for on a bad morning —
 * reporting an outage, and seeing what just moved — were squeezed into a
 * 300px gutter. A branching DAG is what you open when a family argues with the
 * decision; it is not what you need at 7:40 am when a machine has just failed.
 * So the pathway and the decision trace are now collapsed by default, one
 * click away, and the live feed and the issue reporter have the width.
 *
 * This replaced a single page that tried to be six consoles and a family
 * phone at once. The persona switcher survives, because signing in as Seema
 * and then as Dr Sinha is how the brief asks for the stories to be presented,
 * but it now changes who may approve rather than which screen you get.
 *
 * Invariant 8 holds here as everywhere: this console reflects the world and
 * never causes it. Nothing on this page computes a decision, a date, or a
 * ranking — the two controls that write anything are a desk reporting a
 * resource down, and a human approving one of the options the planner ranked.
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

export default function HospitalApp() {
  const [persona, choosePersona] = useIdentity();
  const world = useLiveWorld();
  const [rows, setRows] = useState<Board[]>([]);
  const [pending, setPending] = useState<PendingOption[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [storyId, setStoryId] = useState<string | null>(null);
  const [story, setStory] = useState<Story | null>(null);
  const [affected, setAffected] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Two ways to read one family: the pathway (what is waiting on what) and the
  // trace (why this answer, down to the ledger rows). Both are about the same
  // family, so they are a tab on one pane rather than two places to navigate.
  const [lens, setLens] = useState<"pathway" | "why" | null>(null);

  const refresh = useCallback(() => {
    boards
      .all()
      .then((result) => {
        setRows(result.boards);
        setSelected((current) => current ?? result.boards[0]?.patient.id ?? null);
      })
      .catch((e: Error) => setError(e.message));
    disruptionApi.pending().then(setPending).catch(() => undefined);
    storyApi
      .state()
      .then((state) => {
        if (!state.scripted || state.stories.length === 0) return setStory(null);
        const chosen = state.stories.find((s) => s.id === storyId) ?? state.stories[0];
        setStory(chosen);
        setStoryId((current) => current ?? chosen.id);
      })
      .catch(() => setStory(null));
  }, [storyId]);

  useEffect(refresh, [refresh, world.cohortRevision]);

  const waiting = useMemo(
    () => new Map(pending.map((row) => [row.patient_id, row])),
    [pending],
  );

  // Families needing a human first. The order is a consequence of two facts
  // anyone can check — is a decision waiting, and how far would they travel —
  // not a priority score. There is no field here that could hold one.
  const ordered = useMemo(
    () => [...rows].sort((a, b) => {
      const pa = waiting.has(a.patient.id) ? 0 : 1;
      const pb = waiting.has(b.patient.id) ? 0 : 1;
      return pa - pb || b.patient.distance_km - a.patient.distance_km;
    }),
    [rows, waiting],
  );

  const board = ordered.find((row) => row.patient.id === selected) ?? ordered[0] ?? null;
  const decide = board ? waiting.get(board.patient.id) : undefined;
  const canApprove = persona.role === "navigator" || persona.role === "doctor";

  return (
    <div className="hx-app">
      <DemoNav />
      <header className="hx-top">
        <div className="hx-brand">
          <span className="name">Saathi</span>
          <span className="sub">Hospital</span>
        </div>

        <ClockBar snapshot={world.snapshot} connected={world.connected} />

        <span className="spacer" />

        {pending.length > 0 && (
          <Chip tone="wait">
            <Bell size={12} />
            {pending.length} waiting on a person
          </Chip>
        )}

        <PersonaSwitcher persona={persona} onChoose={choosePersona} />

        <span className="boundary" title="The scope boundary, enforced in code">
          <Shield size={13} />
          Logistics only
        </span>
      </header>

      <AgentStatus working={world.working} events={world.events} />

      <StoryBar
        selected={storyId}
        onSelect={setStoryId}
        onAdvanced={refresh}
        revision={world.cohortRevision}
      />

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

        {/* what happened, what needs me, what changed */}
        <main className="hx-work">
          {error && <Notice tone="warn">{error}</Notice>}

          <IssueReporter onReported={(ids) => { setAffected(ids); refresh(); }} />

          {decide && canApprove && (
            <OptionsApprovalCard
              disruptionId={decide.disruption_id}
              patientId={decide.patient_id}
              approverRole={persona.role}
              approverName={persona.name}
              onApproved={refresh}
            />
          )}
          {decide && !canApprove && (
            <Notice tone="warn">
              {decide.option_count} options are ready for {decide.patient_id}, but a{" "}
              {decide.requires_doctor ? "doctor" : "navigator"} has to choose. Sign in as
              one to approve.
            </Notice>
          )}
          {!decide && affected && (
            <Notice tone="calm">
              {affected.length} famil{affected.length === 1 ? "y" : "ies"} picked up by the
              planner. Holding messages went out before any new date was worked out.
            </Notice>
          )}

          <ActivityStrip
            events={world.events}
            connected={world.connected}
            onSelect={setSelected}
          />

          {/* Why, when you need it — not in the way when you do not. */}
          {board && (
            <div className="hx-detail">
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
              </div>

              {lens === "pathway" && <PlanBoard board={board} compact />}
              {lens === "why" && <ExplainPane patientId={board.patient.id} />}
            </div>
          )}
        </main>
      </div>

      {story && (
        <p className="hx-foot">
          {story.title} · {story.who}
        </p>
      )}
    </div>
  );
}
