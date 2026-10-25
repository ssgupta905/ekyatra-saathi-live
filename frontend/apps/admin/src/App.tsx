import { useEffect, useState } from "react";
import { admin, useLiveWorld, type AdminConfig } from "@saathi/api-client";
import { AgentStatus, AppShell, Card } from "@saathi/ui-web";
import { AuditLog } from "./AuditLog";
import { IDENTITY } from "./identity";

/**
 * Readiness rules, languages, call cadence, and the audit log — read-only for now.
 * Editing these is a reasonable pilot follow-up; the admin's ask centres on
 * auditability, which this screen gives in full.
 */
export default function App() {
  const world = useLiveWorld();
  const [config, setConfig] = useState<AdminConfig | null>(null);

  useEffect(() => {
    admin.config().then(setConfig).catch(() => undefined);
  }, []);

  return (
    <AppShell
      app="Admin"
      identity={IDENTITY}
      snapshot={world.snapshot}
      connected={world.connected}
    >
      <AgentStatus working={world.working} events={world.events} />

      <div className="hx-panes single">
        <main className="hx-work">
          {config && (
            <div className="widget-grid">
              <Card
                title="Readiness rules"
                hint={`${Math.round(config.readiness.coverage * 100)}% coverage guarantee`}
                flush
              >
                <table className="audit-table">
                  <thead>
                    <tr>
                      <th>Queue</th>
                      <th>Median turnaround</th>
                      <th>Tail probability</th>
                      <th>Tail extra</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(config.readiness.queue_turnaround_profiles).map(([queue, p]) => (
                      <tr key={queue}>
                        <td>{queue}</td>
                        <td>{p.median_days}d</td>
                        <td>{Math.round(p.tail_probability * 100)}%</td>
                        <td>{p.tail_extra_days}d</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>

              <Card title="Staff, languages, call hours">
                <p className="plain">
                  Languages: {config.languages.join(", ")} · Channels: {config.channels.join(", ")}
                </p>
                <p className="plain">
                  Watched families: {config.staff.watched_families} · Auto-confirm after{" "}
                  {config.staff.auto_confirm_ticks} ticks · Caregiver cadence every{" "}
                  {config.staff.inbound_every_seconds}s
                </p>
                <p className="hint">
                  Language layer: {config.language_layer_enabled ? "on" : "off"} · Actors:{" "}
                  {config.actors_enabled ? "on" : "off"}
                </p>
              </Card>

              <div className="span-2 widget-scroll tall">
                <AuditLog />
              </div>
            </div>
          )}
        </main>
      </div>
    </AppShell>
  );
}
