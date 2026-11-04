import { useCallback, useEffect, useMemo, useState } from "react";
import { directory, type Organisation, type OrgType, type RoleSummary } from "@saathi/api-client";
import { Card, Chip } from "@saathi/ui-web";
import { RecordForm, errorText, type Field } from "../components/RecordForm";
import { SegmentedControl } from "../components/SegmentedControl";
import { usePersona } from "../session";
import { EmptyState } from "../ui/kit";
import { Building } from "../ui/icons";

const TABS = [
  { value: "network" as const, label: "The network" },
  { value: "roles" as const, label: "People and roles" },
];

/** What each need on a journey is answered by, in words a navigator would say. */
const TYPE_LABEL: Record<OrgType, string> = {
  lab: "Lab or diagnostic centre",
  pharmacy: "Pharmacy",
  medicine_distributor: "Medicine distributor",
  equipment_distributor: "Medical equipment distributor",
  shop: "Shop or merchant",
  cab: "Cab service",
  travel: "Travel partner",
  hotel: "Hotel or stay",
  insurer: "Insurer or scheme desk",
  ambulance: "Ambulance",
};

const FIELDS: Field[] = [
  { key: "id", label: "Id", lockedWhenEditing: true, placeholder: "e.g. cab-meru-mum" },
  { key: "name", label: "Name" },
  {
    key: "type",
    label: "Kind",
    type: "select",
    lockedWhenEditing: true,
    options: Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label })),
  },
  { key: "services", label: "What it offers", type: "list", placeholder: "MRI, blood tests, airport pickup" },
  { key: "districts", label: "Districts it serves", type: "list", placeholder: "Mumbai, Patna" },
  { key: "hospital_ids", label: "Hospitals it works with", type: "list", placeholder: "TMH-MUM (blank = any)" },
  { key: "address", label: "Address" },
  { key: "contact", label: "Contact" },
  { key: "hours", label: "Hours" },
  {
    key: "mode",
    label: "How it answers",
    type: "select",
    options: [
      { value: "simulated", label: "Answers by itself (demonstration)" },
      { value: "people", label: "Waits for a person there" },
    ],
  },
  {
    key: "answer",
    label: "A simulated one says",
    type: "select",
    options: [
      { value: "ready", label: "Ready" },
      { value: "cannot", label: "Can't do it" },
    ],
  },
  { key: "delay_seconds", label: "…after (seconds)" },
  { key: "alternate_id", label: "If it cannot, turn to", placeholder: "another organisation's id" },
  { key: "linked_ids", label: "Linked to", type: "list", placeholder: "e.g. its distributor" },
  { key: "active", label: "Active", type: "checkbox" },
];

const TEXT_KEYS = ["address", "contact", "hours"];

/**
 * Everyone a journey runs through: the labs, pharmacies, distributors, shops,
 * cabs, travel partners, hotels and insurers around a hospital. Staff read it;
 * administrators keep it. A family's journey picks from here, so what is in this
 * list is what the family is directed to.
 */
