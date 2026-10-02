import { useEffect, useMemo, useRef, useState } from "react";
import type { Alert, Patient } from "../lib/api";
import { LANGUAGE_NAMES } from "../lib/api";
import { ALERT_LABELS, ALERT_TONE } from "../lib/explain";
import { humanize } from "../lib/format";
import { Chip } from "../ui/primitives";
import { Search } from "../ui/icons";

/**
 * The call list.
 *
 * Rows carry the signals behind them and nothing else — no priority number, no
 * ordering by a score. Families with something open float to the top because
 * something is open, which is a fact, not a ranking.
 */
export function CallList({
  patients,
  alerts,
  watched,
  selectedId,
  onSelect,
}: {
  patients: Patient[];
  alerts: Alert[];
  /** Families the live world is rendering messages for and running actors on. */
  watched: string[];
  selectedId: string | null;
  onSelect: (p: Patient) => void;
}) {
  const [query, setQuery] = useState("");
  const watching = useMemo(() => new Set(watched), [watched]);
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());

  // The console opens on the first family in the cohort, which is rarely the
  // first row here — bring it into view rather than leaving the selection off-screen.
  useEffect(() => {
    if (!selectedId) return;
    rowRefs.current.get(selectedId)?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  const signals = useMemo(() => {
    const map = new Map<string, Alert[]>();
    for (const a of alerts) {
      const list = map.get(a.patient_id);
      if (list) list.push(a);
      else map.set(a.patient_id, [a]);
    }
    return map;
  }, [alerts]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matched = q
      ? patients.filter(
          (p) =>
            p.id.toLowerCase().includes(q) ||
            p.home_district.toLowerCase().includes(q) ||
            LANGUAGE_NAMES[p.language].toLowerCase().includes(q),
        )
      : patients;
    // Open signals first, then furthest from the hospital — the family for whom
    // a wasted journey costs the most.
    return [...matched].sort((a, b) => {
      const sa = signals.get(a.id)?.length ?? 0;
      const sb = signals.get(b.id)?.length ?? 0;
      if (sa !== sb) return sb - sa;
      return b.home_distance_km - a.home_distance_km;
    });
  }, [patients, query, signals]);

  return (
    <nav className="rail" aria-label="Call list">
      <div className="rail-head">
        <div className="title">Call list · {patients.length} families</div>
        <label style={{ position: "relative", display: "block" }}>
          <span
            style={{
              position: "absolute",
              left: 10,
              top: "50%",
              transform: "translateY(-50%)",
              color: "var(--ink-4)",
              display: "flex",
            }}
          >
            <Search />
          </span>
          <input
            className="search"
            style={{ paddingLeft: 30 }}
            placeholder="Family, district or language"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Filter the call list"
          />
        </label>
      </div>

      <div className="rail-list">
        {rows.length === 0 && (
          <p className="empty" style={{ padding: "12px 11px" }}>
            Nobody matches “{query}”.
          </p>
        )}
        {rows.map((p) => {
          const open = signals.get(p.id) ?? [];
          return (
            <button
              key={p.id}
              type="button"
              className="row"
              ref={(el) => {
                if (el) rowRefs.current.set(p.id, el);
                else rowRefs.current.delete(p.id);
              }}
              aria-pressed={selectedId === p.id}
              onClick={() => onSelect(p)}
            >
              <div className="row-top">
                <span className="pid">{p.id}</span>
                {watching.has(p.id) && (
                  <span
                    className="pulse on"
                    title="live: messages rendered and actors running for this family"
                  />
                )}
              </div>
              <div className="row-meta">
                {p.home_district} · {Math.round(p.home_distance_km)} km ·{" "}
                {LANGUAGE_NAMES[p.language]}
              </div>
              {open.length > 0 && (
                <div className="row-signals">
                  {open.slice(0, 2).map((a) => (
                    <Chip key={a.id} tone={ALERT_TONE[a.kind] ?? "neutral"}>
                      <span className="dot" />
                      {ALERT_LABELS[a.kind] ?? humanize(a.kind)}
                    </Chip>
                  ))}
                  {open.length > 2 && <Chip>+{open.length - 2}</Chip>}
                </div>
              )}
            </button>
          );
        })}
      </div>

      <div className="rail-foot">
        Families with an open signal are listed first, then by distance from the
        hospital. No priority score exists.
      </div>
    </nav>
  );
}
