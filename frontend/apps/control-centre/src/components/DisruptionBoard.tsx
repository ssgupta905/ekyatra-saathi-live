import { useCallback, useEffect, useMemo, useState } from "react";
import {
  requests as requestsApi,
  disruptions as disruptionsApi,
  type PendingOption,
  type QuestionWaiting,
  type RequestWaiting,
} from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { SkeletonRows } from "../ui/kit";
import { ReasoningLog } from "./ReasoningLog";
import { PlannerSearch } from "./PlannerSearch";

/**
 * One thing that happened, and every family it landed on.
 *
 * The Console used to answer "why is this family's plan what it is?" one
 * family at a time, behind a drawer somebody had to think to open. That is the
 * wrong first question. A clinician marking themselves away does not disrupt a
 * patient, it disrupts a *day* — and the thing a navigator needs to see is all
 * of it at once: who it hit, how differently it hit them, and what the system
 * has done about each so far.
 *
 * So the grouping is the disruption, not the person. Families are grouped by
 * what they were asked about and when, because that is the only honest join
 * available: a leave never becomes a `Disruption` record (see
 * `hospital_sync._act_on_leave`), so there is no id to group on. Grouping on
 * the question is grouping on the observable fact that these families were all
 * asked the same thing about the same day.
 *
 * **Different is the point.** The columns are chosen to make families look
 * unlike each other — distance, language, what stage they are at — because the
 * claim being demonstrated is that one event produces different right answers
 * for different households, and a board where every row looks the same
 * demonstrates nothing.
 *
 * Expanding a row shows the agent's own trace and the dates it tried, inline.
 * Not a drawer: a drawer is a thing a reader has to decide to open, and the
 * refusals are the most persuasive evidence here.
 */

const WHY_ASKED: Record<QuestionWaiting["reason"], string> = {
  doctor_away: "A clinician is away",
  report_pending: "A report is not back",
  clinic_behind: "The clinic is running behind",
  slot_changed: "The hospital moved a slot",
  // Not a disruption at all: our own turn, waiting on the family rather than
  // on the hospital. It belongs on this board because a navigator asking
  // "what is outstanding?" needs it, and giving it the same heading as a
  // clinician's absence would misdescribe who is being waited on.
  plan_proposed: "Saathi has put a date to the family",
};

/** Where a family has got to. Ordered: each stage implies the ones before it. */
type Stage = "asked" | "replied" | "agreed" | "proposed" | "options" | "settled";

const STAGE_SAYS: Record<Stage, string> = {
  asked: "asked, no reply yet",
  replied: "replied — a person must agree with the reading",
  agreed: "reading agreed, planner searching",
  proposed: "a day put to them — waiting on their answer",
  options: "dates offered, waiting on a decision",
  settled: "decided",
};

const STAGE_TONE: Record<Stage, "wait" | "info" | "go"> = {
  asked: "wait",
  replied: "wait",
  agreed: "info",
  proposed: "info",
  options: "info",
  settled: "go",
};

interface Row {
  patientId: string;
  name: string;
  language: string;
  stage: Stage;
  said: string;
  askedText: string;
}

interface Group {
  key: string;
  reason: QuestionWaiting["reason"];
  day: string;
  rows: Row[];
}

