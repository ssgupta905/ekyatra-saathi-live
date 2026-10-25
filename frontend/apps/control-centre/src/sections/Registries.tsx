import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  registry,
  type Clinician,
  type Hospital,
  type NetworkCentre,
  type ResourceRecord,
  type StaffAccount,
} from "@saathi/api-client";
import { Card, Chip, Notice, stepName } from "@saathi/ui-web";
import { RecordForm, errorText, type Field } from "../components/RecordForm";
import { SegmentedControl } from "../components/SegmentedControl";
import { usePersona } from "../session";
import { useWorld } from "../world";

const TABS = [
  { value: "hospitals" as const, label: "Hospitals" },
  { value: "centres" as const, label: "Treatment centres" },
  { value: "clinicians" as const, label: "Doctors & clinicians" },
  { value: "resources" as const, label: "Resources" },
  { value: "accounts" as const, label: "Staff accounts" },
];
type Tab = (typeof TABS)[number]["value"];

const STEP_KINDS = ["consult", "biopsy", "bloods", "scan", "pet_ct", "review_consult", "joint_clinic",
  "treatment", "maintenance_dose", "echo_review"];  // prettier-ignore

/**
 * The hospital network as an administrator keeps it: hospitals and their
 * departments, the treatment centres in each network and what each can do, the
 * doctors, the bookable resources, and who may sign in. Everyone on staff can
 * read it; only administrators change it, and every change is in the audit log.
 */
