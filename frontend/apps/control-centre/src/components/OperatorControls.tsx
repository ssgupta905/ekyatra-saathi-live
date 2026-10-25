import { useState } from "react";
import { live, type LiveSnapshot, type Patient } from "@saathi/api-client";
import { Card, Chip, Notice, Pause, Play, Rewind, Spark, StepForward } from "@saathi/ui-web";

/**
 * The controls a person running the demo actually needs.
 *
 * Every button here supplies an *input* and then gets out of the way. Nothing
 * sets a decision, nothing stages an outcome: injecting a question runs the
 * real guard, and stepping a day runs the real planner over the whole cohort.
 * If the system did something interesting afterwards, it did it on its own.
 */

const SPEEDS = [
  { label: "slow · 8s a day", value: 8 },
  { label: "steady · 4s a day", value: 4 },
  { label: "quick · 2s a day", value: 2 },
  { label: "fast · 1s a day", value: 1 },
];

export function OperatorControls({
  snapshot,
  patients,
  onChange,
}: {
  snapshot: LiveSnapshot | null;
  patients: Patient[];
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<string>("");
  const [note, setNote] = useState<string | null>(null);

  const watched = snapshot?.watched ?? [];
  const chosen =
    target || watched[0] || patients[0]?.id || "";

  const run = async (fn: () => Promise<unknown>, said?: string) => {
    setBusy(true);
    setNote(null);
    try {
      await fn();
      if (said) setNote(said);
      onChange();
    } catch (error) {
      setNote(error instanceof Error ? error.message : "that did not work");
    } finally {
      setBusy(false);
    }
  };

  const running = snapshot?.running ?? false;

  return (
    <Card
      title="Run the world"
      hint={snapshot ? `one day every ${snapshot.seconds_per_day}s` : undefined}
      note="Each of these supplies an input and stops there. What follows — re-planning, rendering, guarding, rescoring — happens because the system reacted to it, not because a button said so."
    >
      <div className="ops">
        <div className="ops-group">
          <span className="ops-label">Clock</span>
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            onClick={() => run(() => live.control(running ? "pause" : "play"))}
          >
            <span style={{ display: "inline-flex", verticalAlign: "-2px", marginRight: 6 }}>
              {running ? <Pause /> : <Play />}
            </span>
            {running ? "Pause" : "Play"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy || running}
            onClick={() => run(() => live.control("step"))}
          >
            <span style={{ display: "inline-flex", verticalAlign: "-2px", marginRight: 6 }}>
              <StepForward />
            </span>
            One day
          </button>
          <select
            value={snapshot?.seconds_per_day ?? 4}
            disabled={busy}
            onChange={(event) =>
              run(() => live.control("speed", Number(event.target.value)))
            }
            aria-label="Simulation speed"
          >
            {SPEEDS.map((speed) => (
              <option key={speed.value} value={speed.value}>
                {speed.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => run(() => live.control("reset"), "World rebuilt from the same seed.")}
          >
            <span style={{ display: "inline-flex", verticalAlign: "-2px", marginRight: 6 }}>
              <Rewind />
            </span>
            Reset
          </button>
        </div>

        <div className="ops-group">
          <span className="ops-label">A family writes</span>
          <select
            value={chosen}
            disabled={busy}
            onChange={(event) => setTarget(event.target.value)}
            aria-label="Which family"
          >
            {(watched.length ? watched : patients.map((p) => p.id)).map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn"
            disabled={busy || !chosen}
            onClick={() =>
              run(
                () => live.inject(chosen, "clinical_question"),
                "Sent through the real guard.",
              )
            }
          >
            <span style={{ display: "inline-flex", verticalAlign: "-2px", marginRight: 6 }}>
              <Spark />
            </span>
            …a clinical question
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy || !chosen}
            onClick={() =>
              run(
                () => live.inject(chosen, "logistics_question"),
                "Sent through the real guard.",
              )
            }
          >
            …about the journey
          </button>
        </div>

        {snapshot && !snapshot.actors_enabled && (
          <Notice tone="calm">
            <strong>Actors are off.</strong> Without <span className="mono">GROQ_API_KEY</span>{" "}
            nothing writes a family's words for them, so the inject buttons have nothing
            to send. The clock, the planner, the guard and the ledger all still run — that
            is the configuration CI uses.
          </Notice>
        )}

        {note && (
          <div>
            <Chip tone="info">{note}</Chip>
          </div>
        )}

        {snapshot && (
          <div className="ops-group">
            <span className="ops-label">This run</span>
            {Object.entries(snapshot.counters).map(([key, value]) => (
              <Chip key={key}>
                {key.replace(/_/g, " ")}: {value}
              </Chip>
            ))}
            <Chip>{snapshot.language_layer ?? "language layer off"}</Chip>
            <Chip>watching {snapshot.watched.length} families closely</Chip>
          </div>
        )}
      </div>
    </Card>
  );
}
