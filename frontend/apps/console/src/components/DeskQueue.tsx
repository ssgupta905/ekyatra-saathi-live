import { useState } from "react";
import { live, type DeskCandidate } from "@saathi/api-client";
import { stepName, Badge, Card, Chip, CheckCircle, Doc, Spark } from "@saathi/ui-web";

/**
 * The desk queue — the gate every status change has to pass through.
 *
 * A report finishing in the lab is not the same event as a hospital system
 * knowing about it, and conflating the two is how software ends up believing
 * things nobody told it. So the world raises a candidate, a person confirms it,
 * and only then does the step change and the family's plan move.
 *
 * The note is prose because that is what a ward actually sends. The parsed
 * record beside it is what a model made of that prose — shown, not trusted:
 * nothing happens until the button is pressed, and a parse that named an
 * unknown step never got this far.
 */
export function DeskQueue({
  queue,
  onConfirmed,
  onSelect,
}: {
  queue: DeskCandidate[];
  onConfirmed: () => void;
  onSelect?: (patientId: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  const confirm = async (candidate: DeskCandidate) => {
    setBusy(candidate.id);
    try {
      await live.confirm(candidate.id);
      onConfirmed();
    } catch {
      /* the row stays; the queue refetches on the next event either way */
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card
      title="Desk queue"
      hint={queue.length ? `${queue.length} waiting on the desk` : "clear"}
      flush={queue.length > 0}
      note="A report becoming available and the hospital knowing about it are two different events. Nothing moves until someone confirms the record — and if nobody does, it is confirmed automatically after a couple of days and the event stream says so."
    >
      {queue.length === 0 ? (
        <p className="empty">
          Nothing waiting. Releases appear here as the lab finishes them.
        </p>
      ) : (
        queue.map((candidate) => {
          const parsedStatus = String(candidate.parsed.new_status ?? "—").replace(/_/g, " ");
          const mismatch = candidate.parsed.matches_expected === false;
          return (
            <div className="desk-row" key={candidate.id}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
                  {onSelect ? (
                    <button
                      type="button"
                      className="cite"
                      onClick={() => onSelect(candidate.patient_id)}
                    >
                      {candidate.patient_id}
                    </button>
                  ) : (
                    <span className="mono">{candidate.patient_id}</span>
                  )}
                  <span style={{ fontSize: 14, fontWeight: 500 }}>
                    {stepName(candidate.step_kind)}
                  </span>
                </div>

                <div className="desk-note">{candidate.note}</div>

                <div className="desk-meta">
                  <Chip>
                    <Doc size={11} />
                    reads as: {parsedStatus}
                  </Chip>
                  {candidate.drafted_by === "groq" ? (
                    <Chip tone="info">
                      <Spark size={11} />
                      note drafted by the model
                    </Chip>
                  ) : (
                    <Chip>note from the feed</Chip>
                  )}
                  {mismatch && (
                    <Chip tone="critical">
                      <span className="dot" />
                      parse names a different step
                    </Chip>
                  )}
                  <Chip tone="wait">
                    auto-confirms in {candidate.ticks_until_auto} day
                    {candidate.ticks_until_auto === 1 ? "" : "s"}
                  </Chip>
                </div>
              </div>

              <button
                type="button"
                className="btn primary"
                disabled={busy === candidate.id}
                onClick={() => confirm(candidate)}
              >
                {busy === candidate.id ? "Confirming…" : "Confirm record"}
              </button>
            </div>
          );
        })
      )}
      {queue.length > 0 && (
        <div style={{ padding: "12px 20px 2px" }}>
          <Badge tone="neutral" icon={<CheckCircle size={13} />}>
            Confirming is the only thing that releases a report
          </Badge>
        </div>
      )}
    </Card>
  );
}
