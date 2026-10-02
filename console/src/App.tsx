import { useEffect, useState } from "react";
import { api, type Patient } from "./lib/api";
import { useLiveWorld } from "./lib/live";
import { useIdentity } from "./lib/identity";
import { ClockBar } from "./components/ClockBar";
import { PersonaSwitcher } from "./components/PersonaSwitcher";
import { NavigatorConsole } from "./components/NavigatorConsole";
import { DeskConsole } from "./components/DeskConsole";
import { DoctorConsole } from "./components/DoctorConsole";
import { PatientSimpleView } from "./components/PatientSimpleView";
import { CaregiverView } from "./components/CaregiverView";
import { AdminConsole } from "./components/AdminConsole";
import { Notice } from "./ui/primitives";
import { Shield } from "./ui/icons";

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
  const world = useLiveWorld();

  useEffect(() => {
    api
      .patients()
      .then(setPatients)
      .catch((e: Error) => setError(e.message));
  }, []);

  const body = () => {
    switch (persona.role) {
      case "navigator":
        return (
          <NavigatorConsole
            persona={persona}
            world={world}
            patients={patients}
            error={error}
            setError={setError}
          />
        );
      case "desk":
        return <DeskConsole persona={persona} />;
      case "doctor":
        return <DoctorConsole persona={persona} />;
      case "patient":
        return persona.patientFocus ? (
          <PatientSimpleView patientId={persona.patientFocus} />
        ) : (
          <Notice tone="warn">This persona has no family assigned.</Notice>
        );
      case "caregiver":
        return persona.patientFocus ? (
          <CaregiverView persona={persona} />
        ) : (
          <Notice tone="warn">This persona has no family assigned.</Notice>
        );
      case "admin":
        return <AdminConsole persona={persona} />;
    }
  };

  // Patient simple mode is deliberately chrome-free: a feature phone has a
  // voice and a keypad, nothing else — no header, no persona switcher
  // visible in the family's own view (it still exists for the demo operator
  // to switch back out, tucked away at the foot of the screen).
  if (persona.role === "patient") {
    return (
      <div className="simple-shell">
        <div key={persona.id} className="panel-fade">
          {body()}
        </div>
        <div className="simple-escape">
          <PersonaSwitcher persona={persona} onChoose={choosePersona} />
        </div>
      </div>
    );
  }

  return (
    <>
      <header className="chrome">
        <div className="wordmark">
          <span className="name">Saathi</span>
          <span className="sub">{persona.title}</span>
        </div>

        {persona.role === "navigator" && (
          <ClockBar snapshot={world.snapshot} connected={world.connected} />
        )}

        <span className="spacer" />

        <PersonaSwitcher persona={persona} onChoose={choosePersona} />

        <span className="boundary" title="The scope boundary, enforced in code">
          <Shield size={14} />
          Logistics only · no results, no diagnosis, no advice
        </span>
      </header>

      <div key={persona.id} className="panel-fade">
        {body()}
      </div>
    </>
  );
}
