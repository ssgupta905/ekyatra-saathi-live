/**
 * The live stream.
 *
 * One event stream for the whole app. Every frame is something that
 * actually happened in the backend — a day passing, a report confirmed, the
 * planner re-running, the guard holding a message — and most carry the measured
 * duration of the work behind them.
 *
 * The hook deliberately does not hold domain data. It holds *what changed*, and
 * the cards re-fetch. That keeps one source of truth (the API) and means a card
 * can never drift into showing a world the backend has moved on from.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { live, type LiveSnapshot } from "./api";
import { streamUrl } from "./client";

export type EventKind =
  | "clock.tick"
  | "desk.candidate"
  | "desk.confirmed"
  | "step.released"
  | "plan.recomputed"
  | "message.rendered"
  | "message.held"
  | "inbound.received"
  | "guard.blocked"
  | "ledger.appended"
  | "alert.raised"
  | "metrics.updated"
  | "world.reset"
  | "runner.state"
  | "disruption.raised"
  | "holding_message.sent"
  | "options.ready"
  | "approval.recorded"
  | "confirmation.received"
  | "process.answered"
  | "agent.started"
  | "agent.finished"
  | "tool.called"
  | "language.changed";

export interface WorldEvent {
  kind: EventKind;
  at: string;
  sim_date: string;
  patient_id: string | null;
  summary: string;
  duration_ms: number | null;
  payload: Record<string, unknown>;
  seq: number;
}

/** Kept short on purpose: this is "what just happened", not a log file. */
export const EVENT_WINDOW = 80;

export const ALL_KINDS: EventKind[] = [
  "clock.tick",
  "desk.candidate",
  "desk.confirmed",
  "step.released",
  "plan.recomputed",
  "message.rendered",
  "message.held",
  "inbound.received",
  "guard.blocked",
  "ledger.appended",
  "alert.raised",
  "metrics.updated",
  "world.reset",
  "runner.state",
  "disruption.raised",
  "holding_message.sent",
  "options.ready",
  "approval.recorded",
  "confirmation.received",
  "process.answered",
  "agent.started",
  "agent.finished",
  "tool.called",
  "language.changed",
];

/** Events that change something about one family's page. */
export const PATIENT_KINDS = new Set<EventKind>([
  "plan.recomputed",
  "message.rendered",
  "message.held",
  "step.released",
  "ledger.appended",
  "inbound.received",
  "guard.blocked",
  "holding_message.sent",
  "options.ready",
  "approval.recorded",
  "confirmation.received",
  "process.answered",
]);

/** Events that change the cohort view, the desk queue or the alert list. */
export const COHORT_KINDS = new Set<EventKind>([
  "metrics.updated",
  "alert.raised",
  "desk.candidate",
  "desk.confirmed",
  "world.reset",
  "clock.tick",
  "disruption.raised",
  "approval.recorded",
]);

/** The clock and the runner state ride on the snapshot, not the event. */
const SNAPSHOT_KINDS = new Set<EventKind>([
  "clock.tick",
  "runner.state",
  "world.reset",
  "metrics.updated",
]);

export const needsSnapshot = (kind: EventKind): boolean => SNAPSHOT_KINDS.has(kind);

export interface WorkItem {
  id: string;
  task: string;
  detail: string;
  patientId: string | null;
  startedAt: number;
}

/** What the stream has told us so far. Holds *what changed*, never domain data. */
export interface LiveEventState {
  events: WorldEvent[];
  /** Work announced and not yet finished. A screen that only shows finished
   *  work looks frozen while the system is busy. */
  working: WorkItem[];
  revisions: Record<string, number>;
  cohortRevision: number;
}

export const emptyLiveState: LiveEventState = {
  events: [],
  working: [],
  revisions: {},
  cohortRevision: 0,
};

/**
 * Fold one event into the state. Pure, so the web hook and the phone use the
 * same rules and a test can run them without a screen.
 */
export function applyEvent(
  state: LiveEventState,
  event: WorldEvent,
  now: number = Date.now(),
): LiveEventState {
  const events = [event, ...state.events].slice(0, EVENT_WINDOW);

  // In-flight work, so the screen can say what is happening rather than
  // leaving someone watching an unchanged page.
  let working = state.working;
  const workId = event.payload.work_id as string | undefined;
  if (event.kind === "agent.started" && workId) {
    working = [
      ...working,
      {
        id: workId,
        task: event.summary,
        detail: (event.payload.detail as string) ?? "",
        patientId: event.patient_id,
        startedAt: now,
      },
    ];
  } else if (event.kind === "agent.finished" && workId) {
    working = working.filter((item) => item.id !== workId);
  }

  let revisions = state.revisions;
  if (event.patient_id && PATIENT_KINDS.has(event.kind)) {
    revisions = { ...revisions, [event.patient_id]: (revisions[event.patient_id] ?? 0) + 1 };
  }

  const cohortRevision =
    COHORT_KINDS.has(event.kind) || event.kind === "runner.state"
      ? state.cohortRevision + 1
      : state.cohortRevision;

  return { events, working, revisions, cohortRevision };
}

export function parseEvent(raw: string): WorldEvent | null {
  try {
    return JSON.parse(raw) as WorldEvent;
  } catch {
    return null;
  }
}

