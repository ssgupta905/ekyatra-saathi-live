import { useState } from "react";
import { live, type LiveSnapshot } from "@saathi/api-client";
import { fmtDate, Pause, Play, StepForward } from "@saathi/ui-web";

/**
 * The clock, in the chrome where it cannot scroll out of sight.
 *
 * It compresses time and nothing else: the rest of the system has no idea it is
 * being run fast. The pulse says whether the world is moving and whether the
 * console is still connected to it — a frozen page and a paused world look
 * identical otherwise, and only one of them is fine.
 */
export function ClockBar({
  snapshot,
  connected,
}: {
  snapshot: LiveSnapshot | null;
  connected: boolean;
}) {
  const [busy, setBusy] = useState(false);

  if (!snapshot) {
    return (
      <span className="clock">
        <span className="pulse off" />
        <span className="when">
          <span className="date">connecting…</span>
          <span className="day">live world</span>
        </span>
      </span>
    );
  }

  const run = async (action: "play" | "pause" | "step") => {
    setBusy(true);
    try {
      await live.control(action);
    } finally {
      setBusy(false);
    }
  };

  const running = snapshot.running;
  const pulse = !connected ? "lost" : running ? "on" : "off";

  return (
    <span className="clock">
      <span
        className={`pulse ${pulse}`}
        title={
          !connected
            ? "not receiving events"
            : running
              ? `running · one day every ${snapshot.seconds_per_day}s`
              : "paused"
        }
      />
      <span className="when">
        <span className="date">{fmtDate(snapshot.current)}</span>
        <span className="day">
          day {snapshot.day} · {snapshot.pending_reports} reports pending
        </span>
      </span>
      <button
        type="button"
        className="btn round"
        disabled={busy}
        onClick={() => run(running ? "pause" : "play")}
        aria-label={running ? "Pause the world" : "Start the world"}
        title={running ? "Pause" : "Play"}
      >
        {running ? <Pause /> : <Play />}
      </button>
      <button
        type="button"
        className="btn round"
        disabled={busy || running}
        onClick={() => run("step")}
        aria-label="Advance one day"
        title="Advance one day"
      >
        <StepForward />
      </button>
    </span>
  );
}
