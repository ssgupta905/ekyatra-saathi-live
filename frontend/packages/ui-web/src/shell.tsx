import { useEffect, type ReactNode } from "react";
import type { LiveSnapshot, Role } from "@saathi/api-client";
import { fmtDate, setSimToday } from "./format";
import { Shield } from "./icons";

/**
 * Who is acting in this app. Until login exists (Step 5) each app is configured
 * with one person for its role; the server still decides what that role may do.
 */
export interface StaffIdentity {
  name: string;
  title: string;
  role: Role;
}

/**
 * The clock, in the chrome where it cannot scroll out of sight.
 *
 * It *shows* time; it does not control it. The pulse says whether the world is
 * moving and whether this app is still connected to it, because a frozen page and
 * a paused world look identical otherwise and only one of them is fine. Controls
 * for the demo clock are passed in as `children`, and only the demo stage has any.
 */
export function ClockDisplay({
  snapshot,
  connected,
  children,
}: {
  snapshot: LiveSnapshot | null;
  connected: boolean;
  children?: ReactNode;
}) {
  if (!snapshot) {
    return (
      <span className="clock">
        <span className="pulse off" />
        <span className="when">
          <span className="date">connecting…</span>
          <span className="day">live world</span>
        </span>
      </span>
    );
  }

  const running = snapshot.running;
  const pulse = !connected ? "lost" : running ? "on" : "off";

  return (
    <span className="clock">
      <span
        className={`pulse ${pulse}`}
        title={
          !connected
            ? "not receiving events"
            : running
              ? `running · one day every ${snapshot.seconds_per_day}s`
              : "paused"
        }
      />
      <span className="when">
        <span className="date">{fmtDate(snapshot.current)}</span>
        <span className="day">
          day {snapshot.day} · {snapshot.pending_reports} reports pending
        </span>
      </span>
      {children}
    </span>
  );
}

/**
 * The frame every staff app shares: brand, the app's own name, the clock, who is
 * signed in, and the scope boundary. What goes inside is the app's business.
 */
export function AppShell({
  app,
  identity,
  snapshot,
  connected,
  status,
  children,
}: {
  /** "Navigator", "Desk"... shown beside the brand and in the tab title. */
  app: string;
  identity: StaffIdentity;
  snapshot: LiveSnapshot | null;
  connected: boolean;
  /** Chips for the right of the header, e.g. how many are waiting on a person. */
  status?: ReactNode;
  children: ReactNode;
}) {
  useEffect(() => {
    document.title = `Saathi ${app} — ${identity.name}`;
  }, [app, identity.name]);

  // "Yesterday", "in 3 days" and "2 days ago" are relative to the hospital's day,
  // which in a demo is the simulated one. Set during render, before the children
  // below format their dates, so the first paint is already right.
  setSimToday(snapshot?.current ?? null);

  return (
    <div className="hx-app">
      <header className="hx-top">
        <div className="hx-brand">
          <span className="name">Saathi</span>
          <span className="sub">{app}</span>
        </div>

        <ClockDisplay snapshot={snapshot} connected={connected} />

        <span className="spacer" />
        {status}

        <span className="hx-who">
          <span className="hint">Signed in as</span>
          <strong>{identity.name}</strong>
          <span className="hint">{identity.title}</span>
        </span>

        <span className="boundary" title="The scope boundary, enforced in code">
          <Shield size={13} />
          Logistics only
        </span>
      </header>
      {children}
    </div>
  );
}
