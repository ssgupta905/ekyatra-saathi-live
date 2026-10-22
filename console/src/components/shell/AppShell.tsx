import type { ReactNode } from "react";
import type { LiveSnapshot } from "../../lib/api";
import type { Persona } from "../../lib/identity";
import { NAV, type NavIcon, type PageId } from "../../lib/nav";
import { ClockBar } from "../ClockBar";
import { RoleSwitcher } from "./RoleSwitcher";
import {
  Bell,
  CheckCircle,
  Doc,
  Grid,
  Inbox,
  People,
  Pin,
  Play,
  Shield,
  Wave,
} from "../../ui/icons";

const ICONS: Record<NavIcon, ReactNode> = {
  grid: <Grid size={17} />,
  people: <People size={17} />,
  check: <CheckCircle size={17} />,
  wave: <Wave size={17} />,
  play: <Play size={15} />,
  bell: <Bell size={17} />,
  inbox: <Inbox size={17} />,
  shield: <Shield size={17} />,
  doc: <Doc size={17} />,
  pin: <Pin size={17} />,
};

/**
 * One frame for every staff screen: a quiet top bar, a short list of pages on
 * the left, and exactly one page in the middle. Family-facing screens skip
 * the sidebar entirely — a caregiver has one question, not a menu.
 */
export function AppShell({
  persona,
  onChoosePersona,
  page,
  onNavigate,
  snapshot,
  connected,
  badges,
  children,
}: {
  persona: Persona;
  onChoosePersona: (id: string) => void;
  page: PageId;
  onNavigate: (page: PageId) => void;
  snapshot: LiveSnapshot | null;
  connected: boolean;
  /** Small counts shown beside nav items, e.g. decisions waiting. */
  badges?: Partial<Record<PageId, number>>;
  children: ReactNode;
}) {
  const items = NAV[persona.role];
  const staff = persona.role !== "caregiver" && persona.role !== "patient";

  return (
    <div className={staff ? "shell" : "shell no-nav"}>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">S</span>
          <span className="brand-name">Saathi</span>
        </div>
        <span className="spacer" />
        {staff && <ClockBar snapshot={snapshot} connected={connected} />}
        <RoleSwitcher persona={persona} onChoose={onChoosePersona} />
      </header>

      {staff && (
        <nav className="sidenav" aria-label="Pages">
          <div className="sidenav-items">
            {items.map((item) => {
              const count = badges?.[item.id];
              return (
                <button
                  key={item.id}
                  type="button"
                  className="sidenav-item"
                  aria-current={page === item.id ? "page" : undefined}
                  onClick={() => onNavigate(item.id)}
                  title={item.label}
                >
                  <span className="sidenav-icon">{ICONS[item.icon]}</span>
                  <span className="sidenav-label">{item.label}</span>
                  {count ? <span className="sidenav-count">{count}</span> : null}
                </button>
              );
            })}
          </div>
          <div className="sidenav-foot">
            <Shield size={13} />
            <span>Logistics only — never a result, a diagnosis or advice.</span>
          </div>
        </nav>
      )}

      <main className="main">{children}</main>
    </div>
  );
}

/** Title + the one question this page answers. Nothing else at the top. */
export function PageHeader({
  title,
  question,
  aside,
}: {
  title: string;
  question: string;
  aside?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{question}</p>
      </div>
      {aside && <div className="page-header-aside">{aside}</div>}
    </div>
  );
}
