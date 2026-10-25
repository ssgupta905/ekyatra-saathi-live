import { useEffect, useState } from "react";
import { admin, type AdminConfig } from "@saathi/api-client";
import type { Persona } from "../lib/identity";
import { AuditLog } from "./AuditLog";
import { Card } from "@saathi/ui-web";

/**
 * Readiness rules, languages, call cadence, and the audit log — read-only in
 * this prototype. Editing these is a reasonable pilot follow-up; the brief's
 * admin ask centers on auditability, which this screen gives in full.
 */
export function AdminConsole({ persona }: { persona: Persona }) {
  const [config, setConfig] = useState<AdminConfig | null>(null);

  useEffect(() => {
    admin.config().then(setConfig).catch(() => undefined);
  }, []);

  return (
    <div className="stage">
      <Card title={persona.title} hint={persona.name}>
        <p className="plain">Readiness rules per step, languages and call hours, and the audit log.</p>
      </Card>

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
    </div>
  );
}
