import { useMemo, useState } from "react";
import { live } from "../lib/api";
import { fmtAgo, type LiveWorldState, type WorldEvent } from "../lib/live";
import { PageHeader } from "../components/shell/AppShell";
import { StepAccordion, type Step, type StepState } from "../components/StepAccordion";
import { Badge, Notice } from "../ui/primitives";
import { Play, Rewind } from "../ui/icons";

interface Beat {
  action: string;
  who: string;
}

interface Story {
  id: "shambhu" | "anita";
  patientId: string;
  title: string;
  blurb: string;
  phase: string;
  beats: Beat[];
  /** Who to sign in as to see each loop step from their side. */
  viewAs: (round: number) => string[];
}

/** Mirrors `synthetic/scripted.py` — each beat calls a real runner method. */
const STORIES: Story[] = [
  {
    id: "shambhu",
    patientId: "P-SHAMBHU",
    title: "The MRI machine fails",
    blurb: "Shambhu Prasad, Gaya → Mumbai. MRI-2 goes out of service on the morning of his scan.",
    phase: "Story 1 · before treatment",
    beats: [
      { action: "Report MRI-2 out of service", who: "Imran · radiology desk" },
      { action: "Approve the best-ranked option", who: "Seema · navigator" },
    ],
    viewAs: () => ["imran", "vikash", "seema", "seema", "shambhu"],
  },
  {
    id: "anita",
    patientId: "P-ANITA",
    title: "The echo doctor is called away",
    blurb: "Anita Devi, maintenance dose 13. The hub's only echo cardiologist goes on leave, then the drug delivery is late.",
    phase: "Story 2 · maintenance",
    beats: [
      { action: "Report the cardiologist unavailable", who: "Sanjay · cardiology desk" },
      { action: "Approve the option that keeps the echo first", who: "Dr Sinha · oncologist" },
      { action: "Report the drug delivery not received", who: "Rekha · day-care desk" },
      { action: "Approve the one-trip plan", who: "Dr Sinha · oncologist" },
    ],
    viewAs: (round) => [round === 0 ? "sanjay" : "rekha", "priya", "sinha", "sinha", "anita"],
  },
];

/** The brief's Figure 2 — the same five steps, whatever goes wrong. */
const LOOP = [
  { title: "Desk reports", who: "Person" },
  { title: "Family told first", who: "Rules" },
  { title: "Planner re-solves", who: "Solver" },
  { title: "A person decides", who: "Person" },
  { title: "Everyone updated", who: "Rules" },
];

interface LoopStepEvidence {
  state: StepState;
  summary: string;
  events: WorldEvent[];
}

/** Read the five steps of the latest round for one family off the real event stream. */
function readLoop(events: WorldEvent[], patientId: string): LoopStepEvidence[] {
  const ordered = [...events].sort((a, b) => a.seq - b.seq);
  const raisedIndex = ordered
    .map((e, i) => ({ e, i }))
    .filter(
      ({ e }) =>
        e.kind === "disruption.raised" &&
        Array.isArray(e.payload.affected) &&
        (e.payload.affected as string[]).includes(patientId),
    )
    .pop()?.i;

  const empty = (summary: string): LoopStepEvidence => ({ state: "neutral", summary, events: [] });
  if (raisedIndex === undefined) {
    return [
      empty("Waiting for a desk to report something"),
      empty("Goes out within minutes, before any new date"),
      empty("Every affected family is re-planned"),
      empty("A navigator or doctor picks from ranked options"),
      empty("Desks and family updated in one pass"),
    ];
  }

  const raised = ordered[raisedIndex];
  const after = ordered.slice(raisedIndex + 1).filter((e) => e.patient_id === patientId);
  const holding = after.filter((e) => e.kind === "holding_message.sent");
  const options = after.find((e) => e.kind === "options.ready");
  const approval = after.find((e) => e.kind === "approval.recorded");
  const replans = after.filter((e) => e.kind === "plan.recomputed");
  const autoResolved = !options && replans.length > 0;

  return [
    { state: "done", summary: raised.summary, events: [raised] },
    holding.length
      ? {
          state: "done",
          summary: `Holding message sent on ${holding.map((h) => h.payload.channel).join(" and ")} — don't travel yet`,
          events: holding,
        }
      : { state: "active", summary: "Sending…", events: [] },
    options
      ? { state: "done", summary: options.summary, events: [options] }
      : autoResolved
        ? { state: "done", summary: "Only one way forward — moved automatically", events: replans.slice(0, 1) }
        : { state: "active", summary: "Re-solving…", events: [] },
    approval
      ? { state: "done", summary: approval.summary, events: [approval] }
      : autoResolved
        ? { state: "done", summary: "Not needed — nothing to choose between", events: [] }
        : { state: "waiting", summary: "Waiting on a person — press the next beat or open Decisions", events: [] },
    approval || autoResolved
      ? {
          state: "done",
          summary: approval?.payload.desk
            ? `${String(approval.payload.desk)} desk and the family's plan updated`
            : "The family's plan re-issued from the real planner",
          events: [...(approval ? [approval] : []), ...replans.filter((r) => !approval || r.seq > approval.seq).slice(0, 1)],
        }
      : { state: "neutral", summary: "After the decision", events: [] },
  ];
}