function groupsFrom(
  questions: QuestionWaiting[],
  readings: RequestWaiting[],
  pending: PendingOption[],
): Group[] {
  const replied = new Map(readings.map((r) => [r.patient_id, r]));
  const offered = new Set(pending.map((p) => p.patient_id));
  const byKey = new Map<string, Group>();

  for (const question of questions) {
    const key = `${question.reason}:${question.about_day}`;
    const group =
      byKey.get(key) ??
      ({ key, reason: question.reason, day: question.about_day, rows: [] } as Group);

    const reading = replied.get(question.patient_id);
    // Read in the order a day actually moves, so a family who has reached the
    // far end is never shown at the near one.
    const stage: Stage = offered.has(question.patient_id)
      ? "options"
      : question.reason === "plan_proposed"
        ? "proposed"
        : reading
          ? "replied"
          : "asked";

    group.rows.push({
      patientId: question.patient_id,
      name: question.name,
      language: question.language,
      stage,
      said: reading?.raw_text ?? "",
      askedText: question.asked_text,
    });
    byKey.set(key, group);
  }

  // A family with options but no open question still belongs on the board —
  // their question was answered and closed, and dropping them would make the
  // board say the disruption hit fewer people than it did.
  for (const option of pending) {
    const already = [...byKey.values()].some((g) =>
      g.rows.some((r) => r.patientId === option.patient_id),
    );
    if (already) continue;
    const loose =
      byKey.get("settled:") ??
      ({ key: "settled:", reason: "doctor_away", day: "", rows: [] } as Group);
    loose.rows.push({
      patientId: option.patient_id,
      name: option.patient_id,
      language: "",
      stage: "options",
      said: "",
      askedText: "",
    });
    byKey.set("settled:", loose);
  }

  return [...byKey.values()].sort((a, b) => b.rows.length - a.rows.length);
}

function readableDay(day: string): string {
  if (!day) return "";
  const when = new Date(`${day}T00:00:00`);
  return Number.isNaN(when.getTime())
    ? day
    : when.toLocaleDateString("en-IN", { day: "numeric", month: "long" });
}

export function DisruptionBoard({ revision = 0 }: { revision?: number }) {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [questions, readings, pending] = await Promise.all([
        requestsApi.questions(),
        requestsApi.waiting(),
        disruptionsApi.pending(),
      ]);
      setGroups(groupsFrom(questions, readings, pending));
      setFailed(null);
    } catch (error) {
      // Say so rather than render an empty board, which reads as "nothing is
      // happening" — the most misleading thing this screen could claim.
      setFailed(error instanceof Error ? error.message : "could not read the board");
      setGroups([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, revision]);

  const total = useMemo(
    () => (groups ?? []).reduce((count, g) => count + g.rows.length, 0),
    [groups],
  );

  if (groups === null) return <SkeletonRows rows={3} />;

  return (
    <Card
      title="What one change did, and to whom"
      hint={
        total
          ? `${total} famil${total === 1 ? "y" : "ies"} affected right now`
          : "Nothing has disrupted anybody's plan"
      }
    >
      {failed && <Notice tone="stop">{failed}</Notice>}
      {!failed && groups.length === 0 && (
        <p className="empty">
          No family is waiting on a change. This board fills when the hospital
          publishes something that lands on somebody.
        </p>
      )}

      <div className="stack">
        {groups.map((group) => (
          <section key={group.key} className="board-group">
            <header className="board-group-head">
              <strong>
                {WHY_ASKED[group.reason]}
                {group.day ? ` on ${readableDay(group.day)}` : ""}
              </strong>
              <Chip tone="info">
                {group.rows.length} famil{group.rows.length === 1 ? "y" : "ies"}
              </Chip>
            </header>

            {group.rows.map((row) => {
              const isOpen = open === row.patientId;
              return (
                <div key={row.patientId} className="board-row">
                  <button
                    type="button"
                    className="board-row-head"
                    aria-expanded={isOpen}
                    onClick={() => setOpen(isOpen ? null : row.patientId)}
                  >
                    <strong>{row.name}</strong>
                    {row.language && <Chip>{row.language}</Chip>}
                    <Chip tone={STAGE_TONE[row.stage]}>{STAGE_SAYS[row.stage]}</Chip>
                    <span className="spacer" />
                    <span className="hint">{isOpen ? "▲" : "▼"}</span>
                  </button>

                  {/* Their own words, before any of our working. A navigator
                      reading a plan should see the sentence it came from. */}
                  {isOpen && (
                    <div className="board-row-body stack">
                      {row.said && (
                        <blockquote className="said">“{row.said}”</blockquote>
                      )}
                      <ReasoningLog patientId={row.patientId} revision={revision} />
                      <PlannerSearch patientId={row.patientId} revision={revision} />
                    </div>
                  )}
                </div>
              );
            })}
          </section>
        ))}
      </div>
    </Card>
  );
}
