import { ROSTER, type Persona } from "../lib/identity";

/**
 * "Sign in as X" — client-side only. See `lib/identity.ts` for why this is
 * a demo convenience, not an authentication system.
 */
export function PersonaSwitcher({
  persona,
  onChoose,
}: {
  persona: Persona;
  onChoose: (id: string) => void;
}) {
  return (
    <label className="persona-switcher">
      <span className="hint">Signed in as</span>
      <select value={persona.id} onChange={(e) => onChoose(e.target.value)}>
        {ROSTER.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name} — {p.title}
          </option>
        ))}
      </select>
    </label>
  );
}