/**
 * A disruption, walked through one beat at a time. Each beat calls the same
 * runner method a person would trigger from their own screen — nothing here is
 * replayed — and each of the five steps shows the event that proves it ran.
 */
export function StoriesPage({
  world,
  onViewAs,
  onOpenFamily,
}: {
  world: LiveWorldState;
  onViewAs: (personaId: string) => void;
  onOpenFamily: (patientId: string) => void;
}) {
  const [storyId, setStoryId] = useState<Story["id"]>("shambhu");
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const snap = world.snapshot;
  const story = STORIES.find((s) => s.id === storyId)!;
  const progress = snap?.story_progress?.[story.id] ?? 0;
  const round = Math.min(Math.floor(progress / 2), story.beats.length / 2 - 1);
  const next = story.beats[progress];
  const loop = useMemo(() => readLoop(world.events, story.patientId), [world.events, story.patientId]);
  const viewAs = story.viewAs(progress >= 2 ? 1 : round);

  const advance = async () => {
    setBusy(true);
    try {
      await live.control("advance_story", undefined, story.id);
      world.refresh();
    } finally {
      setBusy(false);
    }
  };

  const restart = async () => {
    setBusy(true);
    try {
      await live.control("reset");
      world.refresh();
      setOpen(null);
    } finally {
      setBusy(false);
    }
  };

  const steps: Step[] = LOOP.map((def, i) => ({
    id: `loop-${i}`,
    title: def.title,
    state: loop[i].state,
    summary: (
      <>
        <span className="who-chip">{def.who}</span> {loop[i].summary}
      </>
    ),
    content: (
      <div className="loop-detail">
        {loop[i].events.length === 0 ? (
          <p className="empty">Nothing has happened at this step yet.</p>
        ) : (
          <ul className="mini-feed">
            {loop[i].events.map((e) => (
              <li key={e.seq}>
                <span className="mini-summary">{e.summary}</span>
                <span className="mini-when">{fmtAgo(e.at)}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="loop-actions">
          <button type="button" className="btn" onClick={() => onViewAs(viewAs[i])}>
            See this as {viewAs[i]}
          </button>
          <button type="button" className="link-btn" onClick={() => onOpenFamily(story.patientId)}>
            Open {story.patientId}
          </button>
        </div>
      </div>
    ),
  }));

  return (
    <div className="page">
      <PageHeader
        title="Stories"
        question="Walk a disruption through, one step at a time."
        aside={
          <button type="button" className="btn" disabled={busy} onClick={restart}>
            <Rewind /> Restart
          </button>
        }
      />

      {snap && !snap.scripted && (
        <Notice tone="warn">
          The story families aren't in this world. Restart the API with{" "}
          <span className="mono">SAATHI_LIVE_SCRIPTED=true</span>.
        </Notice>
      )}

      <div className="story-picker">
        {STORIES.map((s) => {
          const done = snap?.story_progress?.[s.id] ?? 0;
          return (
            <button
              key={s.id}
              type="button"
              className="story-card"
              aria-pressed={s.id === storyId}
              onClick={() => {
                setStoryId(s.id);
                setOpen(null);
              }}
            >
              <span className="story-phase">{s.phase}</span>
              <span className="story-title">{s.title}</span>
              <span className="story-blurb">{s.blurb}</span>
              <span className="story-progress">
                <span className="story-bar">
                  <span style={{ width: `${(done / s.beats.length) * 100}%` }} />
                </span>
                {done} of {s.beats.length} beats
              </span>
            </button>
          );
        })}
      </div>

      <section className="panel">
        <div className="loop-rail" aria-label="The disruption loop">
          {LOOP.map((def, i) => (
            <button
              key={def.title}
              type="button"
              className={`loop-node ${loop[i].state}`}
              onClick={() => setOpen(`loop-${i}`)}
            >
              <span className="loop-dot">{loop[i].state === "done" ? "✓" : i + 1}</span>
              <span className="loop-label">{def.title}</span>
            </button>
          ))}
        </div>

        <div className="next-beat">
          {next ? (
            <>
              <div>
                <div className="next-label">
                  Next · round {round + 1} of {story.beats.length / 2}
                </div>
                <div className="next-action">{next.action}</div>
                <div className="next-who">{next.who}</div>
              </div>
              <button type="button" className="btn primary" disabled={busy || !snap?.scripted} onClick={advance}>
                {busy ? "Working…" : (
                  <>
                    <Play /> Do it
                  </>
                )}
              </button>
            </>
          ) : (
            <>
              <div>
                <div className="next-label">Story complete</div>
                <div className="next-action">Every step ran on real code — open the family to see the result.</div>
              </div>
              <button type="button" className="btn primary" onClick={() => onOpenFamily(story.patientId)}>
                Open {story.patientId}
              </button>
            </>
          )}
        </div>

        {progress === 0 && (snap?.day ?? 0) > 0 && (
          <Notice tone="warn">
            The clock has moved since the story families were seeded. <Badge tone="wait">Restart</Badge>{" "}
            first so the booked scan still falls inside the outage.
          </Notice>
        )}
      </section>

      <div className="section-label">The five steps, as they happened</div>
      <StepAccordion steps={steps} open={open} onOpen={setOpen} />
    </div>
  );
}
