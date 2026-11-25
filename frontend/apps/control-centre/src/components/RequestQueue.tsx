import { useCallback, useEffect, useState } from "react";
import {
  requests as requestsApi,
  type QuestionWaiting,
  type RequestWaiting,
} from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { SkeletonRows, useToast } from "../ui/kit";

/**
 * What a family asked for, as something a person agrees with before it moves anything.
 *
 * The screen exists because of one rule, and the whole design follows from it:
 * **the planner never sees a reading a person has not confirmed.** A language
 * model read the family's own words, and mishearing "after the 20th" as "on
 * the 20th" sends somebody several hundred kilometres for nothing. So the
 * family's message is shown verbatim, next to what the system made of it, and
 * the navigator agrees or corrects.
 *
 * Three deliberate choices a reader might otherwise take for granted:
 *
 * **Rejecting is a button, not an escape hatch.** A navigator who reads the
 * message and sees the extractor got it wrong has done the most valuable thing
 * in this loop. If the only way to disagree were to ignore the row, the system
 * would never learn it was wrong, and nobody would be able to tell a model
 * that mishears dates from one that was never run.
 *
 * **A figure is shown attributed or not at all.** `travel` arrives absent —
 * not null — when the family's own sentence is missing, because a rupee amount
 * with nothing behind it is indistinguishable from one this system invented.
 * This screen is the last place that distinction could be blurred, so it
 * states who said it.
 *
 * **Open questions sit underneath.** A family who was asked something and
 * never replied appears nowhere else in the product. They are the likeliest to
 * turn up on the wrong day, or not at all, and a queue showing only answers
 * hides exactly them.
 */
