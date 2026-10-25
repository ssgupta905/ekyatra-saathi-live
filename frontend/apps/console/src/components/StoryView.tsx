import { useMemo } from "react";
import { type StoryLane, type Story, EVENT_LABEL, fmtMs, type WorldEvent } from "@saathi/api-client";
import { Card, Chip } from "@saathi/ui-web";

/**
 * The brief's Figure 5, drawn from what actually happened.
 *
 * Four lanes — the desk, the agent layer, whoever decides, and the family — and
 * one numbered dot per real event, in the order they occurred, joined by a line
 * that zigzags between the lanes. The shape *is* the argument: a disruption
 * enters at the desk, the family is reached before anything else happens, the
 * agents work, one person decides, and the family confirms. If the line ever
 * reaches the family *after* the decision rather than before it, the picture
 * shows it immediately.
 *
 * Nothing here is drawn in advance. Every dot is an event the backend emitted,
 * carrying the measured cost of the work behind it, and clicking one opens that
 * record. A story that has not been advanced yet has an empty diagram, which is
 * the honest state.
 */

const LANES: { id: StoryLane; label: string }[] = [
  { id: "desk", label: "Hospital desk" },
  { id: "agents", label: "Saathi agents" },
  { id: "decision", label: "Navigator · doctor" },
  { id: "family", label: "Family" },
];

/** Which lane an event belongs in. The one place event kinds meet the diagram. */
const LANE_OF: Record<string, StoryLane> = {
  "disruption.raised": "desk",
  "desk.candidate": "desk",
  "desk.confirmed": "desk",
  "step.released": "desk",
  "holding_message.sent": "family",
  "inbound.received": "family",
  "confirmation.received": "family",
  "message.rendered": "family",
  "message.held": "agents",
  "process.answered": "agents",
  "plan.recomputed": "agents",
  "options.ready": "agents",
  "ledger.appended": "agents",
  "guard.blocked": "agents",
  "tool.called": "agents",
  "approval.recorded": "decision",
};

const LANE_INDEX = new Map(LANES.map((lane, index) => [lane.id, index]));

const ROW_HEIGHT = 56;
const LEFT_GUTTER = 132;
const DOT_SPACING = 58;
const DOT_RADIUS = 13;

export function StoryView({
  story,
  events,
  onOpenEvent,
}: {
  story: Story;
  events: WorldEvent[];
  onOpenEvent?: (event: WorldEvent) => void;
}) {
  /** Oldest first, and only what belongs to this story's family. */
  const beats = useMemo(() => {
    return events
      .filter((event) => {
        const lane = LANE_OF[event.kind];
        if (!lane) return false;
        // Cohort-wide events (a disruption hits many families) stay in; a
        // different family's plan run does not.
        if (event.patient_id && event.patient_id !== story.patient_id) return false;
        return true;
      })
      .slice()
      .reverse();
  }, [events, story.patient_id]);

  const width = Math.max(720, LEFT_GUTTER + beats.length * DOT_SPACING + 40);
  const height = LANES.length * ROW_HEIGHT + 24;

  const points = beats.map((event, index) => ({
    event,
    x: LEFT_GUTTER + index * DOT_SPACING,
    y: 20 + (LANE_INDEX.get(LANE_OF[event.kind]) ?? 1) * ROW_HEIGHT + ROW_HEIGHT / 2,
  }));

  return (
    <Card
      title={story.title}
      hint={story.who}
      aside={
        <Chip tone={story.done ? "go" : "info"}>
          {story.done ? "story complete" : `beat ${story.index} of ${story.total}`}
        </Chip>
      }
      flush
      note="Each dot is something that happened, in the order it happened. The line crossing from the desk down to the family before it reaches the navigator is the promise this system makes: the family hears first, and a person decides afterwards."
    >
      {points.length === 0 ? (
        <p className="empty" style={{ padding: "0 20px 16px" }}>
          Nothing has happened yet. Press <strong>Advance</strong> to start the story.
        </p>
      ) : (
        <div className="story-scroll">
          <svg
            className="story-lanes"
            width={width}
            height={height}
            role="img"
            aria-label={`${story.title}: ${points.length} events across four lanes`}
          >
            {LANES.map((lane, index) => {
              const y = 20 + index * ROW_HEIGHT;
              return (
                <g key={lane.id}>
                  <rect
                    x={0}
                    y={y}
                    width={width}
                    height={ROW_HEIGHT}
                    className={index % 2 === 0 ? "lane even" : "lane odd"}
                  />
                  <text x={16} y={y + ROW_HEIGHT / 2 + 4} className="lane-label">
                    {lane.label}
                  </text>
                  <line
                    x1={LEFT_GUTTER - 18}
                    y1={y + ROW_HEIGHT / 2}
                    x2={width - 16}
                    y2={y + ROW_HEIGHT / 2}
                    className="lane-rule"
                  />
                </g>
              );
            })}

            {/* The path between consecutive events: the shape of the loop. */}
            <polyline
              className="story-path"
              points={points.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
            />

            {points.map((point, index) => (
              <g
                key={point.event.seq}
                className="story-dot"
                onClick={() => onOpenEvent?.(point.event)}
                role={onOpenEvent ? "button" : undefined}
                tabIndex={onOpenEvent ? 0 : undefined}
                onKeyDown={(e) => {
                  if (onOpenEvent && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onOpenEvent(point.event);
                  }
                }}
              >
                <title>
                  {`${EVENT_LABEL[point.event.kind] ?? point.event.kind} — ${point.event.summary}` +
                    (point.event.duration_ms ? ` · ${fmtMs(point.event.duration_ms)}` : "")}
                </title>
                <circle cx={point.x} cy={point.y} r={DOT_RADIUS} className="dot-face" />
                <text x={point.x} y={point.y + 4} className="dot-number">
                  {index + 1}
                </text>
              </g>
            ))}
          </svg>
        </div>
      )}

      {points.length > 0 && (
        <ol className="story-legend">
          {points.map((point, index) => (
            <li key={point.event.seq}>
              <button
                type="button"
                className="story-legend-row"
                onClick={() => onOpenEvent?.(point.event)}
              >
                <span className="n">{index + 1}</span>
                <span className="lane-tag">{EVENT_LABEL[point.event.kind] ?? point.event.kind}</span>
                <span className="what">{point.event.summary}</span>
                <span className="cost mono">
                  {fmtMs(point.event.duration_ms) ?? ""}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
