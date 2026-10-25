import { useEffect, useMemo, useState } from "react";
import { EVENT_LABEL, useLiveWorld } from "@saathi/api-client";

/**
 * Both apps at once, for one recording.
 *
 * The family's phone and the hospital's desk are separate applications on
 * separate devices — that is the whole point of having split them. But the
 * thing worth watching is one event crossing between the two: a machine goes
 * down at the hospital, and a phone six hundred kilometres away changes while
 * someone is holding it.
 *
 * So this page mounts the two real apps in two frames. Not mock-ups of them,
 * and not a third rendering of the same data: these are `index.html` and
 * `family.html`, each with its own event-stream connection, each talking to
 * the same backend. Whatever happens here would happen on two devices.
 *
 * The caption band at the bottom is narration for the recording and nothing
 * more. It is driven by the real event stream, so it can only say things that
 * actually happened.
 *
 * Either screen can also take the whole stage. Side by side is the right view
 * for the moment an event crosses between them, and the wrong one for reading
 * a thirty-family worklist or a thread of messages — at half width each screen
 * is legible on a monitor and not on a projector. The focus control is a view
 * setting on this page only; neither app is told which mode it is in.
 */

type Focus = "both" | "phone" | "hospital";

/** Which families get a phone. Two by default — the brief's two stories. */
function phonesFromUrl(): string[] {
  const params = new URLSearchParams(window.location.search);
  const listed = params.get("phones");
  return listed ? listed.split(",").filter(Boolean) : ["P-SHAMBHU"];
}

export default function StageApp() {
  const phones = useMemo(phonesFromUrl, []);
  const world = useLiveWorld();
  const [caption, setCaption] = useState<string | null>(null);
  const [focus, setFocus] = useState<Focus>("both");

  // The newest real event, in words. Narration that cannot drift from the run
  // because it is not written anywhere — it is read off the stream.
  const newest = world.events[0];
  useEffect(() => {
    if (!newest) return;
    setCaption(`${EVENT_LABEL[newest.kind] ?? newest.kind} · ${newest.summary}`);
  }, [newest?.seq, newest]);

  const api = window.location.origin;

  return (
    <div className={`st-stage focus-${focus}`}>
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
                src={`${api}/family.html?patient=${encodeURIComponent(patientId)}`}
                allow="microphone"
              />
            </div>
          </section>
        ))}

        <section className="st-desk">
          <header className="st-label">
            <span className="st-dot hospital" />
            The hospital's screen
            <span className="st-sub">navigator and desk</span>
          </header>
          <div className="st-desk-shell">
            <iframe title="Hospital app" src={`${api}/index.html`} />
          </div>
        </section>
      </div>

      <footer className="st-caption">
        <div className="st-focus" role="group" aria-label="Which screen">
          {([
            ["both", "Both"],
            ["phone", "Phone"],
            ["hospital", "Hospital"],
          ] as [Focus, string][]).map(([mode, label]) => (
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
