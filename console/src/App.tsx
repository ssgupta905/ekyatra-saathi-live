import { useEffect, useState } from "react";
import {
  api,
  LANGUAGE_NAMES,
  type Alert,
  type CareStep,
  type LedgerView,
  type Metrics,
  type Patient,
  type PlanResponse,
} from "./lib/api";
import { PlanCard } from "./components/PlanCard";
import { MessageCard } from "./components/MessageCard";
import { LedgerCard } from "./components/LedgerCard";
import { MetricsBar } from "./components/MetricsBar";
import { AlertsCard } from "./components/AlertsCard";

export default function App() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selected, setSelected] = useState<Patient | null>(null);
  const [steps, setSteps] = useState<CareStep[]>([]);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [ledger, setLedger] = useState<LedgerView | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .patients()
      .then((rows) => {
        setPatients(rows);
        setSelected(rows[0] ?? null);
      })
      .catch((e: Error) => setError(e.message));
    api.alerts().then(setAlerts).catch(() => undefined);
    // /metrics plans the whole cohort, so it is slow on purpose — it is the
    // benchmark, not a dashboard poll.
    api.metrics().then(setMetrics).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!selected) return;
    setPlan(null);
    setLedger(null);
    Promise.all([api.steps(selected.id), api.plan(selected.id)])
      .then(([stepRows, planResponse]) => {
        setSteps(stepRows);
        setPlan(planResponse);
        // Fetch the ledger after planning, so it reflects the entries the plan wrote.
        return api.ledger(selected.id);
      })
      .then(setLedger)
      .catch((e: Error) => setError(e.message));
  }, [selected]);

  return (
    <>
      <header className="app">
        <h1>EKYATRA Saathi — Navigator Console</h1>
        <p>
          Logistics only. Saathi never diagnoses, never reads report content, and never
          answers a clinical question — it routes it to you.
        </p>
      </header>

      <div className="layout">
        <nav className="sidebar">
          {patients.map((patient) => (
            <button
              key={patient.id}
              className="patient-row"
              aria-selected={selected?.id === patient.id}
              onClick={() => setSelected(patient)}
            >
              <div className="id">{patient.id}</div>
              <div className="meta">
                {patient.home_district} · {Math.round(patient.home_distance_km)} km ·{" "}
                {LANGUAGE_NAMES[patient.language]}
              </div>
            </button>
          ))}
        </nav>

        <main>
          {error && <p className="notice error">{error}</p>}
          <MetricsBar metrics={metrics} />

          {selected && (
            <>
              <PlanCard plan={plan} />
              <MessageCard plan={plan} patient={selected} />

              <section className="card">
                <h2>Journey · {selected.id}</h2>
                <table>
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Status</th>
                      <th>Scheduled</th>
                      <th>Queue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {steps.map((step) => (
                      <tr key={step.id}>
                        <td>{step.kind.replace(/_/g, " ")}</td>
                        <td>
                          <span className={`status ${step.status}`}>
                            {step.status.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td className="mono">
                          {step.scheduled_for ?? step.completed_on ?? "—"}
                        </td>
                        <td className="mono">{step.queue ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <LedgerCard ledger={ledger} />
            </>
          )}

          <AlertsCard alerts={alerts} />
        </main>
      </div>
    </>
  );
}
