import { useEffect, useMemo, useRef, useState } from "react";
import { api, LANGUAGE_NAMES, type Patient } from "@saathi/api-client";
import type { Section } from "./sections";
import { ICONS } from "./ui/navIcons";
import { ChevronRight, Users } from "./ui/icons";

/**
 * ⌘K: type a family, a district or a screen, press Enter. The fastest way from
 * "Anita's daughter is on the phone" to Anita's plan.
 */
export function CommandPalette({
  open,
  onClose,
  sections,
  onSection,
  onFamily,
}: {
  open: boolean;
  onClose: () => void;
  sections: Section[];
  onSection: (id: string) => void;
  onFamily: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    api.patients().then(setPatients).catch(() => undefined);
    window.setTimeout(() => input.current?.focus(), 0);
  }, [open]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    const screens = sections
      .filter((s) => !q || s.label.toLowerCase().includes(q) || s.hint.toLowerCase().includes(q))
      .map((s) => ({ kind: "section" as const, id: s.id, title: s.label, sub: s.hint, icon: s.icon }));
    const families = patients
      .filter(
        (p) =>
          q &&
          (p.id.toLowerCase().includes(q) ||
            (p.name ?? "").toLowerCase().includes(q) ||
            p.home_district.toLowerCase().includes(q)),
      )
      .slice(0, 8)
      .map((p) => ({
        kind: "family" as const,
        id: p.id,
        title: p.name ? `${p.name} · ${p.id}` : p.id,
        sub: `${p.home_district} · ${Math.round(p.home_distance_km)} km · ${LANGUAGE_NAMES[p.language]}`,
        icon: null,
      }));
    return [...families, ...screens].slice(0, 12);
  }, [query, patients, sections]);

  if (!open) return null;

  const choose = (i: number) => {
    const r = results[i];
    if (!r) return;
    if (r.kind === "family") onFamily(r.id);
    else onSection(r.id);
  };

  return (
    <div className="ui-palette-wrap" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ui-palette" role="dialog" aria-label="Search">
        <input
          ref={input}
          value={query}
          placeholder="A family, a district, or a screen…"
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, results.length - 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            }
            if (e.key === "Enter") choose(active);
          }}
        />
        <ul>
          {results.map((r, i) => (
            <li key={`${r.kind}-${r.id}`}>
              <button
                type="button"
                className={i === active ? "on" : ""}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(i)}
              >
                <span className="ui-palette-icon">{r.kind === "family" ? <Users /> : ICONS[r.icon!]()}</span>
                <span className="ui-palette-text">
                  <strong>{r.title}</strong>
                  <span>{r.sub}</span>
                </span>
                <span className="ui-palette-kind">{r.kind === "family" ? "Family" : "Screen"}</span>
                <ChevronRight />
              </button>
            </li>
          ))}
          {results.length === 0 && <li className="ui-palette-empty">Nothing matches “{query}”.</li>}
        </ul>
        <footer>
          <kbd>↑</kbd><kbd>↓</kbd> to move · <kbd>Enter</kbd> to open · <kbd>Esc</kbd> to close
        </footer>
      </div>
    </div>
  );
}
