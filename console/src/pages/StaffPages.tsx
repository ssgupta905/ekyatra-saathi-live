import { useCallback, useEffect, useState } from "react";
import { admin, live, type AdminConfig, type DeskCandidate } from "../lib/api";
import type { Persona } from "../lib/identity";
import type { LiveWorldState } from "../lib/live";
import { PageHeader } from "../components/shell/AppShell";
import { DisruptionReportForm } from "../components/DisruptionReportForm";
import { DeskQueue } from "../components/DeskQueue";
import { AuditLog } from "../components/AuditLog";
import { StatTile } from "../components/StatTile";
import { Card, Notice } from "../ui/primitives";

/* ── desk ───────────────────────────────────────────────────────────────── */

export function DeskReportPage({ persona }: { persona: Persona }) {
  const [affected, setAffected] = useState<string[] | null>(null);
  return (
    <div className="page narrow">
      <PageHeader title="Report an issue" question={`${persona.title} · is something you run unavailable?`} />
      <DisruptionReportForm defaultResourceId={persona.deskResourceId} onReported={setAffected} />
      {affected && (
        <Notice tone="calm">
          {affected.length
            ? `${affected.length} famil${affected.length === 1 ? "y" : "ies"} affected (${affected.join(", ")}). Each has been told not to travel yet; the planner is re-solving.`
            : "No booked family falls inside that window."}
        </Notice>
      )}
    </div>
  );
}

export function DeskRecordsPage({ world }: { world: LiveWorldState }) {
  const [queue, setQueue] = useState<DeskCandidate[]>([]);
  const refresh = useCallback(() => {
    live.deskQueue().then(setQueue).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh, world.cohortRevision]);

  return (
    <div className="page narrow">
      <PageHeader title="Records" question="Which finished records need your confirmation?" />
      <DeskQueue queue={queue} onConfirmed={refresh} />
    </div>
  );
}

/* ── admin ──────────────────────────────────────────────────────────────── */

export function AdminRulesPage() {
  const [config, setConfig] = useState<AdminConfig | null>(null);
  useEffect(() => {
    admin.config().then(setConfig).catch(() => undefined);
  }, []);

  return (
    <div className="page">
      <PageHeader title="Rules" question="What readiness rules is the system running with?" />
      {config && (
        <>
          <div className="tiles">
            <StatTile
              label="Coverage guarantee"
              value={`${Math.round(config.readiness.coverage * 100)}%`}
              hint="Readiness windows are right at least this often"
              tone="go"
            />
            <StatTile label="Languages" value={config.languages.length} hint={config.languages.join(", ")} />
            <StatTile label="Channels" value={config.channels.length} hint={config.channels.join(", ")} />
            <StatTile
              label="Watched families"
              value={config.staff.watched_families}
              hint={`Auto-confirm after ${config.staff.auto_confirm_ticks} days`}
            />
          </div>
          <Card title="Turnaround per queue" hint="what the conformal windows are calibrated on" flush>
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Queue</th>
                  <th>Median</th>
                  <th>Slow tail</th>
                  <th>Tail adds</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(config.readiness.queue_turnaround_profiles).map(([queue, p]) => (
                  <tr key={queue}>
                    <td>{queue.replace(/_/g, " ")}</td>
                    <td>{p.median_days} days</td>
                    <td>{Math.round(p.tail_probability * 100)}% of the time</td>
                    <td>{p.tail_extra_days} days</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}

export function AdminAuditPage() {
  return (
    <div className="page">
      <PageHeader title="Audit log" question="Every action, and who or what it came from." />
      <div className="widget-scroll tall">
        <AuditLog />
      </div>
    </div>
  );
}