/** The slice of `EventSource` the hook uses, so a phone can supply its own. */
export interface EventSourceLike {
  onopen: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  addEventListener(kind: string, listener: (event: { data: string }) => void): void;
  close(): void;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

const browserEventSource: EventSourceFactory = (url) =>
  new EventSource(url) as unknown as EventSourceLike;

const RECONNECT_MS = 2000;

export interface LiveWorldState {
  connected: boolean;
  working: WorkItem[];
  snapshot: LiveSnapshot | null;
  events: WorldEvent[];
  /** Bumped when an event names this family — put it in a fetch effect's deps. */
  revisionFor: (patientId: string | null) => number;
  cohortRevision: number;
  refresh: () => void;
}

export interface LiveWorldOptions {
  /**
   * Defaults to the browser's `EventSource`. React Native passes its own.
   * Must be a stable reference (define it at module level): a new function each
   * render would reconnect the stream each render.
   */
  createEventSource?: EventSourceFactory;
}

export function useLiveWorld(options: LiveWorldOptions = {}): LiveWorldState {
  const createEventSource = options.createEventSource ?? browserEventSource;
  const [connected, setConnected] = useState(false);
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [state, setState] = useState<LiveEventState>(emptyLiveState);

  const refresh = useCallback(() => {
    live
      .snapshot()
      .then(setSnapshot)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();

    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    let source: EventSourceLike | null = null;

    const connect = async () => {
      if (closed) return;
      let url: string;
      try {
        url = await streamUrl();
      } catch {
        // Could not get a ticket (server down, or signed out): try again shortly.
        if (!closed) retry = setTimeout(connect, RECONNECT_MS);
        return;
      }
      if (closed) return;
      const current = createEventSource(url);
      source = current;

      current.onopen = () => setConnected(true);

      current.onerror = () => {
        // EventSource retries on its own, but a dev server restart can leave it
        // wedged — reconnect explicitly so the screen recovers unattended.
        setConnected(false);
        current.close();
        if (!closed) retry = setTimeout(connect, RECONNECT_MS);
      };

      const onEvent = (raw: { data: string }) => {
        const event = parseEvent(raw.data);
        if (!event) return;
        setState((previous) => applyEvent(previous, event));
        if (needsSnapshot(event.kind)) refresh();
      };

      for (const kind of ALL_KINDS) current.addEventListener(kind, onEvent);
    };

    connect();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      source?.close();
      source = null;
    };
  }, [refresh, createEventSource]);

  const { revisions } = state;
  const revisionFor = useCallback(
    (patientId: string | null) => (patientId ? (revisions[patientId] ?? 0) : 0),
    [revisions],
  );

  return useMemo(
    () => ({
      connected,
      snapshot,
      events: state.events,
      working: state.working,
      revisionFor,
      cohortRevision: state.cohortRevision,
      refresh,
    }),
    [connected, snapshot, state, revisionFor, refresh],
  );
}

/* ── presentation ───────────────────────────────────────────────────────── */

/** Tone per event kind. Status colour is never the only signal — each of these
 *  pairs with a glyph and the event's own words in the activity strip. */
export const EVENT_TONE: Record<EventKind, "go" | "wait" | "critical" | "info" | "neutral"> = {
  "clock.tick": "neutral",
  "desk.candidate": "wait",
  "desk.confirmed": "go",
  "step.released": "go",
  "plan.recomputed": "info",
  "message.rendered": "go",
  "message.held": "critical",
  "inbound.received": "info",
  "guard.blocked": "critical",
  "ledger.appended": "info",
  "alert.raised": "wait",
  "metrics.updated": "info",
  "world.reset": "neutral",
  "runner.state": "neutral",
  "disruption.raised": "critical",
  "holding_message.sent": "wait",
  "options.ready": "wait",
  "approval.recorded": "go",
  "confirmation.received": "go",
  "process.answered": "info",
  "agent.started": "info",
  "agent.finished": "neutral",
  "tool.called": "info",
  "language.changed": "info",
};

export const EVENT_LABEL: Record<EventKind, string> = {
  "clock.tick": "Day",
  "desk.candidate": "Desk",
  "desk.confirmed": "Desk",
  "step.released": "Feed",
  "plan.recomputed": "Planner",
  "message.rendered": "Message",
  "message.held": "Guard",
  "inbound.received": "Inbound",
  "guard.blocked": "Guard",
  "ledger.appended": "Ledger",
  "alert.raised": "Alert",
  "metrics.updated": "Score",
  "world.reset": "World",
  "runner.state": "Clock",
  "disruption.raised": "Disruption",
  "holding_message.sent": "Holding",
  "options.ready": "Options",
  "approval.recorded": "Approval",
  "confirmation.received": "Confirmed",
  "process.answered": "Process",
  "agent.started": "Working",
  "agent.finished": "Done",
  "tool.called": "Tool",
  "language.changed": "Language",
};

/** Milliseconds, rendered the way a navigator reads them. */
export const fmtMs = (ms: number | null | undefined) =>
  ms == null ? null : ms < 1 ? "<1 ms" : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;

export function secondsAgo(iso: string): number {
  return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
}

export const fmtAgo = (iso: string) => {
  const n = secondsAgo(iso);
  if (n < 2) return "just now";
  if (n < 60) return `${n}s ago`;
  return `${Math.floor(n / 60)}m ago`;
};
