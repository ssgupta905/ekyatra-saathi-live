import type { ReactElement } from "react";
import { EVENT_LABEL, EVENT_TONE, fmtMs, type WorldEvent } from "@saathi/api-client";
import { Card, Chip } from "../primitives";
import { CheckCircle, Clock, Doc, Question, Shield, Stop, Wave } from "../icons";

/**
 * What just happened.
 *
 * This is the card that makes the rest of the console checkable. Every row is
 * an event the backend emitted while doing something, and the figure on the
 * right is the *measured* wall-clock cost of that work — the planner batch, the
 * Groq render, the chain verification. Nothing here is a progress animation and
 * nothing is a scripted beat; a row appears because code ran.
 */

const GLYPH: Record<string, ReactElement> = {
  "clock.tick": <Clock size={12} />,
  "desk.candidate": <Doc size={12} />,
  "desk.confirmed": <CheckCircle size={12} />,
  "step.released": <CheckCircle size={12} />,
  "plan.recomputed": <Wave size={12} />,
  "message.rendered": <CheckCircle size={12} />,
  "message.held": <Stop size={12} />,
  "inbound.received": <Question size={12} />,
  "guard.blocked": <Shield size={12} />,
  "ledger.appended": <Doc size={12} />,
  "alert.raised": <Clock size={12} />,
  "metrics.updated": <Wave size={12} />,
  "world.reset": <Clock size={12} />,
  "runner.state": <Clock size={12} />,
};

export function ActivityStrip({
  events,
  connected,
  onSelect,
}: {
  events: WorldEvent[];
  connected: boolean;
  onSelect?: (patientId: string) => void;
}) {
  const newest = events[0]?.seq;

  return (
    <Card
      title="What just happened"
      hint={connected ? "live" : "not connected"}
      flush={events.length > 0}
      aside={
        connected ? (
          <Chip tone="go">
            <span className="dot" />
            streaming
          </Chip>
        ) : (
          <Chip tone="critical">
            <span className="dot" />
            stream down
          </Chip>
        )
      }
      note="Every figure on the right is the measured wall-clock cost of the work the row describes — the planner batch, the model call, the chain check. None of it is an animation."
    >
      {events.length === 0 ? (
        <p className="empty">
          Nothing yet. Press play in the header, or step one day, and the world starts
          moving.
        </p>
      ) : (
        <div className="feed">
          {events.map((event) => {
            const tone = EVENT_TONE[event.kind] ?? "neutral";
            const cost = fmtMs(event.duration_ms);
            return (
              <div
                key={event.seq}
                className={`feed-row${event.seq === newest ? " fresh" : ""}`}
              >
                <span className={`tag ${tone}`}>
                  {GLYPH[event.kind]}
                  {EVENT_LABEL[event.kind] ?? event.kind}
                </span>
                <span className="what">
                  {event.patient_id && onSelect ? (
                    <>
                      <button
                        type="button"
                        className="cite"
                        onClick={() => onSelect(event.patient_id!)}
                        title={`Open ${event.patient_id}`}
                      >
                        {event.patient_id}
                      </button>{" "}
                      {stripPatient(event.summary, event.patient_id)}
                    </>
                  ) : (
                    event.summary
                  )}
                </span>
                <span className={cost ? "cost" : "cost none"}>{cost ?? "—"}</span>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

/** The id is already a chip on the row; don't say it twice. */
function stripPatient(summary: string, patientId: string): string {
  return summary
    .replace(new RegExp(`^${patientId}:\\s*`), "")
    .replace(new RegExp(`\\s*for ${patientId}`), "")
    .replace(new RegExp(`\\s*from ${patientId}`), "")
    .replace(new RegExp(`\\s*${patientId}\\s*`), " ")
    .trim();
}
