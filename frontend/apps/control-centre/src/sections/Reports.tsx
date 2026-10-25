import { useEffect, useMemo, useState } from "react";
import { reports, type QueueForecasts, type ReportList, type ReportState } from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { ReportTable } from "../components/ReportTable";
import { useWorld } from "../world";

const FILTERS: [ReportState | "", string][] = [
  ["", "All"],
  ["overdue", "Overdue"],
  ["due", "Due now"],
  ["waiting", "Not due yet"],
  ["no_forecast", "No forecast"],
  ["released", "Released"],
];

/**
 * Every report in the hospital, against the window it should land in, and what
 * the forecast knows about each lab queue — including whether it is keeping the
 * coverage it promises.
 */
export function Reports({ onOpenFamily }: { onOpenFamily: (patientId: string) => void }) {
  const world = useWorld();
  const [list, setList] = useState<ReportList | null>(null);
  const [queues, setQueues] = useState<QueueForecasts | null>(null);
  const [filter, setFilter] = useState<ReportState | "">("");
  const [queue, setQueue] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    reports.list().then(setList).catch((e: Error) => setError(e.message));
    reports.queues().then(setQueues).catch(() => undefined);
  }, [world.cohortRevision]);

  const rows = useMemo(
    () =>
      (list?.reports ?? []).filter(
        (r) => (!filter || r.state === filter) && (!queue || r.queue === queue),
      ),
    [list, filter, queue],
  );

  if (error) return <Notice tone="warn">{error}</Notice>;

  return (
    <div className="widget-grid">
      <div className="span-2">
        <Card
          title="Lab queues"
          hint={queues ? `forecast promises ${Math.round(queues.coverage_target * 100)}% coverage` : ""}
          flush
          note={
            queues
              ? `A queue is forecast only once it has at least ${queues.min_calibration} past reports and enough of them for the promised coverage. Until then the planner says it does not know rather than promise a date. Observed coverage is the share of released reports that landed inside the interval.`
              : undefined
          }
        >
          <table className="audit-table">
            <thead>
              <tr>
                <th>Queue</th>
                <th>Past reports</th>
                <th>Interval</th>
                <th>Forecast</th>
                <th>Pending</th>
                <th>Released</th>
                <th>Observed coverage</th>
              </tr>
            </thead>
            <tbody>
              {(queues?.queues ?? []).map((q) => (
                <tr key={q.queue}>
                  <td className="mono">
                    <button type="button" className="linkish" onClick={() => setQueue(q.queue === queue ? "" : q.queue)}>
                      {q.queue}
                    </button>
                  </td>
                  <td>{q.observations}</td>
                  <td>{q.interval_days ? `${q.interval_days[0]}–${q.interval_days[1]} days` : "—"}</td>
                  <td>
                    <Chip tone={q.calibrated ? "go" : "uncertain"}>{q.calibrated ? "calibrated" : "not yet"}</Chip>
                  </td>
                  <td>{q.pending}</td>
                  <td>{q.released}</td>
                  <td>
                    {q.observed_coverage == null
                      ? "—"
                      : `${Math.round(q.observed_coverage * 100)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="span-2">
        <Card
          title="Every report"
          hint={list ? `as of ${list.today}${queue ? ` · queue ${queue}` : ""}` : "loading…"}
          aside={
            <div className="cc-filters">
              {FILTERS.map(([value, label]) => (
                <button
                  key={value || "all"}
                  type="button"
                  aria-pressed={filter === value}
                  onClick={() => setFilter(value)}
                >
                  {label}
                  {value && list?.counts[value] ? ` · ${list.counts[value]}` : ""}
                </button>
              ))}
            </div>
          }
          flush
        >
          <ReportTable rows={rows} onOpenFamily={onOpenFamily} />
        </Card>
      </div>
    </div>
  );
}
