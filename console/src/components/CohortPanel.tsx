import type { Metrics } from "../lib/api";
import { inr, pct } from "../lib/format";
import { Card, Disclosure } from "../ui/primitives";

/**
 * The measurement, in the family's currency.
 *
 * One hero figure — trips not taken — then the two rates side by side. The
 * comparison is one hue in two ordinal steps rather than two colours, because
 * these are the same quantity measured twice, not two categories.
 */
export function CohortPanel({ metrics }: { metrics: Metrics | null }) {
  if (!metrics) {
    return (
      <Card title="Cohort outcome" hint="planning every patient…">
        <div style={{ display: "grid", gap: 10, maxWidth: 320 }}>
          <div className="skeleton" style={{ height: 40 }} />
          <div className="skeleton" style={{ width: "70%" }} />
        </div>
      </Card>
    );
  }

  const max = Math.max(metrics.baseline_wasted_trips, metrics.saathi_wasted_trips, 1);
  const bars = [
    {
      key: "base",
      label: "Hospital default: fixed intervals",
      value: metrics.baseline_wasted_trips,
      rate: metrics.baseline_waste_rate,
    },
    {
      key: "saathi",
      label: "With Saathi's prerequisite gate",
      value: metrics.saathi_wasted_trips,
      rate: metrics.saathi_waste_rate,
    },
  ];

  return (
    <Card
      title="Cohort outcome"
      hint={`${metrics.patients} synthetic patients, scored against planted ground truth`}
      note="A wasted trip is one the family made where the step could not happen. Ground truth is planted by the generator, so the score is a measurement rather than an estimate — on synthetic patients, not yet on real ones."
    >
      <div className="hero-figure" style={{ padding: "4px 0 0" }}>
        <div className="hf-val" style={{ color: "var(--go)" }}>
          {metrics.wasted_trips_avoided}
        </div>
        <div className="hf-label">
          journeys not taken — trips the hospital's fixed-interval default would have
          asked these families to make for a step that was not ready.
        </div>
      </div>

      <div className="compare" style={{ marginTop: 22 }}>
        {bars.map((b) => (
          <div className="crow" key={b.key}>
            <div className="clabel">{b.label}</div>
            <div className="cbarwrap">
              <div
                className={`cbar ${b.key}`}
                style={{ width: `${(b.value / max) * 100}%` }}
                title={`${b.label}: ${b.value} wasted trips, ${pct(b.rate)} of trips taken`}
              />
              <span className="cval tnum">
                {b.value} wasted · {pct(b.rate)} of trips
              </span>
            </div>
          </div>
        ))}
        <div className="caxis">0 — {max} wasted trips across {metrics.patients} patients</div>
      </div>

      <div className="tiles" style={{ marginTop: 22, borderRadius: "var(--r-md)", overflow: "hidden" }}>
        <div className="tile">
          <div className="tval tnum">{metrics.patients}</div>
          <div className="tlabel">families planned</div>
        </div>
        <div className="tile">
          <div className="tval tnum">{pct(metrics.baseline_waste_rate)}</div>
          <div className="tlabel">of trips wasted, today's default</div>
        </div>
        <div className="tile">
          <div className="tval tnum good">{pct(metrics.saathi_waste_rate)}</div>
          <div className="tlabel">of trips wasted, with Saathi</div>
          <div className="tdelta">
            ↓ {pct(metrics.baseline_waste_rate - metrics.saathi_waste_rate)} absolute
          </div>
        </div>
        <div className="tile">
          <div className="tval tnum">{inr.format(metrics.non_medical_cost_avoided_inr)}</div>
          <div className="tlabel">fares, lodging and lost wages not spent</div>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <Disclosure summary="How these two numbers are produced">
          <div style={{ fontSize: 13, color: "var(--ink-2)", letterSpacing: 0, maxWidth: "72ch" }}>
            <p style={{ margin: "0 0 8px" }}>
              <b>The baseline</b> is what happens now: the family is given a follow-up
              date at a fixed interval after the previous step, and travels on it
              whether or not the prerequisites landed.
            </p>
            <p style={{ margin: "0 0 8px" }}>
              <b>Saathi's number</b> is the same cohort with the same ground truth, but
              the family travels only on a date the prerequisite gate returned GO for.
            </p>
            <p style={{ margin: 0 }}>
              Both are counted against the generator's planted ready-dates, so neither
              side is scored by the model that produced it.
            </p>
          </div>
        </Disclosure>
      </div>
    </Card>
  );
}
