import { useCallback, useEffect, useState } from "react";
import { requests as requestsApi, type Considered, type PlanSearch } from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { SkeletonRows } from "../ui/kit";

/**
 * Every date the planner tried, including the ones it threw away.
 *
 * The family is shown only what is actually on offer — `care_rules` discards
 * impossible options silently and on purpose, because offering somebody a
 * date and then withdrawing it is worse than never offering it. But that left
 * nobody able to answer the question every senior clinician asks about an
 * automated decision: **what else did you look at?**
 *
 * So this is the other audience's view of the same search. It shows the
 * rejections first-class, with the rule that killed each one in the rule's
 * own words, because a planner that only ever displays its successes is
 * indistinguishable from one that only ever found one option.
 *
 * Nothing here can change a decision. The component reads a record the
 * planner wrote while it worked; it cannot keep an option the rules rejected
 * or drop one they kept. A log that could edit the thing it describes would
 * not be worth reading.
 */

/** Rejections grouped by the rule behind them, commonest first.
 *
 *  Grouping rather than listing: five dates refused by one care rule is a
 *  single fact about the hospital's rules, and reading it as five facts
 *  invites the conclusion that the planner failed five separate times.
 */
function byRule(items: Considered[]): { why: string; dates: Considered[] }[] {
  const groups = new Map<string, Considered[]>();
  for (const item of items) {
    const existing = groups.get(item.why);
    if (existing) existing.push(item);
    else groups.set(item.why, [item]);
  }
  return [...groups.entries()]
    .map(([why, dates]) => ({ why, dates }))
    .sort((a, b) => b.dates.length - a.dates.length);
}

function day(iso: string | null): string {
  if (!iso) return "no date";
  const parsed = new Date(`${iso}T00:00:00`);
  return Number.isNaN(parsed.getTime())
    ? iso
    : parsed.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

/** What an offered option costs the family, when the search got far enough
 *  to price it. Silent when it did not — an unpriced option is not a free one. */
function cost(item: Considered): string | null {
  const parts: string[] = [];
  if (item.nights_added) parts.push(`${item.nights_added} more night(s) away`);
  if (item.trips_added) parts.push(`${item.trips_added} more trip(s)`);
  return parts.length ? parts.join(", ") : null;
}

export function PlannerSearch({
  patientId,
  revision,
}: {
  patientId?: string;
  revision: number;
}) {
  const [search, setSearch] = useState<PlanSearch | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!patientId) return;
    requestsApi
      .search(patientId)
      .then(setSearch)
      .catch((e: Error) => setError(e.message));
  }, [patientId]);

  useEffect(load, [load, revision]);

  if (!patientId) return null;
  if (error) return <Notice tone="warn">{error}</Notice>;
  if (search === null) return <SkeletonRows rows={3} />;

  const offered = search.considered.filter((item) => item.offered);
  const rejected = search.considered.filter((item) => !item.offered);

  return (
    <Card title="What the planner considered" hint={search.summary}>
      {search.considered.length === 0 ? (
        <p className="muted">
          Nothing has forced a re-plan for this family yet. The search fills the
          moment something does.
        </p>
      ) : (
        <>
          <ol className="reasoning">
            {offered.map((item) => (
              <li key={item.ref} className="step step-human">
                <Chip tone="go">{day(item.on)}</Chip>
                <span className="step-text">
                  on the list
                  {cost(item) && <em className="step-again"> — {cost(item)}</em>}
                </span>
              </li>
            ))}
          </ol>

          {rejected.length > 0 && (
            <>
              {/* The half a planner usually hides. Named plainly: a heading
                  that said "other dates" would be a way of not saying it. */}
              <p className="muted">
                {rejected.length} date(s) were ruled out, and by what:
              </p>
              <ol className="reasoning">
                {byRule(rejected).map(({ why, dates }) => (
                  <li key={why} className="step step-guard">
                    <Chip tone="uncertain">{dates.length}</Chip>
                    <span className="step-text">
                      {why}
                      <em className="step-again">
                        {" "}
                        — {dates.map((item) => day(item.on)).join(", ")}
                      </em>
                      {/* The rule's own objection — a day of the week, a
                          confidence, a number of nights. Only when it adds
                          something the verdict did not already say. */}
                      {dates.some((item) => item.detail) && (
                        <em className="step-again">
                          {" "}
                          ({[...new Set(dates.map((d) => d.detail).filter(Boolean))].join("; ")})
                        </em>
                      )}
                    </span>
                  </li>
                ))}
              </ol>
            </>
          )}
        </>
      )}
    </Card>
  );
}
