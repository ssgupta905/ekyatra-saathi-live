import { useEffect, useState } from "react";
import { admin, type AdminConfig } from "@saathi/api-client";
import { Card, Notice } from "@saathi/ui-web";

/**
 * How the system is set up. Read-only for now, and says where each value comes
 * from, so nobody edits a number here expecting the planner to change.
 */
export function Configuration() {
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    admin.config().then(setConfig).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (!config) return <Notice tone="calm">Loading…</Notice>;

  return (
    <div className="widget-grid">
      <Card
        title="Readiness rules"
        hint={`${Math.round(config.readiness.coverage * 100)}% coverage guarantee · α ${config.readiness.conformal_alpha}`}
        flush
        note="Set by SAATHI_CONFORMAL_ALPHA. The queue profiles are the demo generator's turnaround shapes; on real records the forecast is calibrated on reports this hospital has released."
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

      <Card title="Languages and channels" note="Set in the server's environment.">
        <table className="audit-table">
          <tbody>
            <tr>
              <td>Languages</td>
              <td>{config.languages.join(", ")}</td>
            </tr>
            <tr>
              <td>Channels</td>
              <td>{config.channels.join(", ")}</td>
            </tr>
            <tr>
              <td>Families watched live</td>
              <td>{config.staff.watched_families}</td>
            </tr>
            <tr>
              <td>Desk auto-confirm (demo)</td>
              <td>after {config.staff.auto_confirm_ticks} days</td>
            </tr>
            <tr>
              <td>Caregiver actor cadence (demo)</td>
              <td>every {config.staff.inbound_every_seconds}s</td>
            </tr>
          </tbody>
        </table>
      </Card>

      <Card title="Integrations">
        <table className="audit-table">
          <tbody>
            <tr>
              <td>Language layer</td>
              <td>{config.language_layer_enabled ? "on" : "off (no GROQ_API_KEY / ANTHROPIC_API_KEY)"}</td>
            </tr>
            <tr>
              <td>Actors</td>
              <td>{config.actors_enabled ? "on" : "off"}</td>
            </tr>
          </tbody>
        </table>
      </Card>
    </div>
  );
}
