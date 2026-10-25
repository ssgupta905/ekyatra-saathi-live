import { useEffect, type ReactNode } from "react";
import { AgentStatus, ClockDisplay, Shield, setSimToday } from "@saathi/ui-web";
import { usePersona } from "./session";
import { sectionsFor, type Section } from "./sections";
import { useWorld } from "./world";

/**
 * The frame: who is signed in, the hospital's day, what the system is doing now,
 * and the screens this role uses down the left. Wide on purpose — this is the
 * hospital's control centre, read on a desk monitor, not the family's phone.
 */
export function Shell({
  current,
  onNavigate,
  children,
}: {
  current: string;
  onNavigate: (section: string) => void;
  children: ReactNode;
}) {
  const { persona, mode, switchPersona } = usePersona();
  const world = useWorld();
  const demo = (world.snapshot?.world ?? "demo") === "demo";
  const sections = sectionsFor(persona.role, demo);
  const here: Section | undefined = sections.find((s) => s.id === current);

  // Relative dates are relative to the hospital's day, the simulated one in a demo.
  setSimToday(world.snapshot?.current ?? null);

  useEffect(() => {
    document.title = `Saathi Control Centre — ${here?.label ?? ""} — ${persona.name}`;
  }, [here?.label, persona.name]);

  return (
    <div className="cc-app">
      <header className="cc-top">
        <div className="hx-brand">
          <span className="name">Saathi</span>
          <span className="sub">Control Centre</span>
        </div>
        <ClockDisplay snapshot={world.snapshot} connected={world.connected} />
        <span className={`cc-world ${demo ? "demo" : "real"}`}>
          {demo ? "Demo world" : "Real records"}
        </span>
        <span className="spacer" />
        <span className="hx-who">
          <span className="hint">{mode === "real" ? "Signed in as" : "Acting as"}</span>
          <strong>{persona.name}</strong>
          <span className="hint">{persona.title}</span>
        </span>
        <button type="button" className="btn small" onClick={switchPersona}>
          {mode === "real" ? "Sign out" : "Switch person"}
        </button>
        <span className="boundary" title="The scope boundary, enforced in code">
          <Shield size={13} />
          Logistics only · no results, no diagnosis, no advice
        </span>
      </header>

      <AgentStatus working={world.working} events={world.events} />

      <div className="cc-body">
        <nav className="cc-nav" aria-label="Sections">
          {sections.map((s) => (
            <button
              key={s.id}
              type="button"
              className={s.id === current ? "on" : ""}
              aria-current={s.id === current ? "page" : undefined}
              onClick={() => onNavigate(s.id)}
              title={s.hint}
            >
              {s.label}
            </button>
          ))}
        </nav>
        <main className="cc-main" data-section={current}>
          {here && (
            <div className="cc-heading">
              <h1>{here.label}</h1>
              <p>{here.hint}</p>
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