export function RequestQueue({
  revision,
  onSelect,
}: {
  revision: number;
  /** Open this family's working beside the queue. A navigator deciding
   *  whether a reading is right wants the evidence behind it, and until this
   *  existed the only way to reach it was through a different screen. */
  onSelect?: (patientId: string) => void;
}) {
  const [rows, setRows] = useState<RequestWaiting[] | null>(null);
  const [questions, setQuestions] = useState<QuestionWaiting[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const load = useCallback(() => {
    requestsApi
      .waiting()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
    // A failure here empties the list rather than breaking the screen: the
    // readings above are the actionable half, and losing the questions pane
    // must not take them with it.
    requestsApi.questions().then(setQuestions).catch(() => setQuestions([]));
  }, []);

  useEffect(load, [load, revision]);

  const confirm = async (row: RequestWaiting) => {
    setBusy(row.id);
    try {
      const { decision } = await requestsApi.confirm(row.patient_id, row.id);
      toast(
        decision
          ? `Agreed for ${row.name}. The plan now says ${decision}.`
          : `Agreed for ${row.name}.`,
      );
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not confirm");
    } finally {
      setBusy(null);
    }
  };

  const reject = async (row: RequestWaiting) => {
    if (!reason.trim()) return;
    setBusy(row.id);
    try {
      await requestsApi.reject(row.patient_id, row.id, reason.trim());
      toast(`Recorded that this reading was wrong for ${row.name}. No plan changed.`);
      setRejecting(null);
      setReason("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not record that");
    } finally {
      setBusy(null);
    }
  };

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (rows === null) return <SkeletonRows rows={2} />;

  return (
    <div className="stack">
      <Card
        title="What families have asked for"
        hint="Read their own words first. Nothing moves until you agree."
      >
        {rows.length === 0 ? (
          <p className="muted">Nobody is waiting on you.</p>
        ) : (
          <ul className="queue">
            {rows.map((row) => (
              <li key={row.id} className="queue-row">
                <div className="queue-head">
                  {onSelect ? (
                    <button
                      type="button"
                      className="linklike"
                      onClick={() => onSelect(row.patient_id)}
                    >
                      {row.name}
                    </button>
                  ) : (
                    <strong>{row.name}</strong>
                  )}
                  <Chip tone={row.needs_a_person ? "uncertain" : "info"}>
                    {row.needs_a_person ? "needs a person" : row.intent.replace("_", " ")}
                  </Chip>
                  {row.confidence === "low" && (
                    <Chip tone="uncertain">read with low confidence — check it</Chip>
                  )}
                </div>

                {/* Their words, then ours. In that order, deliberately: a
                    navigator who reads the summary first reads the message
                    looking for agreement with it. */}
                <blockquote className="said">{row.raw_text}</blockquote>
                {row.gloss && <p className="muted gloss">{row.gloss}</p>}

                <p className="reading">{row.summary}</p>

                <Window constraint={row.constraint} />
                {row.travel && <Travel travel={row.travel} />}

                {rejecting === row.id ? (
                  <div className="queue-actions">
                    <input
                      autoFocus
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      placeholder="What did they actually say?"
                      aria-label="What did they actually say?"
                    />
                    <button
                      type="button"
                      disabled={busy === row.id || !reason.trim()}
                      onClick={() => reject(row)}
                    >
                      Record the correction
                    </button>
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => {
                        setRejecting(null);
                        setReason("");
                      }}
                    >
                      Back
                    </button>
                  </div>
                ) : (
                  <div className="queue-actions">
                    <button
                      type="button"
                      disabled={busy === row.id}
                      onClick={() => confirm(row)}
                    >
                      {row.needs_a_person
                        ? "Agree — and I will call them"
                        : "Agree, and re-plan"}
                    </button>
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => setRejecting(row.id)}
                    >
                      This is not what they said
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title="Asked, and no answer yet"
        hint="A family nobody has heard from is visible nowhere else."
      >
        {questions.length === 0 ? (
          <p className="muted">No question is waiting on a family.</p>
        ) : (
          <ul className="queue">
            {questions.map((question) => (
              <li key={question.id} className="queue-row">
                <div className="queue-head">
                  <strong>{question.name}</strong>
                  <Chip tone="info">{question.reason.replace("_", " ")}</Chip>
                  {question.topics.map((topic) => (
                    <Chip key={topic}>{topic}</Chip>
                  ))}
                </div>
                {/* What was actually sent, in their script. A navigator
                    following up on the phone needs to know what they were
                    already asked, or they ask it again. */}
                <blockquote className="said">{question.asked_text}</blockquote>
                <p className="muted">
                  Sent {new Date(question.asked_at).toLocaleString()} · about{" "}
                  {question.about_day}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

/** The dates the family can and cannot manage, when they named any. */
function Window({ constraint }: { constraint: RequestWaiting["constraint"] }) {
  const parts: string[] = [];
  if (constraint.not_before) parts.push(`not before ${constraint.not_before}`);
  if (constraint.not_after) parts.push(`not after ${constraint.not_after}`);
  if (constraint.excluded_dates.length)
    parts.push(`not on ${constraint.excluded_dates.join(", ")}`);
  if (!parts.length && !constraint.reason) return null;
  return (
    <p className="window">
      {parts.join(" · ")}
      {constraint.reason && <span className="muted"> — {constraint.reason}</span>}
    </p>
  );
}

/**
 * What the family said about getting there.
 *
 * Every figure here is attributed out loud. "They said ₹900" is a fact about
 * the family; "₹900" on its own would read as the hospital's estimate, and
 * this system has no fare source and must never appear to.
 */
function Travel({ travel }: { travel: NonNullable<RequestWaiting["travel"]> }) {
  const facts: string[] = [];
  if (travel.companions !== null)
    facts.push(
      travel.companions === 0
        ? "travelling alone"
        : `${travel.companions} coming with them`,
    );
  if (travel.single_day_trip !== null)
    facts.push(travel.single_day_trip ? "can return the same day" : "needs a night");
  if (travel.stated_cost_inr !== null)
    facts.push(`they said about ₹${travel.stated_cost_inr}`);
  if (travel.refundable !== null)
    facts.push(
      travel.refundable
        ? "their booking can be changed"
        : "their booking cannot be changed",
    );
  if (!facts.length) return null;
  return (
    <div className="travel">
      <p>{facts.join(" · ")}</p>
      <p className="muted attribution">in their words: “{travel.stated_in}”</p>
    </div>
  );
}
