import { useEffect, useState, type ReactNode } from "react";
import { ActivityStrip, AgentStatus, Shield, fmtDate, setSimToday } from "@saathi/ui-web";
import { CommandPalette } from "./CommandPalette";
import { usePersona } from "./session";
import { GROUPS, sectionsFor, type Section } from "./sections";
import { ICONS } from "./ui/navIcons";
import { Drawer } from "./ui/kit";
import * as I from "./ui/icons";
import { useWorld } from "./world";


const initials = (name: string) =>
  name
    .replace(/^Dr\.?\s+/i, "")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

/**
 * The frame: a navigation rail with only this role's work, a quiet top bar
 * (the hospital's day, search, what the system is doing), and the page. What
 * the system is doing right now lives one click away in a drawer rather than
 * permanently on screen: it matters when you ask, and is noise when you don't.
 */
export function Shell({
  current,
  onNavigate,
  onOpenFamily,
  children,
}: {
  current: string;
  onNavigate: (section: string) => void;
  onOpenFamily: (patientId: string) => void;
  children: ReactNode;
}) {
  const { persona, mode, switchPersona } = usePersona();
  const world = useWorld();
  const demo = (world.snapshot?.world ?? "demo") === "demo";
  const sections = sectionsFor(persona.role, demo);
  const here: Section | undefined = sections.find((s) => s.id === current);
  const [palette, setPalette] = useState(false);
  const [activity, setActivity] = useState(false);

  setSimToday(world.snapshot?.current ?? null);

  useEffect(() => {
    document.title = `${here?.label ?? "Saathi"} · Saathi Control Centre`;
  }, [here?.label]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const groups = (Object.keys(GROUPS) as Section["group"][])
    .map((g) => ({ g, items: sections.filter((s) => s.group === g) }))
    .filter((x) => x.items.length);
  const working = world.working.length;

  return (
    <div className="cc-app">
      <nav className="cc-rail" aria-label="Sections">
        <div className="cc-brand">
          <I.Logo />
          <div>
            <strong>Saathi</strong>
            <span>Control Centre</span>
          </div>
        </div>

        {groups.map(({ g, items }) => (
          <div className="cc-group" key={g}>
            <div className="cc-group-label">{GROUPS[g]}</div>
            {items.map((s) => (
              <button
                key={s.id}
                type="button"
                className={s.id === current ? "cc-nav-item on" : "cc-nav-item"}
                aria-current={s.id === current ? "page" : undefined}
                onClick={() => onNavigate(s.id)}
                data-section={s.id}
              >
                {ICONS[s.icon]()}
                <span>{s.label}</span>
              </button>
            ))}
          </div>
        ))}

        <div className="cc-rail-foot">
          <div className="cc-me">
            <span className="cc-avatar">{initials(persona.name)}</span>
            <div>
              <strong>{persona.name}</strong>
              <span>{persona.title}</span>
            </div>
          </div>
          <button type="button" className="cc-switch" onClick={switchPersona}>
            <I.LogOut />
            {mode === "real" ? "Sign out" : "Switch person"}
          </button>
        </div>
      </nav>

      <div className="cc-page">
        <header className="cc-top">
          <button type="button" className="cc-search" onClick={() => setPalette(true)}>
            <I.SearchIcon />
            <span>Search families or jump to a screen</span>
            <kbd>⌘K</kbd>
          </button>
          <span className="spacer" />
          <span className={`cc-world ${demo ? "demo" : "real"}`}>{demo ? "Demo world" : "Real records"}</span>
          <span className="cc-day" title={world.snapshot?.running ? "the clock is running" : "the clock is paused"}>
            <span className={`dot ${world.connected ? (world.snapshot?.running ? "on" : "idle") : "lost"}`} />
            {world.snapshot ? fmtDate(world.snapshot.current) : "connecting…"}
          </span>
          <button
            type="button"
            className={working ? "cc-live busy" : "cc-live"}
            onClick={() => setActivity(true)}
            aria-label="What the system is doing"
          >
            <I.Pulse />
            {working ? `${working} working` : "Live"}
          </button>
          <span className="cc-scope" title="The scope boundary, enforced in code">
            <Shield size={13} /> Logistics only
          </span>
        </header>

        <main className="cc-main" data-section={current}>
          {children}
        </main>
      </div>

      <CommandPalette
        open={palette}
        onClose={() => setPalette(false)}
        sections={sections}
        onSection={(id) => {
          setPalette(false);
          onNavigate(id);
        }}
        onFamily={(id) => {
          setPalette(false);
          onOpenFamily(id);
        }}
      />

      <Drawer open={activity} title="What the system is doing" onClose={() => setActivity(false)}>
        <AgentStatus working={world.working} events={world.events} />
        <ActivityStrip
          events={world.events}
          connected={world.connected}
          onSelect={(id) => {
            setActivity(false);
            onOpenFamily(id);
          }}
        />
      </Drawer>
    </div>
  );
}
