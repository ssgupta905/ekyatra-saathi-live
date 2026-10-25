/**
 * Display vocabulary.
 *
 * The backend speaks in closed enums; a navigator reads English. Every mapping
 * is one-way and total, so a new enum value shows up as itself rather than as a
 * blank cell.
 */

import type { CareStep, StepStatus } from "@saathi/api-client";

const STEP_NAMES: Record<string, string> = {
  consult: "First consult",
  biopsy: "Biopsy",
  bloods: "Blood tests",
  scan: "Scan",
  pathology_report: "Pathology report",
  radiology_report: "Radiology report",
  review_consult: "Review consult",
  treatment: "Treatment",
};

const STATUS_LABELS: Record<StepStatus, string> = {
  not_scheduled: "Not scheduled",
  scheduled: "Scheduled",
  completed: "Done",
  pending_result: "Awaiting result",
  result_available: "Result ready",
  cancelled: "Cancelled",
};

/** Status tone. `go` means "this is no longer in the family's way". */
const STATUS_TONES: Record<StepStatus, "go" | "wait" | "neutral" | "critical"> = {
  not_scheduled: "neutral",
  scheduled: "neutral",
  completed: "go",
  pending_result: "wait",
  result_available: "go",
  cancelled: "critical",
};

/** Steps that produce a result rather than requiring the family to travel. */
const REPORT_STEPS = new Set(["pathology_report", "radiology_report"]);

export const stepName = (kind: string) => STEP_NAMES[kind] ?? humanize(kind);
export const statusLabel = (s: StepStatus) => STATUS_LABELS[s] ?? humanize(s);
export const statusTone = (s: StepStatus) => STATUS_TONES[s] ?? "neutral";
export const isReportStep = (kind: string) => REPORT_STEPS.has(kind);

export function humanize(s: string) {
  const spaced = s.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** A step is satisfied when nothing further has to happen for it. */
export const isSatisfied = (step: CareStep) =>
  step.status === "completed" || step.status === "result_available";

const DAY = 86_400_000;

/** Parse a backend `date` (YYYY-MM-DD) as a local midnight, not a UTC one. */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

/**
 * "Today" means the simulated day, not the wall clock.
 *
 * The world runs on its own calendar, so a travel date two simulated days ahead
 * must read "in 2 days" even when the operator's machine says otherwise. One
 * module-level value rather than a context: the console only ever watches one
 * world, and threading a clock through every date in every card would be a lot
 * of plumbing to express a single fact.
 */
let simToday: Date | null = null;

export function setSimToday(iso: string | null) {
  simToday = iso ? parseDay(iso) : null;
}

export const today = () => {
  if (simToday) return simToday;
  const n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
};

export const daysBetween = (a: Date, b: Date) => Math.round((b.getTime() - a.getTime()) / DAY);

const DATE_FMT = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
});
const DAY_FMT = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" });

export const fmtDate = (iso: string | null) => (iso ? DATE_FMT.format(parseDay(iso)) : "—");
export const fmtDay = (iso: string) => DAY_FMT.format(parseDay(iso));
/** Same as `fmtDay`, for a `Date` already in local time (no UTC round-trip). */
export const fmtDayDate = (d: Date) => DAY_FMT.format(d);

/** "in 4 days" / "3 days ago" / "today" — always relative to local midnight. */
export function fmtWhen(iso: string): string {
  const n = daysBetween(today(), parseDay(iso));
  if (n === 0) return "today";
  if (n === 1) return "tomorrow";
  if (n === -1) return "yesterday";
  return n > 0 ? `in ${n} days` : `${-n} days ago`;
}

export const fmtStamp = (iso: string) =>
  new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));

export const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export const pct = (x: number) => `${Math.round(x * 100)}%`;

const SOURCE_LABELS: Record<string, string> = {
  abdm: "ABDM record",
  hospital_feed: "Hospital feed",
  caregiver_reply: "Caregiver said",
  navigator: "Navigator entry",
  derived: "Saathi model",
};

export const sourceLabel = (s: string) => SOURCE_LABELS[s] ?? humanize(s);

/** Queue ids arrive as enum slugs; a navigator reads them as words. */
export const queueLabel = (q: string | null) => (q ? q.replace(/_/g, " ") : null);
