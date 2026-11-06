import { useCallback, useEffect, useState } from "react";
import {
  directory,
  readiness,
  type Organisation,
  type OrgType,
  type ReadinessItem,
  type ReadinessKind,
  type ReadinessStatus,
} from "@saathi/api-client";
import { Notice } from "@saathi/ui-web";
import { Pill, SkeletonRows, type Tone } from "../ui/kit";

const KIND: Record<ReadinessKind, string> = {
  transport: "Ride",
  stay: "Stay",
  medicine: "Medicine",
  insurance: "Insurer / scheme",
  slot: "Hospital slot",
  doctor: "Doctor available",
  bed: "Bed",
};

/** Which kinds of organisation can answer each need. */
const ORG_TYPES: Record<ReadinessKind, OrgType[]> = {
  transport: ["cab", "travel"],
  stay: ["hotel"],
  medicine: ["pharmacy"],
  insurance: ["insurer"],
  slot: ["hospital", "lab"],
  doctor: ["hospital"],
  bed: ["hospital"],
};

const STATUS: Record<ReadinessStatus, { label: string; tone: Tone }> = {
  ready: { label: "Ready", tone: "go" },
  pending: { label: "Pending", tone: "wait" },
  blocked: { label: "Blocked", tone: "critical" },
  unknown: { label: "No answer yet", tone: "uncertain" },
};

/**
 * Everyone else the journey depends on, and what each has said.
 *
 * A care step being done is not the same as a family being able to travel: the
 * cab, the room, the medicine and the insurer each have a say. A party can only
 * make the answer more cautious, and silence is never read as ready.
 */
export function PartnersLayer({
  patientId,
  revision,
  canEdit,
  onChanged,
}: {
  patientId: string;
  revision: number;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const [items, setItems] = useState<ReadinessItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    kind: "transport" as ReadinessKind,
    party: "",
    status: "ready" as ReadinessStatus,
    detail: "",
    alternative: false,
  });

  const load = useCallback(() => {
    readiness
      .list(patientId)
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message));
  }, [patientId]);

  useEffect(load, [load, revision]);

  const save = async () => {
    setError(null);
    try {
      await readiness.put(patientId, {
        kind: form.kind,
        party: form.party.trim(),
        status: form.status,
        detail: form.detail.trim(),
        alternative_available: form.alternative,
        source: "partner",
      });
      setForm({ ...form, party: "", detail: "", alternative: false });
      load();
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  };

  const [orgs, setOrgs] = useState<Organisation[]>([]);
  const [ask, setAsk] = useState({ kind: "transport" as ReadinessKind, organisation: "" });
  useEffect(() => {
    if (canEdit) directory.list().then(setOrgs).catch(() => undefined);
  }, [canEdit]);
  const candidates = orgs.filter((o) => o.active && ORG_TYPES[ask.kind].includes(o.type));

  const run = async (work: () => Promise<unknown>) => {
    setError(null);
    try {
      await work();
      load();
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  };

  const clear = async (id: string) => {
    await readiness.clear(patientId, id).catch((e: Error) => setError(e.message));
    load();
    onChanged();
  };

  if (!items) return <SkeletonRows rows={2} />;

  return (
    <div className="partners">
      {items.length === 0 ? (
        <Notice tone="calm">
          No other party has reported on this journey. Saathi plans from the care steps alone until one does.
        </Notice>
      ) : (
        <table className="cc-table">
          <thead>
            <tr>
              <th>What</th>
              <th>Who</th>
              <th>Answer</th>
              <th>Note</th>
              {canEdit && <th />}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{KIND[item.kind]}</td>
                <td>{item.party}</td>
                <td>
                  <Pill tone={STATUS[item.status].tone}>{STATUS[item.status].label}</Pill>
                  {item.status === "blocked" && item.alternative_available && (
                    <span className="mono"> · another way exists</span>
                  )}
                </td>
                <td>{item.detail || "—"}</td>
                {canEdit && (
                  <td>
                    {item.status === "blocked" && item.alternative_available && item.partner_id && (
                      <button
                        type="button"
                        className="btn primary small"
                        onClick={() => run(() => readiness.rebook(patientId, item.id))}
                      >
                        Book another
                      </button>
                    )}{" "}
                    <button type="button" className="btn small" onClick={() => clear(item.id)}>
                      Clear
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {canEdit && (
        <div style={{ marginTop: 14 }}>
          <h3>Ask an organisation from the directory</h3>
          <div className="iss-fields cc-form">
            <label>
              <span>What</span>
              <select
                value={ask.kind}
                onChange={(e) => setAsk({ kind: e.target.value as ReadinessKind, organisation: "" })}
              >
                {Object.entries(KIND).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Organisation</span>
              <select value={ask.organisation} onChange={(e) => setAsk({ ...ask, organisation: e.target.value })}>
                <option value="">Choose…</option>
                {candidates.map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="iss-actions" style={{ marginTop: 8 }}>
            <button
              type="button"
              className="btn primary"
              disabled={!ask.organisation}
              onClick={() => run(() => readiness.ask(patientId, ask.kind, ask.organisation))}
            >
              Ask them
            </button>
          </div>
          <h3 style={{ marginTop: 18 }}>Or record an answer by hand</h3>
          <div className="iss-fields">
            <label>
              What
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as ReadinessKind })}>
                {Object.entries(KIND).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Who
              <input value={form.party} placeholder="e.g. Uber, OYO, day-care pharmacy" onChange={(e) => setForm({ ...form, party: e.target.value })} />
            </label>
            <label>
              Their answer
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as ReadinessStatus })}>
                {Object.entries(STATUS).map(([value, s]) => (
                  <option key={value} value={value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Note
              <input value={form.detail} onChange={(e) => setForm({ ...form, detail: e.target.value })} />
            </label>
            <label>
              <input type="checkbox" checked={form.alternative} onChange={(e) => setForm({ ...form, alternative: e.target.checked })} /> Another way exists (another cab, another slot)
            </label>
          </div>
          <div className="iss-actions" style={{ marginTop: 10 }}>
            <button type="button" className="btn primary" disabled={!form.party.trim()} onClick={save}>
              Record their answer
            </button>
          </div>
        </div>
      )}
      {error && <Notice tone="warn">{error}</Notice>}
    </div>
  );
}
