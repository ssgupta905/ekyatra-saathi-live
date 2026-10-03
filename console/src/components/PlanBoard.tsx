import { useMemo } from "react";
import type { BoardNode, PlanBoard as Board } from "../lib/api";
import { fmtDate, fmtWhen, statusLabel, statusTone } from "../lib/format";
import { fmtMs } from "../lib/live";
import { Badge, Card, Chip, DecisionGlyph } from "../ui/primitives";
import { CheckCircle, Clock, Doc, Pin } from "../ui/icons";

/**
 * One patient's pathway, drawn as the branching thing it is.
 *
 * A navigator holding thirty families needs to see *what is waiting on what*.
 * A list sorted by date hides exactly that: it puts the pending radiology report
 * next to the consult it is holding up and gives no hint that one is the reason
 * for the other. Columns are depth through the dependency graph, so reading
 * left to right is reading the order care actually happens in, and the step
 * everything converges on is the one the family would travel for.
 *
 * The layout comes from the backend. Depth is a property of the care pathway,
 * and a console that computed it would be a second copy of the hospital's model
 * of care, drifting quietly out of step with the first.
 */

const glyphFor = (node: BoardNode) => {
  if (node.satisfied) return <CheckCircle size={14} />;
  if (node.status === "pending_result") return <Clock size={14} />;
  return node.no_journey ? <Doc size={14} /> : <Pin size={14} />;
};

function BoardStep({ node }: { node: BoardNode }) {
  const tone = statusTone(node.status);
  const when = node.scheduled_for ?? node.result_available_on ?? node.completed_on;

  const classes = [
    "board-step",
    node.satisfied ? "done" : "",
    node.is_blocking ? "blocking" : "",
    node.is_target ? "target" : "",
    node.no_journey ? "no-journey" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes}>
      <div className="bs-head">
        <span className={`bs-glyph ${tone}`}>{glyphFor(node)}</span>
        <span className="bs-label">{node.label}</span>
      </div>
      <div className="bs-when">
        {when ? `${fmtDate(when)} · ${fmtWhen(when)}` : "no date on record"}
      </div>
      <div className="bs-tags">
        <Chip tone={tone === "critical" ? "critical" : tone === "go" ? "go" : tone === "wait" ? "wait" : undefined}>
          {statusLabel(node.status)}
        </Chip>
        {node.is_target && <Chip tone="info">the visit being decided</Chip>}
        {node.is_blocking && !node.satisfied && <Chip tone="wait">in the way</Chip>}
        {node.no_journey && <Chip>no journey</Chip>}
        {node.resource_id && <Chip>{node.resource_id}</Chip>}
      </div>
    </div>
  );
}

export function PlanBoard({ board, compact }: { board: Board; compact?: boolean }) {
  const columns = useMemo(() => {
    const grouped: BoardNode[][] = Array.from({ length: board.columns }, () => []);
    for (const node of board.nodes) grouped[node.column]?.push(node);
    return grouped;
  }, [board]);

  const decision = board.decision;

  return (
    <Card
      title={`${board.patient.id} · ${board.patient.district}`}
      hint={`${board.patient.distance_km} km away`}
      aside={
        decision ? (
          <Badge
            tone={decision === "go" ? "go" : decision === "wait" ? "wait" : "uncertain"}
            icon={<DecisionGlyph decision={decision} size={13} />}
          >
            {decision === "go" && board.travel_on
              ? `Travel ${fmtDate(board.travel_on)}`
              : decision.toUpperCase()}
          </Badge>
        ) : undefined
      }
      flush
      note={
        compact
          ? undefined
          : "Columns are depth through the care pathway, so left to right is the order things actually happen in. A step is in the way when something the family would travel for is waiting on it."
      }
    >
      <div className="board-scroll">
        {/* A floor, not a fixed width. Five columns at 168px overflowed the
            pane by 29px inside the stage's laptop frame, which clipped the
            rightmost step — the one the family would actually travel for. */}
        <div
          className="board-columns"
          style={{ gridTemplateColumns: `repeat(${board.columns}, minmax(148px, 1fr))` }}
        >
          {columns.map((group, index) => (
            <div className="board-column" key={index}>
              {group.map((node) => (
                <BoardStep node={node} key={node.id} />
              ))}
            </div>
          ))}
        </div>
      </div>

      {board.waiting_on.length > 0 && (
        <div className="board-waiting">
          <span className="bw-label">Waiting on</span>
          {board.waiting_on.map((wait) => (
            <span className="bw-item" key={wait.step_id}>
              <strong>{wait.label}</strong>
              {wait.earliest && wait.latest ? (
                wait.from_booking ? (
                  <> · booked for {fmtDate(wait.earliest)}</>
                ) : (
                  <>
                    {" "}
                    · expected {fmtDate(wait.earliest)} – {fmtDate(wait.latest)}
                  </>
                )
              ) : (
                <> · no date Saathi can stand behind</>
              )}
            </span>
          ))}
        </div>
      )}

      {!compact && board.computed_at && (
        <div className="board-stamp">
          {board.rationale}
          {board.plan_ms != null && <span className="mono"> · planner {fmtMs(board.plan_ms)}</span>}
        </div>
      )}
    </Card>
  );
}
