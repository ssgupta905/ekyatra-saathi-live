import { useCallback, useEffect, useState } from "react";
import { partner, type PartnerJob, type PartnerQueue } from "@saathi/api-client";
import { Business } from "./Business";
import { Job } from "./Job";

/**
 * What a cab firm, a hotel desk or a pharmacy sees.
 *
 * One list, one job at a time, three answers. Built for a phone held in one
 * hand at a desk that is doing something else: no navigation, no tabs, no
 * dashboard. The jobs somebody is waiting on come first, because those are the
 * only ones that need anything from the person reading.
 *
 * It shows the least that lets the job be done — a first name, a district, a
 * day when there is one. There is nothing here about anyone's care, and there
 * is no screen to reach it from: the role cannot read a family at all.
 *
 * There is a second screen now — the vendor's own business: its rates, how it
 * stands, what it is owed. It is behind a switch rather than beside the jobs,
 * because a desk that opens this app has one question ("is anybody waiting on
 * me?") and the answer to it must not be below the fold.
 */
export default function App() {
  const [queue, setQueue] = useState<PartnerQueue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"jobs" | "business">("jobs");

  const refresh = useCallback(() => {
    partner
      .jobs()
      .then((next) => {
        setQueue(next);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    refresh();
    // A desk leaves this open. Polling keeps it honest without a stream, and
    // thirty seconds is well inside the time anyone would wait for a cab.
    const id = window.setInterval(refresh, 30_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const waiting = (queue?.jobs ?? []).filter((j) => j.status === "pending");
  const settled = (queue?.jobs ?? []).filter((j) => j.status !== "pending");

  return (
    <div className="pt-app">
      <header className="pt-top">
        <span className="pt-brand">Saathi</span>
        <span className="pt-org">{queue?.organisation.name ?? "…"}</span>
        <nav className="pt-tabs">
          <button
            type="button"
            className={view === "jobs" ? "on" : ""}
            onClick={() => setView("jobs")}
          >
            Jobs{waiting.length > 0 ? ` (${waiting.length})` : ""}
          </button>
          <button
            type="button"
            className={view === "business" ? "on" : ""}
            onClick={() => setView("business")}
          >
            Your business
          </button>
        </nav>
      </header>

      <main className="pt-scroll">
        {error && <p className="pt-error">{error}</p>}
        {view === "business" && <Business />}

        {view === "jobs" && queue && waiting.length === 0 && (
          <p className="pt-empty">
            Nothing is waiting on you. We will show a job here the moment one is.
          </p>
        )}

        {view === "jobs" && waiting.length > 0 && (
          <>
            <h2 className="pt-h2">Waiting on you</h2>
            {waiting.map((job: PartnerJob) => (
              <Job key={job.item_id} job={job} onAnswered={refresh} />
            ))}
          </>
        )}

        {view === "jobs" && settled.length > 0 && (
          <>
            <h2 className="pt-h2">Answered</h2>
            {settled.map((job: PartnerJob) => (
              <Job key={job.item_id} job={job} onAnswered={refresh} settled />
            ))}
          </>
        )}
      </main>
    </div>
  );
}
