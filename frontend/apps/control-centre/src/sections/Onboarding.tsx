import { useCallback, useEffect, useMemo, useState } from "react";
import {
  directory,
  onboarding,
  registry,
  type AdmissionRecord,
  type Clinician,
  type FormSchema,
  type Hospital,
  type OnboardingRow,
  type OnboardingStatus,
  type Organisation,
  type OrgType,
  type ProfileDocument,
} from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { AddStep } from "../desk/AddStep";
import { RegisterFamily } from "../desk/RegisterFamily";
import { ConsentLayer } from "../components/ConsentLayer";
import { errorText } from "../components/RecordForm";
import { SchemaForm } from "../components/SchemaForm";
import { usePersona } from "../session";
import { EmptyState, SkeletonRows, useToast } from "../ui/kit";
import { UserPlus } from "../ui/icons";
import { useWorld } from "../world";

/**
 * Taking a family on, in order: what the family tells us first, then what the
 * hospital adds for each admission, then a check that nothing is missing before
 * the family is activated. Each stage saves on its own, so a family can be left
 * half done and picked up later by someone else.
 */
export function Onboarding({ patientId, onOpen }: { patientId: string | null; onOpen: (id: string | null) => void }) {
  const world = useWorld();
  const [rows, setRows] = useState<OnboardingRow[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const load = useCallback(() => {
    onboarding.everyone().then(setRows).catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load, world.cohortRevision]);

  const shown = useMemo(
    () => (rows ?? []).filter((r) => `${r.name} ${r.patient_id}`.toLowerCase().includes(q.trim().toLowerCase())),
    [rows, q],
  );
  const selected = patientId ?? shown[0]?.patient_id ?? null;

  return (
    <div className="fam">
      <aside className="ui-panel" style={{ minWidth: 260 }}>
        <header>
          <div>
            <h2>Families</h2>
            <p>{rows ? `${rows.filter((r) => !r.activated).length} still being taken on` : "loading…"}</p>
          </div>
          <button type="button" className="btn primary small" onClick={() => setAdding(true)}>
            New family
          </button>
        </header>
        <div className="ui-panel-body">
          <input aria-label="Search families" placeholder="Name or id" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
          {error && <Notice tone="warn">{error}</Notice>}
          {!rows ? (
            <SkeletonRows rows={5} />
          ) : (
            <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {shown.map((r) => (
                <li key={r.patient_id}>
                  <button
                    type="button"
                    className={`btn${r.patient_id === selected ? " primary" : ""}`}
                    style={{ width: "100%", textAlign: "left" }}
                    onClick={() => onOpen(r.patient_id)}
                  >
                    <strong>{r.name}</strong>
                    <span className="hint" style={{ display: "block" }}>
                      {r.activated ? "Active" : `${r.done} of ${r.total} stages`}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      <div className="fam-main">
        {adding && (
          <RegisterFamily
            onRegistered={(id) => {
              setAdding(false);
              toast(`Registered ${id}. Now take them through the stages.`);
              load();
              onOpen(id);
            }}
          />
        )}
        {selected ? (
          <Workspace key={selected} patientId={selected} onChanged={load} />
        ) : (
          <EmptyState title="Nobody to take on yet" icon={<UserPlus />}>
            Start with <strong>New family</strong>.
          </EmptyState>
        )}
      </div>
    </div>
  );
}

type StageId = "identity" | "background" | "documents" | "medical" | "consent" | "admission" | "review";

function Workspace({ patientId, onChanged }: { patientId: string; onChanged: () => void }) {
  const { persona } = usePersona();
  const toast = useToast();
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [stage, setStage] = useState<StageId>("identity");
  const [refused, setRefused] = useState<string[] | null>(null);
  const [revision, setRevision] = useState(0);

  const reload = useCallback(() => {
    onboarding.status(patientId).then(setStatus).catch(() => undefined);
    onChanged();
  }, [patientId, onChanged]);
  useEffect(() => {
    reload();
  }, [reload, revision]);
  const bump = () => setRevision((n) => n + 1);

  if (!status) return <SkeletonRows rows={6} />;
  const done = (id: string) => status.stages.find((s) => s.id === id)?.done ?? false;
  const tabs: { id: StageId; label: string; group: string }[] = [
    { id: "identity", label: "Who they are", group: "From the family" },
    { id: "background", label: "Background", group: "From the family" },
    { id: "documents", label: "Documents", group: "From the family" },
    { id: "medical", label: "Medical background", group: "From the family" },
    { id: "consent", label: "Agreement to share", group: "From the family" },
    { id: "admission", label: "Hospital admission", group: "From the hospital" },
    { id: "review", label: "Review and activate", group: "Finish" },
  ];

  const activate = async () => {
    setRefused(null);
    try {
      await onboarding.activate(patientId);
      toast("Family activated.");
      bump();
    } catch (e) {
      const detail = (e as { detail?: { missing?: string[] } }).detail;
      setRefused(detail?.missing ?? [errorText(e)]);
    }
  };

  return (
    <>
      <header className="fam-head">
        <div className="fam-id">
          <div>
            <h1>{status.name}</h1>
            <p>
              {status.activated ? `Active since ${status.activated.at.slice(0, 10)}` : `${status.done} of ${status.total} stages done`}
            </p>
          </div>
        </div>
        {status.activated ? <Chip tone="go">Active</Chip> : <Chip tone="wait">Being taken on</Chip>}
      </header>

      <nav aria-label="Stages" className="cc-stages" style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "12px 0" }}>
        {tabs.map((t, i) => (
          <button
            key={t.id}
            type="button"
            className={`btn small${stage === t.id ? " primary" : ""}`}
            aria-current={stage === t.id ? "step" : undefined}
            onClick={() => setStage(t.id)}
          >
            {i + 1}. {t.label}
            {t.id !== "review" && <span aria-label={done(t.id) ? "done" : "to do"}> {done(t.id) ? "✓" : "•"}</span>}
          </button>
        ))}
      </nav>

      {stage === "identity" && (
        <SectionForm title="Who they are and how to reach them" patientId={patientId} section="identity" onSaved={bump} />
      )}
      {stage === "background" && (
        <SectionForm title="Background" hint="Used to find the right schemes and support." patientId={patientId} section="background" onSaved={bump} />
      )}
      {stage === "documents" && <Documents patientId={patientId} onChanged={bump} />}
      {stage === "medical" &&
        (["doctor", "admin"].includes(persona.role) ? (
          <SectionForm
            title="Medical background, as the family reports it"
            hint="Kept apart: only doctors and administrators can see this. It is never used to plan a journey or written into a message."
            patientId={patientId}
            section="medical"
            onSaved={bump}
          />
        ) : (
          <Card title="Medical background">
            <Notice tone="calm">
              A doctor records this stage. {done("medical") ? "It has been recorded." : "It is still to do."} It is kept
              apart and is not visible to your role.
            </Notice>
          </Card>
        ))}
      {stage === "consent" && (
        <Card title="Agreement to share" hint="Saathi asks; the family answers in their own words and can withdraw at any time.">
          <ConsentLayer patientId={patientId} revision={revision} canAsk actor={persona.name ?? "staff"} />
          <div className="iss-actions" style={{ marginTop: 10 }}>
            <button type="button" className="btn" onClick={bump}>Check again</button>
          </div>
        </Card>
      )}
      {stage === "admission" && <Admissions patientId={patientId} onChanged={bump} />}
      {stage === "review" && (
        <Card title="Review and activate" hint="Every stage has to be done before the family is activated.">
          <ul className="stack" style={{ listStyle: "none", padding: 0 }}>
            {status.stages.map((s) => (
              <li key={s.id}>
                <strong>{s.done ? "✓" : "•"} {s.title}</strong>
                <span className="hint"> · {s.owner === "family" ? "from the family" : s.owner === "doctor" ? "a doctor records this" : "from the hospital"}</span>
                {s.missing.map((m) => (
                  <div key={m} className="hint">&nbsp;&nbsp;– {m}</div>
                ))}
              </li>
            ))}
          </ul>
          {refused && (
            <Notice tone="warn">
              Not finished yet: {refused.join("; ")}.
            </Notice>
          )}
          <div className="iss-actions" style={{ marginTop: 10 }}>
            <button type="button" className="btn primary" disabled={Boolean(status.activated)} onClick={activate}>
              {status.activated ? "Already active" : status.ready ? "Activate this family" : "Activate (not ready)"}
            </button>
          </div>
        </Card>
      )}
    </>
  );
}

function SectionForm({
  title,
  hint,
  patientId,
  section,
  onSaved,
  choices,
}: {
  title: string;
  hint?: string;
  patientId: string;
  section: string;
  onSaved: () => void;
  choices?: Record<string, { value: string; label: string }[]>;
}) {
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [initial, setInitial] = useState<Record<string, unknown> | null>(null);
  const [by, setBy] = useState<string | undefined>();
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    setSchema(null);
    setInitial(null);
    Promise.all([onboarding.schema(section), onboarding.section(patientId, section)])
      .then(([s, saved]) => {
        setSchema(s);
        setInitial(saved.data);
        setBy(saved.by);
      })
      .catch((e) => setProblem(errorText(e)));
  }, [patientId, section]);

  return (
    <Card title={title} hint={hint}>
      {problem && <Notice tone="warn">{problem}</Notice>}
      {!schema || !initial ? (
        !problem && <SkeletonRows rows={4} />
      ) : (
        <>
          {by && <p className="hint">Last saved by {by}.</p>}
          <SchemaForm
            key={`${patientId}-${section}`}
            schema={schema}
            initial={initial}
            choices={choices}
            onSave={(values) => onboarding.saveSection(patientId, section, values)}
            onSaved={onSaved}
          />
        </>
      )}
    </Card>
  );
}

function Documents({ patientId, onChanged }: { patientId: string; onChanged: () => void }) {
  const [docs, setDocs] = useState<ProfileDocument[] | null>(null);
  const [kinds, setKinds] = useState<{ kind: string; label: string }[]>([]);
  const [kind, setKind] = useState("aadhaar");
  const [number, setNumber] = useState("");
  const [issuer, setIssuer] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    onboarding.documents(patientId).then(setDocs).catch((e) => setError(errorText(e)));
  }, [patientId]);
  useEffect(load, [load]);
  useEffect(() => {
    onboarding.forms().then((f) => setKinds(f.documents)).catch(() => undefined);
  }, []);
  const label = (k: string) => kinds.find((x) => x.kind === k)?.label ?? k;

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      bytes.forEach((b) => (binary += String.fromCharCode(b)));
      await onboarding.upload(patientId, {
        kind,
        number,
        issuer,
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        data_base64: btoa(binary),
      });
      setFile(null);
      setNumber("");
      load();
      onChanged();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const verify = async (id: string) => {
    await onboarding.verify(patientId, id).catch((e) => setError(errorText(e)));
    load();
    onChanged();
  };

  return (
    <Card title="Documents" hint="Aadhaar and a referral letter are needed; the rest help find the right schemes. Files up to 5 MB.">
      {!docs ? (
        <SkeletonRows rows={3} />
      ) : docs.length === 0 ? (
        <p className="empty">Nothing uploaded yet.</p>
      ) : (
        <table className="audit-table">
          <thead>
            <tr><th>Document</th><th>Number</th><th>Issued by</th><th>File</th><th>Checked</th></tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>{label(d.kind)}{d.synthetic && <span className="hint"> · made-up</span>}</td>
                <td className="mono">{d.number_masked || "—"}</td>
                <td>{d.issuer || "—"}</td>
                <td>{d.filename} · {Math.max(1, Math.round(d.size / 1024))} KB</td>
                <td>
                  {d.verified_by ? (
                    <Chip tone="go">checked by {d.verified_by}</Chip>
                  ) : (
                    <button type="button" className="btn small" onClick={() => verify(d.id)}>Mark as checked</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 style={{ marginTop: 16 }}>Add a document</h3>
      <div className="iss-fields cc-form">
        <label>
          <span>Document</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {kinds.map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}
          </select>
        </label>
        <label>
          <span>Number</span>
          <input value={number} placeholder="only the last 4 are kept" onChange={(e) => setNumber(e.target.value)} />
        </label>
        <label>
          <span>Issued by</span>
          <input value={issuer} onChange={(e) => setIssuer(e.target.value)} />
        </label>
        <label>
          <span>File</span>
          <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      </div>
      <div className="iss-actions" style={{ marginTop: 10 }}>
        <button type="button" className="btn primary" disabled={!file || busy} onClick={upload}>
          {busy ? "uploading…" : "Upload"}
        </button>
      </div>
      {error && <Notice tone="warn">{error}</Notice>}
    </Card>
  );
}

function Admissions({ patientId, onChanged }: { patientId: string; onChanged: () => void }) {
  const [list, setList] = useState<AdmissionRecord[] | null>(null);
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [clinicians, setClinicians] = useState<Clinician[]>([]);
  const [pathways, setPathways] = useState<{ id: string; name: string }[]>([]);
  const [steps, setSteps] = useState(0);
  const [orgs, setOrgs] = useState<Organisation[]>([]);
  useEffect(() => {
    directory.list().then(setOrgs).catch(() => undefined);
  }, []);

  const load = useCallback(() => {
    onboarding.admissions(patientId).then(setList).catch(() => setList([]));
  }, [patientId]);
  useEffect(load, [load]);
  useEffect(() => {
    onboarding.schema("admission").then(setSchema).catch(() => undefined);
    registry.hospitals().then(setHospitals).catch(() => undefined);
    registry.clinicians().then(setClinicians).catch(() => undefined);
    onboarding.forms().then((f) => setPathways(f.pathways)).catch(() => undefined);
  }, []);

  const hospitalName = (id: string) => hospitals.find((h) => h.id === id)?.name ?? id;
  const orgChoices = (...types: OrgType[]) =>
    orgs.filter((o) => o.active && types.includes(o.type)).map((o) => ({ value: o.id, label: o.name }));
  const choices = {
    hospital_id: hospitals.filter((h) => h.active).map((h) => ({ value: h.id, label: h.name })),
    clinician_id: clinicians.filter((c) => c.active).map((c) => ({ value: c.id, label: `${c.name} · ${hospitalName(c.hospital_id)}` })),
    pathway_id: pathways.map((p) => ({ value: p.id, label: p.name })),
  };

  return (
    <div className="stack">
      <Card title="Hospital admissions" hint="One record for each visit or stay. A family can have several over time.">
        {!list ? (
          <SkeletonRows rows={2} />
        ) : list.length === 0 ? (
          <p className="empty">No admission recorded yet.</p>
        ) : (
          <table className="audit-table">
            <thead><tr><th>Hospital</th><th>Department</th><th>Kind</th><th>Pathway</th><th>Status</th></tr></thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id}>
                  <td>{hospitalName(a.hospital_id)}</td>
                  <td>{a.department || "—"}</td>
                  <td>{a.type.replace("_", " ")}</td>
                  <td>{pathways.find((p) => p.id === a.pathway_id)?.name ?? a.pathway_id}</td>
                  <td>{a.status}{a.synthetic && <span className="hint"> · made-up</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {schema && hospitals.length > 0 && (
        <Card title="Record a new admission">
          <SchemaForm
            key={list?.length ?? 0}
            schema={schema}
            initial={{ hospital_id: hospitals[0]?.id }}
            choices={choices}
            submitLabel="Record admission"
            onSave={(values) => onboarding.addAdmission(patientId, values)}
            onSaved={() => {
              load();
              onChanged();
            }}
          />
        </Card>
      )}
      <SectionForm
        title="Who this family's journey should use"
        hint="Leave a choice blank and the directory's best fit for their district and hospital is used."
        patientId={patientId}
        section="partners"
        onSaved={onChanged}
        choices={{
          transport: orgChoices("cab", "travel"),
          stay: orgChoices("hotel"),
          medicine: orgChoices("pharmacy"),
          insurance: orgChoices("insurer"),
        }}
      />
      <Card title="Care steps" hint="The visits and reports this admission involves. The family is planned the moment one is added.">
        <AddStep revision={steps} onAdded={() => { setSteps((n) => n + 1); onChanged(); }} />
      </Card>
    </div>
  );
}
