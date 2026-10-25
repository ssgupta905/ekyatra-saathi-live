import { useState } from "react";
import { disruptions, type DisruptionKind, type WorkLogReading } from "@saathi/api-client";
import { Card, Chip, Notice, Spark } from "@saathi/ui-web";

/**
 * How a desk says something went wrong.
 *
 * It used to be a form: pick a resource from a list, pick a kind, type a number
 * of days. That is the shape of the record, not the shape of the thought. A
 * radiology desk at 7:40 in the morning thinks "MRI-2 down till Saturday" and
 * writes exactly that into a log it already keeps — so this takes that line.
 *
 * The reading is a proposal and is drawn as one. Nothing is raised until the
 * desk confirms what was understood, which is invariant 3 holding in the place
 * it is easiest to lose: the model supplies a reading, a person supplies the
 * decision. Low confidence is said loudly rather than buried, because the
 * cheapest moment to catch a misread is before anybody is told not to travel.
 *
 * Every field stays editable. A reading that got the end date wrong should cost
 * a correction, not a retyped sentence.
 */

const KIND_WORDS: Record<DisruptionKind, string> = {
  machine_down: "machine down",
  staff_unavailable: "person away",
  stock_delay: "stock late",
};

const EXAMPLES = [
  "MRI-2 down till Saturday, no scans on it",
  "Echo cardiologist on emergency leave this week",
  "Contrast stock did not arrive, day care short for 2 days",
];

export function IssueReporter({ onReported }: { onReported: (affected: string[]) => void }) {
  const [text, setText] = useState("");
  const [reading, setReading] = useState<WorkLogReading | null>(null);
  const [busy, setBusy] = useState<"reading" | "raising" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string[] | null>(null);

  const read = async () => {
    if (!text.trim()) return;
    setBusy("reading");
    setError(null);
    setDone(null);
    try {
      const result = await disruptions.read(text);
      setReading(result);
      if (!result.understood) setError(result.reason ?? "could not read that line");
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not read that line");
    } finally {
      setBusy(null);
    }
  };

  const raise = async () => {
    if (!reading?.understood) return;
    setBusy("raising");
    setError(null);
    try {
      const result = await disruptions.raise({
        resource_id: reading.resource_id!,
        kind: reading.kind as DisruptionKind,
        unavailable_from: reading.unavailable_from!,
        unavailable_to: reading.unavailable_to,
        note: reading.note ?? text,
      });
      setDone(result.affected_patient_ids);
      onReported(result.affected_patient_ids);
      setReading(null);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not report that");
    } finally {
      setBusy(null);
    }
  };

  const edit = (patch: Partial<WorkLogReading>) =>
    setReading((previous) => (previous ? { ...previous, ...patch } : previous));

  return (
    <Card
      title="What happened?"
      hint="type it the way you would write it in the log"
      note="Nothing is reported until you confirm what was understood. The reading is a proposal; the decision is yours."
    >
      <div className="iss-entry">
        <textarea
          className="iss-text"
          rows={2}
          value={text}
          placeholder="e.g. MRI-2 down till Saturday, no scans on it"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) read();
          }}
        />
        <button
          type="button"
          className="btn primary"
          onClick={read}
          disabled={busy !== null || !text.trim()}
        >
          {busy === "reading" ? <Spark size={14} /> : "Read it"}
        </button>
      </div>

      {!reading && !done && (
        <div className="iss-examples">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" onClick={() => setText(example)}>
              {example}
            </button>
          ))}
        </div>
      )}

      {error && <Notice tone="warn">{error}</Notice>}

      {reading?.understood && (
        <div className={`iss-reading ${reading.confidence}`}>
          <div className="iss-read-as">
            <Chip tone={reading.confidence === "high" ? "go" : "wait"}>
              {reading.confidence === "high" ? "read clearly" : `${reading.confidence} confidence`}
            </Chip>
            <span>{reading.read_as}</span>
          </div>

          {reading.confidence !== "high" && (
            <Notice tone="warn">
              Check this before confirming. A misread here is the cheapest mistake
              to catch and the most expensive to miss.
            </Notice>
          )}

          <div className="iss-fields">
            <label>
              Resource
              <input value={reading.resource_name ?? ""} readOnly />
            </label>
            <label>
              Kind
              <select
                value={reading.kind}
                onChange={(event) => edit({ kind: event.target.value })}
              >
                {Object.entries(KIND_WORDS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              From
              <input
                type="date"
                value={reading.unavailable_from ?? ""}
                onChange={(event) => edit({ unavailable_from: event.target.value })}
              />
            </label>
            <label>
              Until
              <input
                type="date"
                value={reading.unavailable_to ?? ""}
                onChange={(event) => edit({ unavailable_to: event.target.value || null })}
              />
            </label>
          </div>

          <div className="iss-actions">
            <button type="button" className="btn primary" onClick={raise} disabled={busy !== null}>
              {busy === "raising" ? "reporting…" : "Confirm and report"}
            </button>
            <button type="button" className="btn" onClick={() => setReading(null)}>
              Cancel
            </button>
            <span className="hint mono">{reading.read_by}</span>
          </div>
        </div>
      )}

      {done && (
        <Notice tone="calm">
          Reported. {done.length} famil{done.length === 1 ? "y was" : "ies were"} affected
          {done.length > 0 && <> — {done.join(", ")}</>}. Each was told not to travel
          before any new date was worked out.
        </Notice>
      )}
    </Card>
  );
}
