import { useEffect, useState } from "react";
import {
  admin,
  config as configApi,
  demo,
  type AdminConfig,
  type DemoFamily,
  type Integrations,
} from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { errorText } from "../components/RecordForm";
import { RulesEditor } from "../components/RulesEditor";
import { usePersona } from "../session";
import { useToast } from "../ui/kit";

/** Services in the order they are asked — not proof that any of them answers.
 *  Listing them in order is the honest shape: when the first fails, the second
 *  takes over silently, and a single name would hide that it ever happened. */
const asked = (names: string[] | null | undefined, none: string) =>
  names && names.length > 0 ? (
    <>
      {names.map((name, i) => (
        <Chip key={name} tone={i === 0 ? "go" : "neutral"}>
          {i === 0 ? name : `then ${name}`}
        </Chip>
      ))}
    </>
  ) : (
    <Chip tone="neutral">{none}</Chip>
  );

const on = (value: boolean | string | null | undefined, off = "off") =>
  value ? <Chip tone="go">{typeof value === "string" ? value : "on"}</Chip> : <Chip tone="neutral">{off}</Chip>;

/**
 * Three scripted families for a walk-through. Where each family's sign-in code goes
 * is typed here, by whoever is demonstrating; nothing about it lives in the code.
 * Loading again puts every family back at the start of its story.
 */
function DemoCast() {
  const [emails, setEmails] = useState(["", "", ""]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DemoFamily[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const toast = useToast();
  const given = emails.map((e) => e.trim()).filter(Boolean);
  const ok = given.length > 0 && given.every((e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e));
  const stories = ["Smooth journey", "A vendor fails", "A second condition (dialysis)"];

  const load = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const done = await demo.loadCast(given);
      setResult(done.families);
      toast("Demo families loaded. Each is back at the start of its story.");
    } catch (e) {
      setProblem(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title="Demo families"
      hint="Three scripted journeys, each sent its sign-in code at the address you give. Load again to start over."
    >
      <div className="iss-fields cc-form">
        {stories.map((story, i) => (
          <label key={story} htmlFor={`demo-email-${i}`}>
            <span>{i + 1}. {story}</span>
            <input
              id={`demo-email-${i}`}
              type="email"
              value={emails[i]}
              placeholder="email address (optional)"
              onChange={(e) => setEmails((prev) => prev.map((v, j) => (j === i ? e.target.value : v)))}
            />
          </label>
        ))}
      </div>
      <div className="iss-actions" style={{ marginTop: 10 }}>
        <button type="button" className="btn primary" disabled={!ok || busy} onClick={load}>
          {busy ? "loading…" : "Load the demo families"}
        </button>
        <span className="hint">The first address needs at least one entry; leave the rest blank to load fewer.</span>
      </div>
      {problem && <Notice tone="warn">{problem}</Notice>}
      {result && (
        <table className="audit-table" style={{ marginTop: 10 }}>
          <tbody>
            {result.map((f) => (
              <tr key={f.patient_id}>
                <td><strong>{f.name}</strong><div className="hint">{f.patient_id}</div></td>
                <td>{f.story}</td>
                <td>{f.email ?? "no address"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

/**
 * How the system is set up: each hospital's rules (editable, versioned, and
 * honestly marked as not yet used by the planner), the readiness settings, and
 * what is switched on. Says where each value comes from, so nobody edits a
 * number here expecting something it does not do.
 */
export function Configuration() {
  const { persona } = usePersona();
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [integrations, setIntegrations] = useState<Integrations | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    admin.config().then(setConfig).catch((e: Error) => setError(e.message));
    configApi.integrations().then(setIntegrations).catch(() => undefined);
  }, []);

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (!config) return <Notice tone="calm">Loading…</Notice>;

  return (
    <div className="widget-grid">
      <div className="span-2 cc-stack">
        <RulesEditor canEdit={persona.role === "admin"} />
      </div>
      <Card
        title="Readiness rules"
        hint={`${Math.round(config.readiness.coverage * 100)}% coverage guarantee · α ${config.readiness.conformal_alpha}`}
        flush
        note="Set by SAATHI_CONFORMAL_ALPHA. The queue profiles are the demo generator's turnaround shapes; on real records the forecast is calibrated on reports this hospital has released."
      >
        <table className="audit-table">
          <thead>
            <tr>
              <th>Queue</th>
              <th>Median turnaround</th>
              <th>Tail probability</th>
              <th>Tail extra</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(config.readiness.queue_turnaround_profiles).map(([queue, p]) => (
              <tr key={queue}>
                <td>{queue}</td>
                <td>{p.median_days}d</td>
                <td>{Math.round(p.tail_probability * 100)}%</td>
                <td>{p.tail_extra_days}d</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Languages and channels" note="Set in the server's environment.">
        <table className="audit-table">
          <tbody>
            <tr>
              <td>Languages</td>
              <td>{config.languages.join(", ")}</td>
            </tr>
            <tr>
              <td>Channels</td>
              <td>{config.channels.join(", ")}</td>
            </tr>
            <tr>
              <td>Families watched live</td>
              <td>{config.staff.watched_families}</td>
            </tr>
            <tr>
              <td>Desk auto-confirm (demo)</td>
              <td>after {config.staff.auto_confirm_ticks} days</td>
            </tr>
            <tr>
              <td>Caregiver actor cadence (demo)</td>
              <td>every {config.staff.inbound_every_seconds}s</td>
            </tr>
          </tbody>
        </table>
      </Card>

      <Card title="What is switched on" note="Read from the server's environment. Keys, passwords and full addresses are never shown.">
        {integrations ? (
          <table className="audit-table">
            <tbody>
              <tr><td>World</td><td>{integrations.world === "real" ? "real records" : "demo"}</td></tr>
              <tr><td>Login</td><td>{on(integrations.login.on && integrations.login.provider)}{integrations.login.on && integrations.login.secret_is_default && <span className="hint"> · signing with the dev secret</span>}</td></tr>
              <tr><td>Records database</td><td>{integrations.world === "real" ? on(integrations.records_database) : <span className="hint">in memory (demo)</span>}</td></tr>
              <tr><td>Language layer</td><td>{on(integrations.language_layer, "off: no GROQ_API_KEY / ANTHROPIC_API_KEY")}</td></tr>
              <tr><td>Actors</td><td>{on(integrations.actors)}</td></tr>
              <tr><td>Speech to text</td><td>{asked(integrations.speech_to_text, "nobody can listen")}</td></tr>
              <tr><td>Reading aloud</td><td>{asked(integrations.text_to_speech, "no voice: a family who cannot read hears nothing")}</td></tr>
              <tr><td>Journey lookups</td><td>{on(integrations.reference_cache.present && "cached")}{integrations.reference_cache.network_lookups && <span className="hint"> · live calls allowed</span>} <span className="hint">{integrations.geocoder} · {integrations.router}</span></td></tr>
              <tr><td>Hospital feed</td><td>{on(integrations.feeds.hospital, "not connected")}</td></tr>
              <tr><td>Scheme feed</td><td>{on(integrations.feeds.schemes, "not connected")}</td></tr>
              <tr><td>ABDM</td><td>{on(integrations.feeds.abdm, "not connected")}</td></tr>
              <tr><td>WhatsApp</td><td>{on(integrations.channels.whatsapp, "not connected")}</td></tr>
              <tr><td>Bhashini</td><td>{on(integrations.channels.bhashini, "not connected")}</td></tr>
            </tbody>
          </table>
        ) : (
          <p className="empty">Loading…</p>
        )}
      </Card>

      {integrations?.world === "real" && persona.role === "admin" && <DemoCast />}
    </div>
  );
}
