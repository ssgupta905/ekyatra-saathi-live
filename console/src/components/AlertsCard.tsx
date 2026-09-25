import type { Alert } from "../lib/api";

/**
 * Silence after a visit, and clinical questions that need a human. Both land
 * here because both mean a person has to pick up the phone.
 */
export function AlertsCard({ alerts }: { alerts: Alert[] }) {
  return (
    <section className="card">
      <h2>Alerts</h2>
      {alerts.length === 0 ? (
        <p className="empty">No open alerts.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Patient</th>
              <th>Kind</th>
              <th>Detail</th>
              <th>Raised</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((alert) => (
              <tr key={alert.id}>
                <td className="mono">{alert.patient_id}</td>
                <td>{alert.kind.replace(/_/g, " ")}</td>
                <td>{alert.detail}</td>
                <td className="mono">{new Date(alert.raised_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
