/**
 * The live stream.
 *
 * One `EventSource` for the whole console. Every frame is something that
 * actually happened in the backend — a day passing, a report confirmed, the
 * planner re-running, the guard holding a message — and most carry the measured
 * duration of the work behind them.
 *
 * The hook deliberately does not hold domain data. It holds *what changed*, and
 * the cards re-fetch. That keeps one source of truth (the API) and means a card
 * can never drift into showing a world the backend has moved on from.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { live, type LiveSnapshot } from "./api";

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
const EVENT_WINDOW = 80;

const ALL_KINDS: EventKind[] = [
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
const PATIENT_KINDS = new Set<EventKind>([
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
const COHORT_KINDS = new Set<EventKind>([
  "metrics.updated",
  "alert.raised",
  "desk.candidate",
  "desk.confirmed",
  "world.reset",
  "clock.tick",
  "disruption.raised",
  "approval.recorded",
]);

export interface WorkItem {
  id: string;
  task: string;
  detail: string;
  patientId: string | null;
  startedAt: number;
}

export interface LiveWorldState {
  connected: boolean;
  /** Work announced and not yet finished. A console that only shows finished
   *  work looks frozen while the system is busy. */
  working: WorkItem[];
  snapshot: LiveSnapshot | null;
  events: WorldEvent[];
  /** Bumped when an event names this family — put it in a fetch effect's deps. */
  revisionFor: (patientId: string | null) => number;
  cohortRevision: number;
  refresh: () => void;
}

export function useLiveWorld(): LiveWorldState {
  const [connected, setConnected] = useState(false);
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [events, setEvents] = useState<WorldEvent[]>([]);
  const [revisions, setRevisions] = useState<Record<string, number>>({});
  const [cohortRevision, setCohortRevision] = useState(0);
  const [working, setWorking] = useState<WorkItem[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  const refresh = useCallback(() => {
    live
      .snapshot()
      .then(setSnapshot)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();

    let retry: number | undefined;
    let closed = false;

    const connect = () => {
      if (closed) return;
      const source = new EventSource("/api/stream");
      sourceRef.current = source;

      source.onopen = () => setConnected(true);

      source.onerror = () => {
        // EventSource retries on its own, but a dev server restart can leave it
        // wedged — reconnect explicitly so the console recovers unattended.
        setConnected(false);
        source.close();
        if (!closed) retry = window.setTimeout(connect, 2000);
      };

      const onEvent = (raw: MessageEvent) => {
        let event: WorldEvent;
        try {
          event = JSON.parse(raw.data) as WorldEvent;
        } catch {
          return;
        }
        setEvents((previous) => [event, ...previous].slice(0, EVENT_WINDOW));

        // In-flight work, so the console can say what is happening rather than
        // leaving a navigator watching an unchanged screen.
        const workId = event.payload.work_id as string | undefined;
        if (event.kind === "agent.started" && workId) {
          setWorking((previous) => [
            ...previous,
            {
              id: workId,
              task: event.summary,
              detail: (event.payload.detail as string) ?? "",
              patientId: event.patient_id,
              startedAt: Date.now(),
            },
          ]);
        } else if (event.kind === "agent.finished" && workId) {
          setWorking((previous) => previous.filter((item) => item.id !== workId));
        }

        if (event.patient_id && PATIENT_KINDS.has(event.kind)) {
          const id = event.patient_id;
          setRevisions((previous) => ({ ...previous, [id]: (previous[id] ?? 0) + 1 }));
        }
        if (COHORT_KINDS.has(event.kind) || event.kind === "runner.state") {
          setCohortRevision((n) => n + 1);
        }
        // The clock and the runner state ride on the snapshot, not the event.
        if (
          event.kind === "clock.tick" ||
          event.kind === "runner.state" ||
          event.kind === "world.reset" ||
          event.kind === "metrics.updated"
        ) {
          refresh();
        }
      };

      for (const kind of ALL_KINDS) source.addEventListener(kind, onEvent);
    };

    connect();

    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      sourceRef.current?.close();
      sourceRef.current = null;
    };
  }, [refresh]);

  const revisionFor = useCallback(
    (patientId: string | null) => (patientId ? (revisions[patientId] ?? 0) : 0),
    [revisions],
  );

  return useMemo(
    () => ({ connected, snapshot, events, working, revisionFor, cohortRevision, refresh }),
    [connected, snapshot, events, working, revisionFor, cohortRevision, refresh],
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
