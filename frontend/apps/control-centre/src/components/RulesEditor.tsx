import { useEffect, useMemo, useState } from "react";
import {
  config,
  registry,
  type Hospital,
  type HospitalRules,
  type RulesView,
  type RulesVocabulary,
  type StepRule,
} from "@saathi/api-client";
import { Card, Chip, Notice, stepName } from "@saathi/ui-web";
import { errorText } from "./RecordForm";

const emptyStep = (kind: string): StepRule => ({
  kind,
  lead_days: {},
  weekdays: [],
  slot_times: [],
  shift_tolerance_days: null,
  confirmed: false,
  confirmed_by: null,
});

const list = (text: string) =>
  text
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);

const leadText = (lead: Record<string, number>) =>
  Object.entries(lead)
    .map(([k, d]) => `${k}:${d}`)
    .join(", ");

const parseLead = (text: string): Record<string, number> =>
  Object.fromEntries(
    list(text)
      .map((part) => part.split(":").map((p) => p.trim()))
      .filter(([k, d]) => k && d !== undefined && !Number.isNaN(Number(d)))
      .map(([k, d]) => [k, Number(d)]),
  );

/**
 * One hospital's rules, edited by its administrator: when each kind of step can
 * happen, how far it must follow its prerequisites, how far it may move, what a
 * family is asked to bring, and when a journey needs booking ahead.
 *
 * Every save is a new version, kept, with the editor's name in the audit log.
 * And it says, at the top and on every save, that the planner does not read
 * these yet: a screen that let an administrator believe they had moved a
 * family's date would be worse than no screen.
 */
