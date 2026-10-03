import { useEffect, useState } from "react";
import { fmtMs, type WorkItem, type WorldEvent } from "../lib/live";
import { Spark, Wave } from "../ui/icons";

/**
 * What the system is doing, right now, in one line.
 *
 * A console that reports only finished work looks identical to a broken one
 * while it is busy. This says "looking up the journey from Gaya" *before* the
 * journey is looked up, with a clock that runs — so a navigator can tell a slow
 * re-plan from a dead page, and an audience can see that the pause was work.
 *
 * When nothing is in flight it falls back to the last fact a tool fetched,
 * because the honest resting state of this system is not "idle" but "here is
 * where the last number came from".
 */
export function AgentStatus({
  working,
  events,
}: {
  working: WorkItem[];
  events: WorldEvent[];
}) {
  const [, tick] = useState(0);
  const busy = working.length > 0;

  // A running clock only while something is running; no timer when idle.
  useEffect(() => {
    if (!busy) return;
    const id = window.setInterval(() => tick((n) => n + 1), 200);
    return () => window.clearInterval(id);
  }, [busy]);

  const current = working[working.length - 1] ?? null;
  const lastTool = events.find((event) => event.kind === "tool.called") ?? null;

  if (!current && !lastTool) return null;

  return (
    <div className={busy ? "agent-status busy" : "agent-status"}>
      <span className="as-glyph">{busy ? <Spark size={13} /> : <Wave size={13} />}</span>
      {current ? (
        <>
          <span className="as-task">{current.task}</span>
          {current.detail && <span className="as-detail">{current.detail}</span>}
          <span className="as-clock mono">
            {fmtMs(Date.now() - current.startedAt)}
          </span>
          {working.length > 1 && (
            <span className="as-more">+{working.length - 1} more</span>
          )}
        </>
      ) : (
        <>
          <span className="as-task">{lastTool?.summary}</span>
          <span className="as-detail">
            {String(lastTool?.payload.tool ?? "")} ·{" "}
            {String(lastTool?.payload.provider ?? "")}
          </span>
          <span className="as-clock mono">{fmtMs(lastTool?.duration_ms)}</span>
        </>
      )}
    </div>
  );
}
