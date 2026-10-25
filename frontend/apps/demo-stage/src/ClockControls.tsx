import { useState } from "react";
import { live, type LiveSnapshot } from "@saathi/api-client";
import { Pause, Play, Rewind, StepForward } from "@saathi/ui-web";

/**
 * The demo's control of time: play, pause, one day, and start over.
 *
 * It compresses time and nothing else — the rest of the system has no idea it is
 * being run fast. These exist only on the stage. No role's app has them, because
 * in a real hospital nobody can make a Tuesday arrive sooner.
 */
export function ClockControls({ snapshot }: { snapshot: LiveSnapshot | null }) {
  const [busy, setBusy] = useState(false);
  if (!snapshot) return null;

  const run = async (action: "play" | "pause" | "step" | "reset") => {
    setBusy(true);
    try {
      await live.control(action);
    } finally {
      setBusy(false);
    }
  };

  const running = snapshot.running;

  return (
    <>
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
      <button
        type="button"
        className="btn round"
        disabled={busy}
        onClick={() => run("reset")}
        aria-label="Reset the world"
        title="Reset the world to its first morning"
      >
        <Rewind />
      </button>
    </>
  );
}
