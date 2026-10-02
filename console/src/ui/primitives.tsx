import {
  createContext,
  useContext,
  type ReactNode,
} from "react";
import type { Decision } from "../lib/api";
import { CheckCircle, Chevron, Clock, Question, Stop } from "./icons";

/* ── card ─────────────────────────────────────────────────────────────────── */

export function Card({
  title,
  hint,
  aside,
  flush,
  note,
  children,
}: {
  title?: string;
  hint?: string;
  aside?: ReactNode;
  /** Let the body run to the card edge — for tables and steppers. */
  flush?: boolean;
  /** A quiet footer: the standing caveat a reader should carry away. */
  note?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      {(title || aside) && (
        <header>
          {title && <h2>{title}</h2>}
          {hint && <span className="hint">{hint}</span>}
          <span className="spacer" />
          {aside}
        </header>
      )}
      <div className={flush ? "body flush" : "body"}>{children}</div>
      {note && <div className="card-note">{note}</div>}
    </section>
  );
}

/* ── decision vocabulary ──────────────────────────────────────────────────── */

export const DecisionGlyph = ({ decision, size = 15 }: { decision: Decision; size?: number }) =>
  decision === "go" ? (
    <CheckCircle size={size} />
  ) : decision === "wait" ? (
    <Clock size={size} />
  ) : (
    <Question size={size} />
  );

/* ── badge / chip ─────────────────────────────────────────────────────────── */

type Tone = "go" | "wait" | "uncertain" | "critical" | "neutral" | "info";

export const Badge = ({
  tone,
  solid,
  icon,
  children,
}: {
  tone: Tone;
  solid?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}) => (
  <span className={`badge ${tone}${solid ? " solid" : ""}`}>
    {icon}
    {children}
  </span>
);

export const Chip = ({ tone, children }: { tone?: Tone; children: ReactNode }) => (
  <span className={tone ? `chip ${tone}` : "chip"}>{children}</span>
);

/* ── disclosure ───────────────────────────────────────────────────────────── */

export const Disclosure = ({ summary, children }: { summary: string; children: ReactNode }) => (
  <details className="disclose">
    <summary>
      <Chevron />
      {summary}
    </summary>
    <div className="disclosed">{children}</div>
  </details>
);

/* ── notice ───────────────────────────────────────────────────────────────── */

export const Notice = ({
  tone,
  children,
}: {
  tone: "warn" | "stop" | "calm";
  children: ReactNode;
}) => (
  <div className={`notice ${tone}`} role={tone === "stop" ? "alert" : undefined}>
    {tone === "stop" ? <Stop /> : tone === "warn" ? <Clock /> : null}
    <div>{children}</div>
  </div>
);

/* ── meter: fill and track are two steps of one ramp ──────────────────────── */

export const Meter = ({ value, label }: { value: number; label: string }) => (
  <div className="meter">
    <div
      className="track"
      role="meter"
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <div className="fill" style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }} />
    </div>
    <span className="val">{label}</span>
  </div>
);

/* ── citations ────────────────────────────────────────────────────────────────
   A claim in the trace carries the ledger id it rests on. Clicking it scrolls
   the ledger row into view and flashes it, so "what is this based on" is one
   click rather than a cross-reference by eye.
   ------------------------------------------------------------------------- */

export const CiteContext = createContext<(ledgerId: string) => void>(() => undefined);

export function Cite({ ledgerId, children }: { ledgerId: string; children: ReactNode }) {
  const focus = useContext(CiteContext);
  return (
    <button
      type="button"
      className="cite"
      onClick={() => focus(ledgerId)}
      title={`Show ledger entry ${ledgerId}`}
    >
      {children}
    </button>
  );
}
