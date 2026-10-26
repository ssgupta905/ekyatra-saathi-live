import { useEffect, useMemo, useState } from "react";
import { EVENT_LABEL, runtimeConfig, useLiveWorld } from "@saathi/api-client";
import { ClockDisplay } from "@saathi/ui-web";
import { ClockControls } from "./ClockControls";
import { StoryBar } from "./StoryBar";

/**
 * Every screen at once, for one recording or one presentation.
 *
 * The family's phone, the desk and the navigator are separate applications on
 * separate devices; that is the whole point of having split them. But the thing
 * worth watching is one event crossing between them: a machine goes down at the
 * desk, the navigator's worklist changes, and a phone six hundred kilometres away
 * changes while someone is holding it.
 *
 * So this page mounts the real apps in frames. Not mock-ups of them: each is the
 * actual app with its own event-stream connection, talking to the same backend.
 * Whatever happens here would happen on separate devices.
 *
 * The story bar and the clock controls live here and nowhere else. They are the
 * presenter's tools, not the product's. The caption band is narration read off
 * the real event stream, so it can only say things that actually happened.
 *
 * Any screen can also take the whole stage. Side by side is the right view for the
 * moment an event crosses between them and the wrong one for reading a thirty-family
 * worklist. The focus control is a view setting on this page only.
 */

type Focus = "all" | "phone" | "desk" | "navigator";

const FOCUS: [Focus, string][] = [
  ["all", "All"],
  ["phone", "Phone"],
  ["desk", "Desk"],
  ["navigator", "Navigator"],
];

/** Where each app is. `config.json` wins; these are the local development ports. */
const DEFAULT_APPS = {
  family: "http://localhost:5180",
  /** The control centre, framed twice: once as the desk, once as the navigator. */
  control: "http://localhost:5173",
};

/** Which families get a phone. One by default; `?phones=P-SHAMBHU,P-ANITA` for two. */
function phonesFromUrl(): string[] {
  const listed = new URLSearchParams(window.location.search).get("phones");
  return listed ? listed.split(",").filter(Boolean) : ["P-SHAMBHU"];
}

export default function App() {
  const phones = useMemo(phonesFromUrl, []);
  const apps = { ...DEFAULT_APPS, ...runtimeConfig().apps };
  const world = useLiveWorld();
  const [storyId, setStoryId] = useState<string | null>(null);
  const [caption, setCaption] = useState<string | null>(null);
  const [focus, setFocus] = useState<Focus>("all");

  // The newest real event, in words. Narration that cannot drift from the run
  // because it is not written anywhere — it is read off the stream.
  const newest = world.events[0];
  useEffect(() => {
    if (!newest) return;
    setCaption(`${EVENT_LABEL[newest.kind] ?? newest.kind} · ${newest.summary}`);
  }, [newest?.seq, newest]);

  return (
    <div className={`st-stage focus-${focus}`}>
      <div className="st-controls">
        <header className="st-bar">
          <ClockDisplay snapshot={world.snapshot} connected={world.connected}>
            <ClockControls snapshot={world.snapshot} />
          </ClockDisplay>
        </header>
        <StoryBar
          selected={storyId}
          onSelect={setStoryId}
          onAdvanced={() => undefined}
          revision={world.cohortRevision}
        />
      </div>

      <div className="st-screens">
        {phones.map((patientId) => (
          <section className="st-phone" key={patientId}>
            <header className="st-label">
              <span className="st-dot family" />
              The family's phone
              <span className="st-sub">{patientId}</span>
            </header>
            <div className="st-phone-shell">
              <iframe
                title={`Family app — ${patientId}`}
                src={`${apps.family}/?patient=${encodeURIComponent(patientId)}`}
                allow="microphone"
              />
            </div>
          </section>
        ))}

        <section className="st-desk" data-screen="desk">
          <header className="st-label">
            <span className="st-dot hospital" />
            The desk
            <span className="st-sub">reports and confirms</span>
          </header>
          <div className="st-desk-shell">
            <iframe title="Desk app" src={`${apps.control}/?persona=imran&section=issues`} />
          </div>
        </section>

        <section className="st-desk" data-screen="navigator">
          <header className="st-label">
            <span className="st-dot hospital" />
            The navigator
            <span className="st-sub">decides and calls</span>
          </header>
          <div className="st-desk-shell">
            <iframe title="Navigator app" src={`${apps.control}/?persona=seema&section=families`} />
          </div>
        </section>
      </div>

      <footer className="st-caption">
        <div className="st-focus" role="group" aria-label="Which screen">
          {FOCUS.map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              aria-pressed={focus === mode}
              onClick={() => setFocus(mode)}
            >
              {label}
            </button>
          ))}
        </div>

        <span className={world.connected ? "st-live on" : "st-live"}>
          {world.connected ? "live" : "not connected"}
        </span>
        <span className="st-caption-text">{caption ?? "waiting for the first event…"}</span>
        <span className="st-counters">
          {world.snapshot ? `day ${world.snapshot.day} · ${world.snapshot.current}` : ""}
        </span>
      </footer>
    </div>
  );
}
