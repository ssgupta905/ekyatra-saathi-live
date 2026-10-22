import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ROSTER, type Persona } from "../../lib/identity";
import type { Role } from "../../lib/api";
import { Chevron, Close } from "../../ui/icons";

/** The three groups from the brief's Figure 1 — who signs in. */
const GROUPS: { title: string; hint: string; roles: Role[] }[] = [
  { title: "Hospital staff", hint: "Navigators, desks and doctors", roles: ["navigator", "desk", "doctor"] },
  { title: "Patient and family", hint: "WhatsApp, voice and simple mode", roles: ["caregiver", "patient"] },
  { title: "Admin", hint: "Rules and the audit log", roles: ["admin"] },
];

export const initials = (name: string) =>
  name
    .replace(/^Dr\.?\s+/i, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

/**
 * "Sign in as" — a chip that opens a grouped picker. Client-side only: see
 * `lib/identity.ts` for why this is a demo convenience, not authentication.
 */
export function RoleSwitcher({
  persona,
  onChoose,
}: {
  persona: Persona;
  onChoose: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button type="button" className="role-chip" onClick={() => setOpen(true)}>
        <span className={`avatar role-${persona.role}`}>{initials(persona.name)}</span>
        <span className="role-chip-text">
          <span className="role-chip-name">{persona.name}</span>
          <span className="role-chip-title">{persona.title}</span>
        </span>
        <Chevron size={11} className="role-chip-chevron" />
      </button>

      {open &&
        // Portalled: the top bar's backdrop-filter would otherwise become the
        // containing block for this fixed overlay and clip it to the bar.
        createPortal(
        <div className="overlay" onClick={() => setOpen(false)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Sign in as"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-head">
              <div>
                <h2>Sign in as</h2>
                <p>Each person sees only the screens their role needs.</p>
              </div>
              <button type="button" className="icon-btn" onClick={() => setOpen(false)} aria-label="Close">
                <Close />
              </button>
            </div>

            <div className="modal-body">
              {GROUPS.map((group) => (
                <section key={group.title} className="persona-group">
                  <div className="persona-group-head">
                    <h3>{group.title}</h3>
                    <span>{group.hint}</span>
                  </div>
                  <div className="persona-grid">
                    {ROSTER.filter((p) => group.roles.includes(p.role)).map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        className="persona-card"
                        aria-pressed={p.id === persona.id}
                        onClick={() => {
                          onChoose(p.id);
                          setOpen(false);
                        }}
                      >
                        <span className={`avatar role-${p.role}`}>{initials(p.name)}</span>
                        <span className="persona-card-text">
                          <span className="persona-card-name">{p.name}</span>
                          <span className="persona-card-title">{p.title}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </div>
        </div>,
          document.body,
        )}
    </>
  );
}
