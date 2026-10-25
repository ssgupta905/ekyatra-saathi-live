import { describe, expect, it } from "vitest";
import {
  ALL_KINDS,
  EVENT_LABEL,
  EVENT_TONE,
  EVENT_WINDOW,
  applyEvent,
  emptyLiveState,
  needsSnapshot,
  parseEvent,
  type EventKind,
  type WorldEvent,
} from "./live";

let seq = 0;
const event = (kind: EventKind, patch: Partial<WorldEvent> = {}): WorldEvent => ({
  kind,
  at: "2026-10-25T10:00:00Z",
  sim_date: "2026-10-25",
  patient_id: null,
  summary: kind,
  duration_ms: null,
  payload: {},
  seq: ++seq,
  ...patch,
});

describe("applyEvent", () => {
  it("keeps the newest events first and caps the window", () => {
    let state = emptyLiveState;
    for (let i = 0; i < EVENT_WINDOW + 20; i++) state = applyEvent(state, event("clock.tick"));
    expect(state.events).toHaveLength(EVENT_WINDOW);
    expect(state.events[0].seq).toBeGreaterThan(state.events[1].seq);
  });

  it("tracks work from agent.started until agent.finished", () => {
    const started = event("agent.started", {
      patient_id: "P1",
      summary: "Re-planning",
      payload: { work_id: "w1", detail: "50 families" },
    });
    let state = applyEvent(emptyLiveState, started, 1234);
    expect(state.working).toEqual([
      { id: "w1", task: "Re-planning", detail: "50 families", patientId: "P1", startedAt: 1234 },
    ]);

    state = applyEvent(state, event("agent.finished", { payload: { work_id: "w1" } }));
    expect(state.working).toEqual([]);
  });

  it("ignores work events that carry no work_id", () => {
    const state = applyEvent(emptyLiveState, event("agent.started"));
    expect(state.working).toEqual([]);
  });

  it("bumps a family's revision only for events that change that family's page", () => {
    let state = applyEvent(emptyLiveState, event("plan.recomputed", { patient_id: "P1" }));
    state = applyEvent(state, event("plan.recomputed", { patient_id: "P1" }));
    state = applyEvent(state, event("clock.tick", { patient_id: "P1" }));
    state = applyEvent(state, event("plan.recomputed", { patient_id: null }));
    expect(state.revisions).toEqual({ P1: 2 });
  });

  it("bumps the cohort revision for cohort-level events and runner state", () => {
    let state = applyEvent(emptyLiveState, event("desk.candidate"));
    state = applyEvent(state, event("runner.state"));
    state = applyEvent(state, event("message.rendered", { patient_id: "P1" }));
    expect(state.cohortRevision).toBe(2);
  });

  it("does not mutate the state it was given", () => {
    const before = applyEvent(emptyLiveState, event("plan.recomputed", { patient_id: "P1" }));
    const snapshot = JSON.stringify(before);
    applyEvent(before, event("plan.recomputed", { patient_id: "P1" }));
    expect(JSON.stringify(before)).toBe(snapshot);
  });
});

describe("needsSnapshot", () => {
  it("is true for the events whose news lives on the snapshot", () => {
    for (const kind of ["clock.tick", "runner.state", "world.reset", "metrics.updated"] as const) {
      expect(needsSnapshot(kind)).toBe(true);
    }
    expect(needsSnapshot("message.rendered")).toBe(false);
  });
});

describe("parseEvent", () => {
  it("returns null for a frame that is not JSON", () => {
    expect(parseEvent("not json")).toBeNull();
  });
  it("parses a frame", () => {
    expect(parseEvent(JSON.stringify(event("clock.tick")))?.kind).toBe("clock.tick");
  });
});

describe("the event vocabulary", () => {
  it("is described for every kind the stream can carry", () => {
    // A kind added to the type but not to these tables would render with no
    // tone or label — and, if missing from ALL_KINDS, would never be heard.
    for (const kind of ALL_KINDS) {
      expect(EVENT_TONE[kind], `tone for ${kind}`).toBeDefined();
      expect(EVENT_LABEL[kind], `label for ${kind}`).toBeDefined();
    }
    expect(Object.keys(EVENT_TONE).sort()).toEqual([...ALL_KINDS].sort());
    expect(Object.keys(EVENT_LABEL).sort()).toEqual([...ALL_KINDS].sort());
  });
});
