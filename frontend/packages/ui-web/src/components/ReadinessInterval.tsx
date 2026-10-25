import type { ReadinessWindow } from "@saathi/api-client";
import { daysBetween, fmtDay, fmtDayDate, parseDay, pct, queueLabel, today } from "../format";
import { Meter, Notice } from "../primitives";

/**
 * A readiness window, drawn as an interval rather than a date.
 *
 * The chart exists to make one thing unmistakable: Saathi is giving a range
 * with a stated coverage level, not a promise. One series, one hue, two
 * labels — the range itself and today. Everything else is axis.
 */

const DAY = 86_400_000;
const addDays = (d: Date, n: number) => new Date(d.getTime() + n * DAY);

export function ReadinessInterval({
  window: w,
  queue,
}: {
  window: ReadinessWindow;
  queue: string | null;
}) {
  const q = queueLabel(queue);
  if (!w.calibrated) {
    return (
      <div style={{ marginTop: 10 }}>
        <Notice tone="calm">
          No interval shown. {w.n_calibration} comparable case
          {w.n_calibration === 1 ? "" : "s"} in{" "}
          {q ? <>the <b>{q}</b> queue</> : "this queue"} is too few to stand behind
          a range, and a range Saathi cannot stand behind is worse than none.
        </Notice>
      </div>
    );
  }

  const now = today();
  const earliest = parseDay(w.earliest);
  const latest = parseDay(w.latest);

  // The domain always contains today, so the reader can see how far off the
  // window is rather than just how wide it is.
  const lo = new Date(Math.min(now.getTime(), earliest.getTime()));
  const hi = new Date(Math.max(now.getTime(), latest.getTime()));
  const pad = Math.max(1, Math.round(Math.max(1, daysBetween(lo, hi)) * 0.14));
  const domLo = addDays(lo, -pad);
  const domHi = addDays(hi, pad);
  const total = Math.max(1, daysBetween(domLo, domHi));
  const at = (d: Date) => (daysBetween(domLo, d) / total) * 100;

  const left = at(earliest);
  const width = Math.max(at(latest) - left, 1.5);
  const sameMonth = earliest.getMonth() === latest.getMonth();
  const range = sameMonth
    ? `${earliest.getDate()} – ${fmtDay(w.latest)}`
    : `${fmtDay(w.earliest)} – ${fmtDay(w.latest)}`;

  return (
    <div className="window-chart">
      <div className="axis">
        <span>{fmtDayDate(domLo)}</span>
        <span>{fmtDayDate(domHi)}</span>
      </div>
      <div
        className="window-track"
        role="img"
        aria-label={`Expected ready between ${w.earliest} and ${w.latest}, ${pct(
          1 - w.alpha,
        )} coverage`}
      >
        <div
          className="window-bar"
          style={{ left: `${left}%`, width: `${width}%` }}
          title={`${fmtDay(w.earliest)} – ${fmtDay(w.latest)} · ${pct(1 - w.alpha)} coverage · n = ${w.n_calibration}`}
        />
        <div className="window-today" style={{ left: `${at(now)}%` }}>
          <span>today</span>
        </div>
      </div>
      <div className="window-legend">
        <span className="key">
          <i />
          Expected ready <b style={{ fontWeight: 590, color: "var(--ink)" }}>{range}</b>
        </span>
        <Meter value={1 - w.alpha} label={`${pct(1 - w.alpha)} coverage`} />
        <span>n = {w.n_calibration} past cases</span>
      </div>
    </div>
  );
}
