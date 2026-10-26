import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  api,
  boards as boardsApi,
  config,
  disruptions,
  live,
  registry,
  reports,
  type Alert,
  type DeskCandidate,
  type Disruption,
  type PendingOption,
  type PlanBoard,
  type ReportList,
} from "@saathi/api-client";
import { DecisionGlyph, fmtDate, stepName } from "@saathi/ui-web";
import { usePersona } from "../session";
import { EmptyState, Panel, Pill, SkeletonRows, StatTile } from "../ui/kit";
import * as I from "../ui/icons";
import { useWorld } from "../world";

type Go = (section: string) => void;
type Open = (patientId: string, layer?: string) => void;

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

const firstName = (name: string) => name.replace(/^Dr\.?\s+/i, "Dr ").split(" ").slice(0, name.startsWith("Dr") ? 2 : 1).join(" ");

/**
 * Where each role's day starts: a handful of numbers that each lead somewhere,
 * and the short list of things that need this person now. Everything else is a
 * click away, and nothing here is a score.
 */
export function Today({ go, open }: { go: Go; open: Open }) {
  const { persona } = usePersona();
  const world = useWorld();
  const day = world.snapshot ? fmtDate(world.snapshot.current) : "";

  return (
    <div className="today">
      <header className="today-head">
        <div>
          <p className="today-day">{day}</p>
          <h1>
            {greeting()}, {firstName(persona.name)}
          </h1>
        </div>
      </header>
      {persona.role === "navigator" && <NavigatorToday go={go} open={open} />}
      {persona.role === "desk" && <DeskToday go={go} open={open} />}
      {persona.role === "doctor" && <DoctorToday go={go} open={open} />}
      {persona.role === "admin" && <AdminToday go={go} open={open} />}
    </div>
  );
}