export function Registries({ tab, onTab }: { tab: string | null; onTab: (tab: string) => void }) {
  const { persona } = usePersona();
  const world = useWorld();
  const canEdit = persona.role === "admin";
  const real = world.snapshot?.world === "real";
  const current: Tab = (TABS.find((t) => t.value === tab)?.value ?? "hospitals") as Tab;

  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [centres, setCentres] = useState<NetworkCentre[]>([]);
  const [clinicians, setClinicians] = useState<Clinician[]>([]);
  const [resources, setResources] = useState<ResourceRecord[]>([]);
  const [accounts, setAccounts] = useState<StaffAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ record: Record<string, unknown> | null } | null>(null);

  const load = useCallback(() => {
    setError(null);
    Promise.all([registry.hospitals(), registry.centres(), registry.clinicians(), registry.resources()])
      .then(([h, c, d, r]) => {
        setHospitals(h);
        setCentres(c);
        setClinicians(d);
        setResources(r);
      })
      .catch((e) => setError(errorText(e)));
    if (canEdit && real) registry.users().then(setAccounts).catch(() => setAccounts(null));
  }, [canEdit, real]);

  useEffect(load, [load]);
  useEffect(() => setEditing(null), [current]);

  const hospitalOptions = hospitals.map((h) => ({ value: h.id, label: `${h.name} (${h.id})` }));
  const hospitalName = (id: string) => hospitals.find((h) => h.id === id)?.name ?? id;

  const forms: Record<Tab, { title: string; fields: Field[]; empty: Record<string, unknown>; save: (v: Record<string, unknown>, id?: string) => Promise<unknown>; idKey: string }> = {
    hospitals: {
      title: "Hospital",
      idKey: "id",
      empty: { id: "", name: "", place: "", timezone: "Asia/Kolkata", departments: [], active: true },
      fields: [
        { key: "id", label: "Id", lockedWhenEditing: true, placeholder: "e.g. AIIMS-PAT" },
        { key: "name", label: "Name" },
        { key: "place", label: "City or district", placeholder: "the place journeys are fetched to" },
        { key: "timezone", label: "Timezone" },
        { key: "departments", label: "Departments", type: "list", placeholder: "radiology, pathology, …" },
        { key: "active", label: "Active", type: "checkbox" },
      ],
      save: (v, id) => (id ? registry.editHospital(id, v) : registry.addHospital(v as never)),
    },
    centres: {
      title: "Treatment centre",
      idKey: "id",
      empty: { id: "", hospital_id: hospitals[0]?.id ?? "", name: "", place: "", kind: "day_care", handles: [], active: true },
      fields: [
        { key: "id", label: "Id", lockedWhenEditing: true },
        { key: "hospital_id", label: "Network of", type: "select", options: hospitalOptions, lockedWhenEditing: true },
        { key: "name", label: "Name" },
        { key: "place", label: "City or district" },
        { key: "kind", label: "Kind", type: "select", options: [{ value: "hub", label: "Hub" }, { value: "day_care", label: "Day care" }] },
        { key: "handles", label: "Can do", type: "list", placeholder: STEP_KINDS.slice(0, 4).join(", ") },
        { key: "active", label: "Active", type: "checkbox" },
      ],
      save: (v, id) => (id ? registry.editCentre(id, v) : registry.addCentre(v as never)),
    },
    clinicians: {
      title: "Doctor or clinician",
      idKey: "id",
      empty: { id: "", name: "", specialty: "", hospital_id: hospitals[0]?.id ?? "", department: "", username: "", active: true },
      fields: [
        { key: "id", label: "Id", lockedWhenEditing: true, placeholder: "e.g. dr-rao" },
        { key: "name", label: "Name" },
        { key: "specialty", label: "Specialty" },
        { key: "hospital_id", label: "Hospital", type: "select", options: hospitalOptions },
        { key: "department", label: "Department" },
        { key: "username", label: "Signs in as", placeholder: "their staff username, if any" },
        { key: "active", label: "Active", type: "checkbox" },
      ],
      save: (v, id) => (id ? registry.editClinician(id, v) : registry.addClinician(v as never)),
    },
    resources: {
      title: "Resource",
      idKey: "id",
      empty: {},
      fields: [
        { key: "id", label: "Id", lockedWhenEditing: true },
        { key: "display_name", label: "Name" },
        { key: "kind", label: "Kind", type: "select", options: [{ value: "machine", label: "Machine" }, { value: "staff", label: "Staff role" }, { value: "supply", label: "Supply" }] },
        { key: "hospital_id", label: "Hospital", type: "select", options: hospitalOptions },
        { key: "department", label: "Department" },
      ],
      save: (v, id) => registry.editResource(id!, v),
    },
    accounts: {
      title: "Staff account",
      idKey: "username",
      empty: { username: "", name: "", role: "navigator", password: "", active: true },
      fields: [
        { key: "username", label: "Username", lockedWhenEditing: true },
        { key: "name", label: "Name" },
        { key: "role", label: "Role", type: "select", options: ["navigator", "desk", "doctor", "admin"].map((r) => ({ value: r, label: r })) },
        { key: "password", label: "Password (blank keeps it)", type: "password" },
        { key: "active", label: "Can sign in", type: "checkbox" },
      ],
      save: (v, id) => (id ? registry.editUser(id, v) : registry.addUser(v as never)),
    },
  };

  const form = forms[current];
  const open = (record: Record<string, unknown> | null) => canEdit && setEditing({ record });
  const action = (record: unknown) =>
    canEdit ? (
      <button type="button" className="btn small" onClick={() => open(record as Record<string, unknown>)}>
        Edit
      </button>
    ) : null;

  const table = (head: string[], rows: ReactNode[][]) => (
    <table className="audit-table">
      <thead>
        <tr>
          {head.map((h) => (
            <th key={h}>{h}</th>
          ))}
          {canEdit && <th />}
        </tr>
      </thead>
      <tbody>
        {rows.map((cells, i) => (
          <tr key={i}>
            {cells.map((c, j) => (
              <td key={j}>{c}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );

  const status = (active: boolean) => <Chip tone={active ? "go" : "neutral"}>{active ? "active" : "inactive"}</Chip>;

  const body = (): ReactNode => {
    switch (current) {
      case "hospitals":
        return table(
          ["Id", "Name", "Place", "Departments", "Status"],
          hospitals.map((h) => [<span className="mono">{h.id}</span>, h.name, h.place, h.departments.join(", ") || "—", status(h.active), ...(canEdit ? [action(h)] : [])]),
        );
      case "centres":
        return table(
          ["Centre", "Network", "Place", "Kind", "Can do", "Status"],
          centres.map((c) => [c.name, hospitalName(c.hospital_id), c.place, c.kind === "hub" ? "hub" : "day care", c.handles.map(stepName).join(", ") || "—", status(c.active), ...(canEdit ? [action(c)] : [])]),
        );
      case "clinicians":
        return table(
          ["Name", "Specialty", "Hospital", "Department", "Signs in as", "Status"],
          clinicians.map((c) => [c.name, c.specialty || "—", hospitalName(c.hospital_id), c.department || "—", c.username ? <span className="mono">{c.username}</span> : "no login", status(c.active), ...(canEdit ? [action(c)] : [])]),
        );
      case "resources":
        return table(
          ["Id", "Name", "Kind", "Hospital", "Department"],
          resources.map((r) => [<span className="mono">{r.id}</span>, r.display_name, r.kind, hospitalName(r.hospital_id), r.department, ...(canEdit && real ? [action(r)] : canEdit ? [<span className="hint">real records only</span>] : [])]),
        );
      case "accounts":
        if (!real) return <p className="empty">Staff accounts exist where login is on: run the API on real records.</p>;
        if (!canEdit) return <p className="empty">Only administrators manage accounts.</p>;
        return table(
          ["Username", "Name", "Role", "Status"],
          (accounts ?? []).map((u) => [<span className="mono">{u.username}</span>, u.name, u.role, status(u.active), action(u)]),
        );
    }
  };

  const counts: Record<Tab, number> = {
    hospitals: hospitals.length,
    centres: centres.length,
    clinicians: clinicians.length,
    resources: resources.length,
    accounts: accounts?.length ?? 0,
  };
  const canAdd = canEdit && current !== "resources" && (current !== "accounts" || real);

  return (
    <>
      <SegmentedControl options={TABS} value={current} onChange={onTab} aria-label="Registry" />
      {error && <Notice tone="warn">{error}</Notice>}
      {editing && (
        <RecordForm
          key={JSON.stringify(editing.record)}
          title={`${editing.record ? "Edit" : "Add a"} ${form.title.toLowerCase()}`}
          fields={form.fields}
          initial={editing.record ?? form.empty}
          editing={Boolean(editing.record)}
          onSave={(values) => form.save(values, editing.record ? String(editing.record[form.idKey]) : undefined).then(load)}
          onClose={() => setEditing(null)}
        />
      )}
      <Card
        title={TABS.find((t) => t.value === current)!.label}
        hint={`${counts[current]} on record${canEdit ? "" : " · read-only for your role"}`}
        aside={canAdd ? <button type="button" className="btn primary small" onClick={() => open(null)}>Add</button> : undefined}
        flush
      >
        {body()}
      </Card>
    </>
  );
}
