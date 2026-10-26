import { useEffect, useMemo, useRef, useState } from "react";
import { LANGUAGE_NAMES, type Alert, type PendingOption, type Patient, type PlanBoard } from "@saathi/api-client";
import { DecisionGlyph, fmtDate } from "@saathi/ui-web";
import { FilterChips } from "../ui/kit";
import { SearchIcon } from "../ui/icons";

type Filter = "all" | "decide" | "call" | "soon" | "waiting";

/**
 * Every family, findable. Filters answer the questions a navigator actually asks
 * ("who needs me", "who is travelling"), and the order is the same plain one as
 * everywhere: what is in their way, then how far they would travel. No score.
 */
export function FamilyList({
  patients,
  boards,
  alerts,
  pending,
  selectedId,
  today,
  onSelect,
}: {
  patients: Patient[];
  boards: PlanBoard[];
  alerts: Alert[];
  pending: PendingOption[];
  selectedId: string | null;
  today: string | null;
  onSelect: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const list = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const byId = useMemo(() => new Map(boards.map((b) => [b.patient.id, b])), [boards]);
  const alerted = useMemo(() => new Set(alerts.map((a) => a.patient_id)), [alerts]);
  const deciding = useMemo(() => new Set(pending.map((p) => p.patient_id)), [pending]);
  const soonLimit = today ? Date.parse(today) + 3 * 86_400_000 : Infinity;

  const matches = (p: Patient, f: Filter) => {
    const b = byId.get(p.id);
    if (f === "decide") return deciding.has(p.id);
    if (f === "call") return alerted.has(p.id);
    if (f === "soon") return b?.decision === "go" && !!b.travel_on && Date.parse(b.travel_on) <= soonLimit;
    if (f === "waiting") return !!b && b.decision !== "go" && b.waiting_on.length > 0;
    return true;
  };

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rank = { uncertain: 0, wait: 1, go: 2 } as Record<string, number>;
    return patients
      .filter((p) => matches(p, filter))
      .filter((p) => !q || p.id.toLowerCase().includes(q) || (p.name ?? "").toLowerCase().includes(q) || p.home_district.toLowerCase().includes(q))
      .sort((a, b) => {
        const flag = (p: Patient) => (deciding.has(p.id) || alerted.has(p.id) ? 0 : 1);
        return (
          flag(a) - flag(b) ||
          (rank[byId.get(a.id)?.decision ?? ""] ?? 3) - (rank[byId.get(b.id)?.decision ?? ""] ?? 3) ||
          b.home_distance_km - a.home_distance_km
        );
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patients, query, filter, byId, alerted, deciding]);

  const count = (f: Filter) => patients.filter((p) => matches(p, f)).length;

  // Keep the open family in view when it was opened from elsewhere (Today, ⌘K).
  useEffect(() => {
    list.current
      ?.querySelector<HTMLElement>(`[data-patient="${CSS.escape(selectedId ?? "")}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [selectedId, rows.length]);

  return (
    <aside className="fam-list" aria-label="Families">
      <div className="fam-list-head">
        <label className="fam-search">
          <SearchIcon />
          <input value={query} placeholder="Name, id or district" onChange={(e) => setQuery(e.target.value)} />
        </label>
        <FilterChips<Filter>
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All", count: patients.length },
            { value: "decide", label: "Decide", count: count("decide") },
            { value: "call", label: "Call", count: count("call") },
            { value: "soon", label: "Travelling", count: count("soon") },
            { value: "waiting", label: "Waiting", count: count("waiting") },
          ]}
        />
      </div>
      <div className="fam-rows" ref={list}>
        {rows.length === 0 && <p className="empty">No family matches.</p>}
        {rows.map((p) => {
          const b = byId.get(p.id);
          return (
            <button
              key={p.id}
              type="button"
              className={p.id === selectedId ? "fam-row on" : "fam-row"}
              aria-pressed={p.id === selectedId}
              onClick={() => onSelect(p.id)}
              data-patient={p.id}
            >
              <span className={`fam-glyph ${b?.decision ?? "none"}`}>
                {b?.decision ? <DecisionGlyph decision={b.decision} size={14} /> : null}
              </span>
              <span className="fam-text">
                <strong>{p.name || p.id}</strong>
                <span>
                  {p.name ? `${p.id} · ` : ""}
                  {p.home_district} · {Math.round(p.home_distance_km)} km · {LANGUAGE_NAMES[p.language]}
                </span>
              </span>
              <span className="fam-flags">
                {deciding.has(p.id) && <span className="fam-flag wait">decide</span>}
                {alerted.has(p.id) && <span className="fam-flag critical">call</span>}
                {b?.decision === "go" && b.travel_on && <span className="fam-flag go">{fmtDate(b.travel_on)}</span>}
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
