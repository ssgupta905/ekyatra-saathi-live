import { useEffect, useState } from "react";
import { api, type Metrics } from "../lib/api";
import { EVENT_LABEL, EVENT_TONE, fmtAgo, type LiveWorldState } from "../lib/live";
import type { PageId } from "../lib/nav";
import { PageHeader } from "../components/shell/AppShell";
import { StatTile } from "../components/StatTile";
import { Drawer } from "../components/Drawer";
import { CohortPanel } from "../components/CohortPanel";
import { Bell, CheckCircle, People, Spark } from "../ui/icons";

const inr = (n: number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);

/**
 * The landing page: four numbers that each lead somewhere, the families being
 * watched, and the last few things the system did. Everything else is one
 * click away rather than on screen.
 */
export function TodayPage({
  world,
  onNavigate,
  onOpenFamily,
}: {
  world: LiveWorldState;
  onNavigate: (page: PageId) => void;
  onOpenFamily: (patientId: string) => void;
}) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [impactOpen, setImpactOpen] = useState(false);
  const snap = world.snapshot;

  useEffect(() => {
    api.metrics().then(setMetrics).catch(() => undefined);
  }, [world.cohortRevision]);

  const decisions = snap?.options_pending ?? 0;
  const alerts = snap?.alerts ?? 0;
  const disruptions = snap?.open_disruptions ?? 0;
  const recent = world.events.filter((e) => e.kind !== "clock.tick" && e.kind !== "runner.state").slice(0, 5);

  return (
    <div className="page">
      <PageHeader title="Today" question="What needs me right now?" />

      <div className="tiles">
        <StatTile
          label="Waiting on a decision"
          value={decisions}
          hint={decisions ? "Disrupted families with options to pick" : "Nothing to approve"}
          tone={decisions ? "wait" : "neutral"}
          icon={<CheckCircle size={15} />}
          onOpen={() => onNavigate("decisions")}
        />
        <StatTile
          label="Need a person"
          value={alerts}
          hint={alerts ? "Clinical questions or families gone quiet" : "Every family is on a plan"}
          tone={alerts ? "critical" : "neutral"}
          icon={<Bell size={15} />}
          onOpen={() => onNavigate("decisions")}
        />
        <StatTile
          label="Open disruptions"
          value={disruptions}
          hint={disruptions ? "Machines, staff or stock unavailable" : "Every resource running"}
          tone={disruptions ? "wait" : "neutral"}
          icon={<Spark size={15} />}
          onOpen={() => onNavigate("activity")}
        />
        <StatTile
          label="Families planned"
          value={snap?.patients ?? "—"}
          hint="Re-planned every simulated day"
          icon={<People size={15} />}
          onOpen={() => onNavigate("families")}
        />
      </div>

      <div className="today-grid">
        <section className="panel">
          <div className="panel-head">
            <h2>Journeys not taken</h2>
            <button type="button" className="link-btn" onClick={() => setImpactOpen(true)}>
              How this is measured
            </button>
          </div>
          <div className="impact">
            <div>
              <div className="impact-value go">{metrics ? metrics.wasted_trips_avoided : "—"}</div>
              <div className="impact-label">wasted trips avoided</div>
            </div>
            <div>
              <div className="impact-value">
                {metrics ? inr(metrics.non_medical_cost_avoided_inr) : "—"}
              </div>
              <div className="impact-label">fares, lodging and wages not spent</div>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Watched live</h2>
            <button type="button" className="link-btn" onClick={() => onNavigate("families")}>
              All families
            </button>
          </div>
          <div className="chip-list">
            {(snap?.watched ?? []).map((id) => (
              <button key={id} type="button" className="family-chip" onClick={() => onOpenFamily(id)}>
                <span className="pulse on" />
                {id}
              </button>
            ))}
          </div>
        </section>

        <section className="panel span-2">
          <div className="panel-head">
            <h2>Just happened</h2>
            <button type="button" className="link-btn" onClick={() => onNavigate("activity")}>
              All activity
            </button>
          </div>
          {recent.length === 0 ? (
            <p className="empty">Quiet. Press play in the top bar to run the world.</p>
          ) : (
            <ul className="mini-feed">
              {recent.map((event) => (
                <li key={event.seq}>
                  <span className={`mini-kind ${EVENT_TONE[event.kind]}`}>{EVENT_LABEL[event.kind]}</span>
                  <span className="mini-summary">{event.summary}</span>
                  {event.patient_id ? (
                    <button type="button" className="link-btn" onClick={() => onOpenFamily(event.patient_id!)}>
                      {event.patient_id}
                    </button>
                  ) : null}
                  <span className="mini-when">{fmtAgo(event.at)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <Drawer
        title="Journeys not taken"
        subtitle="Scored against planted ground truth on synthetic patients"
        open={impactOpen}
        onClose={() => setImpactOpen(false)}
      >
        <CohortPanel metrics={metrics} />
      </Drawer>
    </div>
  );
}
