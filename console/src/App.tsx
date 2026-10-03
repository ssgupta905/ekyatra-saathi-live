import { useCallback, useEffect, useState } from "react";
import { api, stories as storyApi, type Patient, type Story } from "./lib/api";
import { useLiveWorld } from "./lib/live";
import { useIdentity } from "./lib/identity";
import { ClockBar } from "./components/ClockBar";
import { StoryBar } from "./components/StoryBar";
import { StoryView } from "./components/StoryView";
import { StoryScorecard } from "./components/StoryScorecard";
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
  const [storyId, setStoryId] = useState<string | null>(null);
  const [story, setStory] = useState<Story | null>(null);
  // The story view is the brief's headline presentation mode; the persona
  // screens are the alternative it offers. Both read the same event stream.
  const [showStory, setShowStory] = useState(true);

  const refreshStory = useCallback(() => {
    storyApi
      .state()
      .then((state) => {
        if (!state.scripted || state.stories.length === 0) {
          setStory(null);
          return;
        }
        const chosen =
          state.stories.find((s) => s.id === storyId) ?? state.stories[0];
        setStory(chosen);
        setStoryId((current) => current ?? chosen.id);
      })
      .catch(() => setStory(null));
  }, [storyId]);

  useEffect(refreshStory, [refreshStory, world.cohortRevision]);

  useEffect(() => {
    api
      .patients()
      .then(setPatients)
      .catch((e: Error) => setError(e.message));
  }, []);

  const body = () => {
    if (showStory && story) {
      return (
        <main className="stage">
          <StoryView story={story} events={world.events} />
          <StoryScorecard story={story} events={world.events} />
        </main>
      );
    }
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

        {story && (
          <div className="segmented" role="group" aria-label="How to watch">
            <button
              type="button"
              aria-pressed={showStory}
              onClick={() => setShowStory(true)}
              title="Family, agents and hospital side by side"
            >
              Story view
            </button>
            <button
              type="button"
              aria-pressed={!showStory}
              onClick={() => setShowStory(false)}
              title={`Work as ${persona.name}`}
            >
              Sign in as one person
            </button>
          </div>
        )}

        <span className="spacer" />

        <PersonaSwitcher persona={persona} onChoose={choosePersona} />

        <span className="boundary" title="The scope boundary, enforced in code">
          <Shield size={14} />
          Logistics only · no results, no diagnosis, no advice
        </span>
      </header>

      <StoryBar
        selected={storyId}
        onSelect={(id) => {
          setStoryId(id);
          setShowStory(true);
        }}
        onAdvanced={refreshStory}
        revision={world.cohortRevision}
      />

      <div
        key={showStory ? "story" : persona.id}
        className={story ? "panel-fade has-story" : "panel-fade"}
      >
        {body()}
      </div>
    </>
  );
}