export function Directory() {
  const { persona } = usePersona();
  const canEdit = persona.role === "admin";
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("network");
  const [orgs, setOrgs] = useState<Organisation[] | null>(null);
  const [type, setType] = useState<OrgType | "">("");
  const [q, setQ] = useState("");
  const [roles, setRoles] = useState<RoleSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ record: Organisation | null } | null>(null);

  const load = useCallback(() => {
    directory.list().then(setOrgs).catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    if (tab === "roles" && canEdit) directory.roles().then(setRoles).catch((e) => setError(errorText(e)));
  }, [tab, canEdit]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (orgs ?? []).filter(
      (o) =>
        (!type || o.type === type) &&
        (!needle || `${o.name} ${o.services.join(" ")} ${o.districts.join(" ")}`.toLowerCase().includes(needle)),
    );
  }, [orgs, type, q]);
  const nameOf = (id: string | null) => (id ? orgs?.find((o) => o.id === id)?.name ?? id : "—");
  const counts = useMemo(() => {
    const out: Partial<Record<OrgType, number>> = {};
    for (const o of orgs ?? []) out[o.type] = (out[o.type] ?? 0) + 1;
    return out;
  }, [orgs]);

  const save = async (values: Record<string, unknown>) => {
    const clean = { ...values };
    for (const k of TEXT_KEYS) if (k in clean && clean[k] === null) clean[k] = "";
    if (typeof clean.delay_seconds === "string") clean.delay_seconds = Number(clean.delay_seconds);
    if (editing?.record) await directory.edit(editing.record.id, clean);
    else await directory.add(clean as never);
    load();
  };

  return (
    <div className="stack">
      <SegmentedControl options={TABS} value={tab} onChange={setTab} aria-label="Directory view" />
      {error && <p className="auth-error" role="alert">{error}</p>}

      {tab === "network" && (
        <>
          {editing && (
            <RecordForm
              title={editing.record ? `Edit ${editing.record.name}` : "Add to the network"}
              fields={FIELDS}
              initial={(editing.record ?? { type: "cab", mode: "simulated", answer: "ready", delay_seconds: 30, active: true, services: [], districts: [], hospital_ids: [], linked_ids: [] }) as unknown as Record<string, unknown>}
              editing={Boolean(editing.record)}
              onSave={save}
              onClose={() => setEditing(null)}
            />
          )}
          <Card
            title="The network"
            hint={orgs ? `${orgs.length} organisations` : "loading…"}
            aside={canEdit ? <button type="button" className="btn primary small" onClick={() => setEditing({ record: null })}>Add</button> : undefined}
          >
            <div className="iss-fields cc-form" style={{ marginBottom: 12 }}>
              <label>
                <span>Kind</span>
                <select value={type} onChange={(e) => setType(e.target.value as OrgType | "")}>
                  <option value="">All kinds ({orgs?.length ?? 0})</option>
                  {Object.entries(TYPE_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label} ({counts[value as OrgType] ?? 0})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Search</span>
                <input value={q} placeholder="name, service or district" onChange={(e) => setQ(e.target.value)} />
              </label>
            </div>
            {orgs && shown.length === 0 ? (
              <EmptyState title="Nobody matches" icon={<Building />}>
                Clear the filter, or {canEdit ? "add the organisation" : "ask an administrator to add it"}.
              </EmptyState>
            ) : (
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Kind</th>
                    <th>Serves</th>
                    <th>How it answers</th>
                    <th>If it cannot</th>
                    <th>Status</th>
                    {canEdit && <th />}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((o) => (
                    <tr key={o.id}>
                      <td>
                        {o.name}
                        <div className="hint">{o.services.join(", ")}</div>
                      </td>
                      <td>{TYPE_LABEL[o.type]}</td>
                      <td>{o.districts.join(", ") || "anywhere"}</td>
                      <td>
                        {o.mode === "people" ? "a person answers" : `says ${o.answer === "ready" ? "ready" : "can't do"} after ${o.delay_seconds}s`}
                      </td>
                      <td>{nameOf(o.alternate_id)}</td>
                      <td><Chip tone={o.active ? "go" : "neutral"}>{o.active ? "active" : "inactive"}</Chip></td>
                      {canEdit && (
                        <td>
                          <button type="button" className="btn small" onClick={() => setEditing({ record: o })}>Edit</button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}

      {tab === "roles" && (
        <Card title="People and roles" hint="What each role is for, and how much of the system it can reach">
          {!canEdit ? (
            <p className="empty">Only administrators see this page.</p>
          ) : !roles ? (
            <p className="empty">loading…</p>
          ) : (
            <>
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>What it is for</th>
                    <th>Actions it can take</th>
                    <th>Accounts</th>
                  </tr>
                </thead>
                <tbody>
                  {roles.map((r) => (
                    <tr key={r.role}>
                      <td><strong>{r.role}</strong></td>
                      <td>{r.blurb}</td>
                      <td>{r.routes}</td>
                      <td>{r.accounts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="hint" style={{ marginTop: 10 }}>
                The numbers are read from the rules the server enforces. Add, disable or change an account under
                Registries &rsaquo; Staff accounts.
              </p>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