export function RulesEditor({ canEdit }: { canEdit: boolean }) {
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [hospitalId, setHospitalId] = useState("");
  const [vocab, setVocab] = useState<RulesVocabulary | null>(null);
  const [view, setView] = useState<RulesView | null>(null);
  const [rules, setRules] = useState<HospitalRules | null>(null);
  const [message, setMessage] = useState<{ tone: "calm" | "warn"; text: string } | null>(null);
  const [addKind, setAddKind] = useState("");

  useEffect(() => {
    registry.hospitals().then((rows) => {
      setHospitals(rows);
      setHospitalId((current) => current || rows[0]?.id || "");
    });
    config.vocabulary().then(setVocab).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!hospitalId) return;
    setMessage(null);
    config
      .rules(hospitalId)
      .then((v) => {
        setView(v);
        setRules(v.policy);
      })
      .catch((e) => setMessage({ tone: "warn", text: errorText(e) }));
  }, [hospitalId]);

  const steps = useMemo(() => Object.values(rules?.steps ?? {}), [rules]);
  const unused = (vocab?.step_kinds ?? []).filter((k) => !rules?.steps[k]);

  if (!rules || !vocab) return <Notice tone="calm">Loading the rules…</Notice>;

  const setStep = (kind: string, patch: Partial<StepRule>) =>
    setRules({ ...rules, steps: { ...rules.steps, [kind]: { ...rules.steps[kind], ...patch } } });

  const setNumber = (key: keyof HospitalRules, value: string) =>
    setRules({ ...rules, [key]: value === "" ? 0 : Number(value) });

  const toggleDoc = (kind: string, doc: string) => {
    const now = rules.requirements[kind] ?? [];
    const next = now.includes(doc) ? now.filter((d) => d !== doc) : [...now, doc];
    const requirements = { ...rules.requirements, [kind]: next };
    if (next.length === 0) delete requirements[kind];
    setRules({ ...rules, requirements });
  };

  const save = async () => {
    setMessage(null);
    try {
      const saved = await config.saveRules(hospitalId, rules);
      setMessage({ tone: "calm", text: `Saved as version ${saved.version}. ${saved.note}` });
      const fresh = await config.rules(hospitalId);
      setView(fresh);
      setRules(fresh.policy);
    } catch (e) {
      setMessage({ tone: "warn", text: errorText(e) });
    }
  };

  const docKinds = Array.from(new Set([...steps.map((s) => s.kind), ...Object.keys(rules.requirements), "review_consult", "consult"]));

  return (
    <>
      <Notice tone="warn">
        <strong>Draft rules.</strong> {view?.note}
      </Notice>

      <Card
        title="Hospital rules"
        hint={
          view
            ? view.source === "default"
              ? "built-in placeholders, never confirmed"
              : `version ${view.version}, saved by ${view.saved_by}`
            : ""
        }
        aside={
          <select value={hospitalId} onChange={(e) => setHospitalId(e.target.value)} aria-label="Hospital">
            {hospitals.map((h) => (
              <option key={h.id} value={h.id}>
                {h.name}
              </option>
            ))}
          </select>
        }
      >
        <h3 className="cc-sub">Travel</h3>
        <div className="iss-fields">
          <label>
            Stay in the city if a round trip is over (hours)
            <input type="number" min={0} disabled={!canEdit} value={rules.stay_rather_than_travel_hours}
              onChange={(e) => setNumber("stay_rather_than_travel_hours", e.target.value)} />
          </label>
          <label>
            Journeys needing a reservation are over (hours)
            <input type="number" min={0} disabled={!canEdit} value={rules.reserved_journey_hours}
              onChange={(e) => setNumber("reserved_journey_hours", e.target.value)} />
          </label>
          <label>
            Days of notice to book a reserved journey
            <input type="number" min={0} disabled={!canEdit} value={rules.reservation_lead_days}
              onChange={(e) => setNumber("reservation_lead_days", e.target.value)} />
          </label>
          <label>
            Gap when no journey is known (days)
            <input type="number" min={0} disabled={!canEdit} value={rules.unknown_journey_gap_days}
              onChange={(e) => setNumber("unknown_journey_gap_days", e.target.value)} />
          </label>
        </div>

        <h3 className="cc-sub">Steps</h3>
        <table className="audit-table">
          <thead>
            <tr>
              <th>Step</th>
              <th>Days it runs</th>
              <th>Slot times</th>
              <th>Must follow (step:days)</th>
              <th>May move ± days</th>
              <th>Confirmed by a clinician</th>
            </tr>
          </thead>
          <tbody>
            {steps.map((step) => (
              <tr key={step.kind}>
                <td>{stepName(step.kind)}</td>
                <td>
                  <div className="cc-days">
                    {vocab.weekdays.map((day, i) => (
                      <label key={day}>
                        <input
                          type="checkbox"
                          disabled={!canEdit}
                          checked={step.weekdays.includes(i)}
                          onChange={() =>
                            setStep(step.kind, {
                              weekdays: step.weekdays.includes(i)
                                ? step.weekdays.filter((d) => d !== i)
                                : [...step.weekdays, i].sort(),
                            })
                          }
                        />
                        {day}
                      </label>
                    ))}
                  </div>
                  {step.weekdays.length === 0 && <span className="hint">any day</span>}
                </td>
                <td>
                  <input disabled={!canEdit} defaultValue={step.slot_times.join(", ")} placeholder="10:00, 14:30"
                    onBlur={(e) => setStep(step.kind, { slot_times: list(e.target.value) })} />
                </td>
                <td>
                  <input disabled={!canEdit} defaultValue={leadText(step.lead_days)} placeholder="scan:2"
                    onBlur={(e) => setStep(step.kind, { lead_days: parseLead(e.target.value) })} />
                </td>
                <td>
                  <input type="number" min={0} disabled={!canEdit} value={step.shift_tolerance_days ?? ""}
                    placeholder="not said" style={{ width: 90 }}
                    onChange={(e) => setStep(step.kind, { shift_tolerance_days: e.target.value === "" ? null : Number(e.target.value) })} />
                </td>
                <td>
                  <label className="cc-inline">
                    <input type="checkbox" disabled={!canEdit} checked={step.confirmed}
                      onChange={(e) => setStep(step.kind, { confirmed: e.target.checked })} />
                    {step.confirmed ? <Chip tone="go">confirmed</Chip> : <Chip tone="uncertain">provisional</Chip>}
                  </label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {canEdit && unused.length > 0 && (
          <div className="iss-actions" style={{ marginTop: 8 }}>
            <select value={addKind} onChange={(e) => setAddKind(e.target.value)} aria-label="Step to add a rule for">
              <option value="">Add a rule for…</option>
              {unused.map((k) => (
                <option key={k} value={k}>
                  {stepName(k)}
                </option>
              ))}
            </select>
            <button type="button" className="btn small" disabled={!addKind}
              onClick={() => { setRules({ ...rules, steps: { ...rules.steps, [addKind]: emptyStep(addKind) } }); setAddKind(""); }}>
              Add
            </button>
          </div>
        )}

        <h3 className="cc-sub">What a family is asked to bring</h3>
        <table className="audit-table">
          <thead>
            <tr>
              <th>For</th>
              {Object.values(vocab.entitlements).map((label) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {docKinds.map((kind) => (
              <tr key={kind}>
                <td>{stepName(kind)}</td>
                {Object.keys(vocab.entitlements).map((doc) => (
                  <td key={doc}>
                    <input type="checkbox" disabled={!canEdit}
                      checked={(rules.requirements[kind] ?? []).includes(doc)}
                      onChange={() => toggleDoc(kind, doc)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        <h3 className="cc-sub">Centres in this network</h3>
        <p className="plain">
          {view?.centres.length
            ? view.centres.map((c) => `${c.name} (${c.kind === "hub" ? "hub" : "day care"})`).join(" · ")
            : "None yet."}{" "}
          <span className="hint">Kept in Registries → Treatment centres.</span>
        </p>

        {canEdit && (
          <div className="iss-actions" style={{ marginTop: 12 }}>
            <button type="button" className="btn primary" onClick={save}>
              Save as a new version
            </button>
            <span className="hint">Versions are kept, never overwritten; each save is in the audit log.</span>
          </div>
        )}
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
      </Card>
    </>
  );
}