function useCohort() {
  const world = useWorld();
  const [boards, setBoards] = useState<PlanBoard[] | null>(null);
  const [pending, setPending] = useState<PendingOption[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  useEffect(() => {
    boardsApi.all({ everyone: true }).then((r) => setBoards(r.boards)).catch(() => setBoards([]));
    disruptions.pending().then(setPending).catch(() => setPending([]));
    api.alerts().then(setAlerts).catch(() => setAlerts([]));
  }, [world.cohortRevision]);
  return { boards, pending, alerts };
}

function Row({ title, sub, aside, onClick, glyph }: { title: ReactNode; sub?: ReactNode; aside?: ReactNode; onClick: () => void; glyph?: ReactNode }) {
  return (
    <button type="button" className="today-row" onClick={onClick}>
      {glyph && <span className="today-row-glyph">{glyph}</span>}
      <span className="today-row-text">
        <strong>{title}</strong>
        {sub && <span>{sub}</span>}
      </span>
      {aside}
      <I.ChevronRight />
    </button>
  );
}

function soon(boards: PlanBoard[] | null, days: number, todayIso: string | undefined) {
  if (!boards) return [];
  // The hospital's day, which in a demo is the simulated one.
  const today = todayIso ? Date.parse(todayIso) : Date.now();
  return boards
    .filter((b) => b.decision === "go" && b.travel_on && (Date.parse(b.travel_on) - today) / 86_400_000 <= days)
    .sort((a, b) => (a.travel_on ?? "").localeCompare(b.travel_on ?? ""));
}

function NavigatorToday({ go, open }: { go: Go; open: Open }) {
  const { boards, pending, alerts } = useCohort();
  const world = useWorld();
  const mine = (pending ?? []).filter((p) => !p.requires_doctor);
  const travelling = soon(boards, 3, world.snapshot?.current);
  const waiting = (boards ?? []).filter((b) => b.decision !== "go" && b.waiting_on.length > 0);
  const loading = boards === null;

  return (
    <>
      <div className="today-tiles">
        <StatTile label="Need your decision" value={mine.length} tone={mine.length ? "wait" : "go"} icon={<I.Approve />}
          hint={pending && pending.length > mine.length ? `${pending.length - mine.length} more wait on a doctor` : "re-plans after a disruption"}
          onClick={() => go("approvals")} loading={pending === null} />
        <StatTile label="Need a person" value={alerts?.length ?? "–"} tone={alerts?.length ? "critical" : "go"} icon={<I.Alert />}
          hint="a question Saathi may not answer, or a family gone quiet" onClick={() => go("cohort")} loading={alerts === null} />
        <StatTile label="Travelling soon" value={travelling.length} tone="brand" icon={<I.Users />}
          hint="cleared to travel in the next three days" onClick={() => go("families")} loading={loading} />
        <StatTile label="Waiting on something" value={waiting.length} tone="neutral" icon={<I.FileText />}
          hint="a report or a step still outstanding" onClick={() => go("reports")} loading={loading} />
      </div>

      <div className="today-cols">
        <Panel title="Needs you now" hint="Decisions and questions, oldest first">
          {pending === null || alerts === null ? (
            <SkeletonRows />
          ) : mine.length + alerts.length === 0 ? (
            <EmptyState title="Nothing waiting on you" icon={<I.Approve />}>Every family is on a plan Saathi can state.</EmptyState>
          ) : (
            <div className="today-list">
              {mine.map((p) => (
                <Row key={`p-${p.patient_id}`} glyph={<Pill tone="wait">Decide</Pill>} title={p.patient_id}
                  sub={`${p.option_count} ranked options after a disruption`} onClick={() => go("approvals")} />
              ))}
              {alerts.map((a) => (
                <Row key={`a-${a.id}`} glyph={<Pill tone="critical">Call</Pill>} title={a.patient_id}
                  sub={a.kind.replace(/_/g, " ")} onClick={() => open(a.patient_id, "family")} />
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Travelling soon" hint="Families cleared to travel, by date">
          {loading ? (
            <SkeletonRows />
          ) : travelling.length === 0 ? (
            <EmptyState title="No journeys in the next three days" icon={<I.Users />} />
          ) : (
            <div className="today-list">
              {travelling.slice(0, 7).map((b) => (
                <Row key={b.patient.id} glyph={<span className="today-glyph go"><DecisionGlyph decision="go" size={14} /></span>}
                  title={b.patient.id} sub={`${b.patient.district} · ${b.patient.distance_km} km`}
                  aside={<Pill tone="go">{fmtDate(b.travel_on)}</Pill>} onClick={() => open(b.patient.id)} />
              ))}
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}

function useDesk() {
  const world = useWorld();
  const [list, setList] = useState<ReportList | null>(null);
  const [queue, setQueue] = useState<DeskCandidate[] | null>(null);
  const [outages, setOutages] = useState<Disruption[] | null>(null);
  useEffect(() => {
    reports.list().then(setList).catch(() => setList(null));
    live.deskQueue().then(setQueue).catch(() => setQueue([]));
    disruptions.list().then(setOutages).catch(() => setOutages([]));
  }, [world.cohortRevision]);
  return { list, queue, outages };
}

function DeskToday({ go, open }: { go: Go; open: Open }) {
  const { list, queue, outages } = useDesk();
  const counts = list?.counts ?? {};
  const urgent = (list?.reports ?? []).filter((r) => r.state === "overdue" || r.state === "due");

  return (
    <>
      <div className="today-tiles">
        <StatTile label="Overdue reports" value={counts.overdue ?? 0} tone={counts.overdue ? "critical" : "go"} icon={<I.FileText />}
          hint="past the window they should have landed in" onClick={() => go("reports")} loading={!list} />
        <StatTile label="Due now" value={counts.due ?? 0} tone="wait" icon={<I.Inbox />}
          hint="inside their window today" onClick={() => go("releases")} loading={!list} />
        <StatTile label="To confirm" value={queue?.length ?? "–"} tone={queue?.length ? "wait" : "go"} icon={<I.Approve />}
          hint="releases waiting on the desk" onClick={() => go("releases")} loading={queue === null} />
        <StatTile label="Outages in force" value={outages?.length ?? "–"} tone={outages?.length ? "wait" : "go"} icon={<I.Alert />}
          hint="machines, people or supplies down" onClick={() => go("issues")} loading={outages === null} />
      </div>

      <div className="today-cols">
        <Panel title="Reports to chase" hint="Overdue first, then due today" actions={<button type="button" className="btn small" onClick={() => go("reports")}>All reports</button>}>
          {!list ? (
            <SkeletonRows />
          ) : urgent.length === 0 ? (
            <EmptyState title="Nothing to chase" icon={<I.FileText />}>Every pending report is inside its window.</EmptyState>
          ) : (
            <div className="today-list">
              {urgent.slice(0, 8).map((r) => (
                <Row key={r.step_id} glyph={<Pill tone={r.state === "overdue" ? "critical" : "wait"}>{r.state === "overdue" ? "Overdue" : "Due"}</Pill>}
                  title={`${stepName(r.kind)} · ${r.patient_name || r.patient_id}`}
                  sub={r.window ? `expected ${fmtDate(r.window.earliest)} – ${fmtDate(r.window.latest)}` : r.queue}
                  onClick={() => open(r.patient_id, "reports")} />
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Something went wrong?" hint="Tell the planner in the words you'd use in the log">
          <div className="today-cta">
            <p>An outage is reported once, here, and every affected family is told not to travel before anyone works out a new date.</p>
            <button type="button" className="btn primary" onClick={() => go("issues")}>Report an issue</button>
          </div>
          {outages && outages.length > 0 && (
            <div className="today-list">
              {outages.map((d) => (
                <Row key={d.id} glyph={<Pill tone="wait">Down</Pill>} title={d.resource_id}
                  sub={d.unavailable_to ? `until ${fmtDate(d.unavailable_to)}` : "until further notice"} onClick={() => go("issues")} />
              ))}
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}

function DoctorToday({ go }: { go: Go; open: Open }) {
  const { pending } = useCohort();
  const mine = (pending ?? []).filter((p) => p.requires_doctor);
  return (
    <>
      <div className="today-tiles">
        <StatTile label="Waiting on a doctor" value={mine.length} tone={mine.length ? "wait" : "go"} icon={<I.Approve />}
          hint="re-plans that touch treatment or a dose date" onClick={() => go("approvals")} loading={pending === null} />
        <StatTile label="All re-plans pending" value={pending?.length ?? "–"} tone="neutral" icon={<I.Users />}
          hint="including those a navigator can approve" onClick={() => go("approvals")} loading={pending === null} />
      </div>
      <Panel title="Decisions only you can make" hint="A navigator cannot approve these; the server refuses it">
        {pending === null ? (
          <SkeletonRows />
        ) : mine.length === 0 ? (
          <EmptyState title="Nothing waiting on you" icon={<I.Approve />}>No re-plan touching treatment is pending.</EmptyState>
        ) : (
          <div className="today-list">
            {mine.map((p) => (
              <Row key={p.patient_id} glyph={<Pill tone="wait">Review</Pill>} title={p.patient_id}
                sub={`${p.option_count} ranked options · raised ${fmtDate(p.created_at.slice(0, 10))}`} onClick={() => go("approvals")} />
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

function AdminToday({ go }: { go: Go; open: Open }) {
  const world = useWorld();
  const [audit, setAudit] = useState<{ total: number; intact: boolean; recent: { claim: string; by?: string; at: string }[] } | null>(null);
  const [hospitals, setHospitals] = useState<{ id: string; name: string; inForce: boolean; version: number }[] | null>(null);
  const [on, setOn] = useState<string[] | null>(null);

  useEffect(() => {
    config
      .audit({ limit: 5 })
      .then((p) =>
        setAudit({
          total: p.total,
          intact: p.intact,
          recent: p.entries.map((e) => ({ claim: e.claim, by: (e.metadata.by ?? e.metadata.confirmed_by) as string | undefined, at: e.recorded_at })),
        }),
      )
      .catch(() => setAudit(null));
    registry
      .hospitals()
      .then((hs) => Promise.all(hs.map((h) => config.rules(h.id).then((r) => ({ id: h.id, name: h.name, inForce: r.used_by_planner, version: r.version })))))
      .then(setHospitals)
      .catch(() => setHospitals([]));
    config
      .integrations()
      .then((i) =>
        setOn(
          [
            i.login.on && "login",
            i.language_layer && "language layer",
            i.actors && "actors",
            i.feeds.abdm && "ABDM",
            i.channels.whatsapp && "WhatsApp",
          ].filter(Boolean) as string[],
        ),
      )
      .catch(() => setOn([]));
  }, [world.cohortRevision]);

  const inForce = useMemo(() => hospitals?.filter((h) => h.inForce).length ?? 0, [hospitals]);

  return (
    <>
      <div className="today-tiles">
        <StatTile label="Audit trail" value={audit ? audit.total : "–"} tone={audit && !audit.intact ? "critical" : "go"} icon={<I.Ledger />}
          hint={audit ? (audit.intact ? "entries · chain intact" : "CHAIN BROKEN") : "loading"} onClick={() => go("audit")} loading={!audit} />
        <StatTile label="Hospital rules in force" value={hospitals ? `${inForce}/${hospitals.length}` : "–"} tone={inForce ? "go" : "wait"} icon={<I.Sliders />}
          hint="hospitals planned on their own saved rules" onClick={() => go("config")} loading={!hospitals} />
        <StatTile label="Families on record" value={world.snapshot?.patients ?? "–"} tone="brand" icon={<I.Users />}
          hint={`${world.snapshot?.pending_reports ?? 0} reports pending`} onClick={() => go("families")} />
        <StatTile label="Switched on" value={on ? on.length : "–"} tone="neutral" icon={<I.Building />}
          hint={on?.length ? on.join(" · ") : "integrations off"} onClick={() => go("config")} loading={!on} />
      </div>

      <div className="today-cols">
        <Panel title="Latest changes" hint="From the audit log" actions={<button type="button" className="btn small" onClick={() => go("audit")}>Open audit log</button>}>
          {!audit ? (
            <SkeletonRows />
          ) : (
            <div className="today-list">
              {audit.recent.map((r, i) => (
                <Row key={i} title={r.claim} sub={`${r.by ?? "system"} · ${new Date(r.at).toLocaleString()}`} onClick={() => go("audit")} />
              ))}
            </div>
          )}
        </Panel>
        <Panel title="Hospitals" hint="Whether each is planned on its own rules">
          {!hospitals ? (
            <SkeletonRows />
          ) : (
            <div className="today-list">
              {hospitals.map((h) => (
                <Row key={h.id} title={h.name} sub={h.id}
                  aside={<Pill tone={h.inForce ? "go" : "neutral"}>{h.inForce ? `rules v${h.version}` : "built-in"}</Pill>}
                  onClick={() => go("config")} />
              ))}
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
