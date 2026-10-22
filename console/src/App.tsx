import { useCallback, useEffect, useState } from "react";
import { api, type Patient } from "./lib/api";
import { useLiveWorld } from "./lib/live";
import { useIdentity } from "./lib/identity";
import { firstPage, NAV, navItem, type PageId } from "./lib/nav";
import { setSimToday } from "./lib/format";
import { AppShell } from "./components/shell/AppShell";
import { RoleSwitcher } from "./components/shell/RoleSwitcher";
import { PatientSimpleView } from "./components/PatientSimpleView";
import { TodayPage } from "./pages/TodayPage";
import { FamiliesPage } from "./pages/FamiliesPage";
import { DecisionsPage } from "./pages/DecisionsPage";
import { ActivityPage } from "./pages/ActivityPage";
import { StoriesPage } from "./pages/StoriesPage";
import { CaregiverPage } from "./pages/CaregiverPage";
import { AdminAuditPage, AdminRulesPage, DeskRecordsPage, DeskReportPage } from "./pages/StaffPages";
import { Notice } from "./ui/primitives";

/** The ledger row a citation points at. `n` counts clicks, so clicking the
 *  same citation twice replays the flash instead of doing nothing. */
export interface Citation {
  id: string;
  n: number;
}

export default function App() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [persona, choosePersona] = useIdentity();
  const [page, setPage] = useState<PageId>(firstPage(persona.role));
  const [focusId, setFocusId] = useState<string | null>(null);
  const world = useLiveWorld();

  // Every date on the page is read against the simulated day, not the wall clock.
  setSimToday(world.snapshot?.current ?? null);

  useEffect(() => {
    api
      .patients()
      .then(setPatients)
      .catch((e: Error) => setError(e.message));
  }, [world.cohortRevision]);

  // A new person at the console starts on their own first page.
  useEffect(() => {
    if (!NAV[persona.role].some((item) => item.id === page)) setPage(firstPage(persona.role));
  }, [persona.role, page]);

  const openFamily = useCallback(
    (patientId: string) => {
      if (!NAV[persona.role].some((item) => item.id === "families")) return;
      setFocusId(patientId);
      setPage("families");
    },
    [persona.role],
  );

  const viewAs = useCallback(
    (personaId: string) => {
      choosePersona(personaId);
    },
    [choosePersona],
  );

  if (persona.role === "patient") {
    // A feature phone has a voice and a keypad, nothing else. The switcher
    // is tucked at the foot for the demo operator, not for the family.
    return (
      <div className="simple-shell">
        <div key={persona.id} className="panel-fade">
          {persona.patientFocus ? (
            <PatientSimpleView patientId={persona.patientFocus} />
          ) : (
            <Notice tone="warn">This persona has no family assigned.</Notice>
          )}
        </div>
        <div className="simple-escape">
          <RoleSwitcher persona={persona} onChoose={choosePersona} />
        </div>
      </div>
    );
  }

  const snap = world.snapshot;
  const badges: Partial<Record<PageId, number>> = {
    decisions: persona.role === "navigator" ? (snap?.options_pending ?? 0) + (snap?.alerts ?? 0) : snap?.options_pending,
    records: snap?.desk_queue,
  };

  const body = () => {
    const question = navItem(persona.role, page).question;
    switch (page) {
      case "today":
        return <TodayPage world={world} onNavigate={setPage} onOpenFamily={openFamily} />;
      case "families":
        return <FamiliesPage patients={patients} world={world} focusId={focusId} />;
      case "decisions":
        return (
          <DecisionsPage
            world={world}
            approverRole={persona.role}
            approverName={persona.name}
            onlyRequiringDoctor={persona.role === "doctor"}
            question={question}
            onOpenFamily={openFamily}
          />
        );
      case "activity":
        return <ActivityPage world={world} patients={patients} onOpenFamily={openFamily} />;
      case "stories":
        return <StoriesPage world={world} onViewAs={viewAs} onOpenFamily={openFamily} />;
      case "report":
        return <DeskReportPage persona={persona} />;
      case "records":
        return <DeskRecordsPage world={world} />;
      case "rules":
        return <AdminRulesPage />;
      case "audit":
        return <AdminAuditPage />;
      case "plan":
        return persona.patientFocus ? (
          <CaregiverPage persona={persona} world={world} />
        ) : (
          <Notice tone="warn">This persona has no family assigned.</Notice>
        );
    }
  };

  return (
    <AppShell
      persona={persona}
      onChoosePersona={choosePersona}
      page={page}
      onNavigate={(next) => {
        setFocusId(null);
        setPage(next);
      }}
      snapshot={snap}
      connected={world.connected}
      badges={badges}
    >
      {error && (
        <div className="page">
          <Notice tone="stop">
            <strong>The console cannot reach the planner.</strong> {error} — start the API with{" "}
            <span className="mono">make api</span>.
          </Notice>
        </div>
      )}
      <div key={`${persona.id}:${page}`} className="panel-fade page-host">
        {body()}
      </div>
    </AppShell>
  );
}
