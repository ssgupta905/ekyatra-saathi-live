import { useMemo } from "react";
import type { Story } from "../lib/api";
import { type WorldEvent } from "../lib/live";
import { Card } from "../ui/primitives";

/**
 * The brief's four-figure cards, every one of them counted from the run.
 *
 * The brief prints "2 min · 0 nights · 1 approval · 4 of 6" as the result of
 * Shambhu's morning. Those are good numbers and they are exactly the kind that
 * get typed into a slide and never checked again. So each one here is derived
 * from the event stream in front of you, and each says underneath which events
 * it counted. If the run went differently, the figures go differently.
 *
 * `—` is a real answer. A figure nothing has happened for yet says so rather
 * than showing a confident zero.
 */

function minutesBetween(a: string, b: string): number {
  return Math.abs(new Date(b).getTime() - new Date(a).getTime()) / 60000;
}

export function StoryScorecard({
  story,
  events,
}: {
  story: Story;
  events: WorldEvent[];
}) {
  const figures = useMemo(() => {
    const mine = events
      .filter((e) => !e.patient_id || e.patient_id === story.patient_id)
      .slice()
      .reverse();

    const disruption = mine.find((e) => e.kind === "disruption.raised");
    const firstToFamily = mine.find((e) => e.kind === "holding_message.sent");
    const approvals = mine.filter((e) => e.kind === "approval.recorded");
    const affected = disruption
      ? ((disruption.payload.affected as string[] | undefined)?.length ?? 0)
      : 0;

    const toFamilyMs =
      disruption && firstToFamily
        ? minutesBetween(disruption.at, firstToFamily.at)
        : null;

    return [
      {
        value:
          toFamilyMs === null
            ? "—"
            : toFamilyMs < 1
              ? "<1 min"
              : `${toFamilyMs.toFixed(0)} min`,
        label: "from the disruption to the family's first message",
        from: "disruption.raised → holding_message.sent",
        good: toFamilyMs !== null,
      },
      {
        value: affected ? `${affected}` : "—",
        label: affected === 1 ? "family affected" : "families affected",
        from: "counted by the world, not estimated",
        good: false,
      },
      {
        value: approvals.length ? `${approvals.length}` : "—",
        label:
          approvals.length === 1
            ? "approval, by a named person"
            : "approvals, each by a named person",
        from: approvals.length
          ? (approvals[approvals.length - 1].payload.approved_by as string) ?? "approval.recorded"
          : "nothing approved yet",
        good: false,
      },
      {
        value: affected ? `${Math.max(affected - approvals.length, 0)} of ${affected}` : "—",
        label: "moved with no human decision needed",
        from: "affected minus those that needed an approval",
        good: affected > 0 && approvals.length < affected,
      },
    ];
  }, [events, story.patient_id]);

  return (
    <Card
      title="What this run cost"
      hint="counted from the events above"
      note="Every figure is derived from the run in front of you and names the events it counted. Nothing here is carried over from the brief — if the story runs differently, these change."
    >
      <div className="scorecard">
        {figures.map((figure) => (
          <div className="figure" key={figure.label}>
            <div className={figure.good ? "v good" : "v"}>{figure.value}</div>
            <div className="k">{figure.label}</div>
            <span className="from">{figure.from}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
