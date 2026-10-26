import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { auth, runtimeConfig, tokenStore } from "@saathi/api-client";
import { AuthGate, useSession } from "@saathi/auth";
import { Shield } from "@saathi/ui-web";
import { Logo } from "./ui/icons";
import { ROLE_GROUPS, ROLE_TITLES, ROSTER, STAFF_ROLES, rememberPersona, storedPersona, type Persona } from "./persona";

/**
 * Who is using the control centre, and how they got in.
 *
 * Two ways in, chosen by the server rather than by this page:
 * - **login on** (the real world): username and password, through the shared
 *   `AuthGate`. The persona is the signed-in account.
 * - **login off** (the demo): a "sign in as" page of named people. Nothing here
 *   is a security boundary; the server checks the role on every action it gates.
 */

interface PersonaValue {
  persona: Persona;
  /** "real" when a person signed in with a password. */
  mode: "demo" | "real";
  switchPersona: () => void;
}

const PersonaContext = createContext<PersonaValue | null>(null);

export function usePersona(): PersonaValue {
  const value = useContext(PersonaContext);
  if (!value) throw new Error("usePersona outside PersonaGate");
  return value;
}

export function PersonaGate({ children }: { children: ReactNode }) {
  const [required, setRequired] = useState<boolean | null>(null);

  useEffect(() => {
    auth
      .config()
      .then((c) => {
        if (!c.required) tokenStore.clear();
        setRequired(c.required);
      })
      .catch(() => setRequired(false));
  }, []);

  if (required === null) return <div className="cc-loading">Opening the control centre…</div>;
  if (required) {
    return (
      <AuthGate app="Control Centre" way="staff" roles={STAFF_ROLES}>
        <SignedIn>{children}</SignedIn>
      </AuthGate>
    );
  }
  return <DemoPersona>{children}</DemoPersona>;
}

function SignedIn({ children }: { children: ReactNode }) {
  const { principal, signOut } = useSession();
  const value = useMemo<PersonaValue | null>(
    () =>
      principal
        ? {
            persona: {
              id: principal.id,
              name: principal.name,
              role: principal.role,
              title: ROLE_TITLES[principal.role],
            },
            mode: "real",
            switchPersona: signOut,
          }
        : null,
    [principal, signOut],
  );
  if (!value) return null;
  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>;
}

function DemoPersona({ children }: { children: ReactNode }) {
  const [persona, setPersona] = useState<Persona | null>(storedPersona);
  const switchPersona = useCallback(() => {
    rememberPersona(null);
    setPersona(null);
  }, []);
  const choose = useCallback((p: Persona) => {
    rememberPersona(p);
    setPersona(p);
  }, []);

  const value = useMemo<PersonaValue | null>(
    () => (persona ? { persona, mode: "demo", switchPersona } : null),
    [persona, switchPersona],
  );

  if (!value) return <PersonaPicker onChoose={choose} />;
  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>;
}

function PersonaPicker({ onChoose }: { onChoose: (p: Persona) => void }) {
  const familyApp = runtimeConfig().apps?.family ?? "http://localhost:5180";
  return (
    <div className="cc-picker">
      <aside className="cc-picker-brand">
        <Logo size={40} />
        <h1>Saathi Control Centre</h1>
        <p>
          Readiness-driven visit planning for families travelling for cancer care. Each person
          sees the work their role does; the server decides what each role may do.
        </p>
        <p className="cc-scope">
          <Shield size={13} /> Logistics only · no results, no diagnosis, no advice
        </p>
      </aside>
      <div className="cc-picker-main">
      <header>
        <h2>Who are you today?</h2>
        <p>Demo world: pick a person from the brief. No password is needed here.</p>
      </header>

      {ROLE_GROUPS.map((group) => (
        <section key={group.role}>
          <h2>
            {group.label} <span>{group.does}</span>
          </h2>
          <div className="cc-cards">
            {ROSTER.filter((p) => p.role === group.role).map((p) =>
              p.role === "caregiver" ? (
                <a
                  key={p.id}
                  className="cc-card"
                  href={`${familyApp}/?patient=${encodeURIComponent(p.patientFocus ?? "")}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <strong>{p.name}</strong>
                  <span>{p.title}</span>
                  <em>opens the family app</em>
                </a>
              ) : (
                <button key={p.id} type="button" className="cc-card" onClick={() => onChoose(p)}>
                  <span className="cc-avatar">{p.name.replace(/^Dr\.?\s+/i, "").split(" ").map((w) => w[0]).slice(0, 2).join("")}</span>
                  <span className="cc-card-text">
                    <strong>{p.name}</strong>
                    <span>{p.title}</span>
                  </span>
                </button>
              ),
            )}
          </div>
        </section>
      ))}

      <p className="cc-foot">
        On real records this page asks for a username and password instead.
      </p>
      </div>
    </div>
  );
}
