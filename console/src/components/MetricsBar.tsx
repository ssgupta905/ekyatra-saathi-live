import type { Metrics } from "../lib/api";

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

/**
 * The only numbers that matter, in the family's terms rather than the
 * hospital's: trips not taken, and money not spent getting there.
 */
export function MetricsBar({ metrics }: { metrics: Metrics | null }) {
  if (!metrics) return null;

  return (
    <section className="card">
      <h2>Cohort · scored against planted ground truth</h2>
      <div className="metrics">
        <div className="metric">
          <div className="value">{metrics.patients}</div>
          <div className="label">patients</div>
        </div>
        <div className="metric">
          <div className="value">{metrics.baseline_wasted_trips}</div>
          <div className="label">
            wasted trips, hospital default ({Math.round(metrics.baseline_waste_rate * 100)}%)
          </div>
        </div>
        <div className="metric">
          <div className="value" style={{ color: "var(--go)" }}>
            {metrics.saathi_wasted_trips}
          </div>
          <div className="label">
            wasted trips, with Saathi ({Math.round(metrics.saathi_waste_rate * 100)}%)
          </div>
        </div>
        <div className="metric">
          <div className="value">{metrics.wasted_trips_avoided}</div>
          <div className="label">wasted trips avoided</div>
        </div>
        <div className="metric">
          <div className="value">{inr.format(metrics.non_medical_cost_avoided_inr)}</div>
          <div className="label">non-medical cost avoided</div>
        </div>
      </div>
    </section>
  );
}
