import { useState, type FormEvent } from "react";
import { fieldProblems, type FormSchema, type SchemaProperty } from "@saathi/api-client";
import { Notice } from "@saathi/ui-web";
import { errorText } from "./RecordForm";

type Values = Record<string, string | boolean>;

interface Resolved {
  key: string;
  label: string;
  hint?: string;
  required: boolean;
  nullable: boolean;
  kind: "text" | "email" | "tel" | "date" | "number" | "textarea" | "select" | "checkbox";
  options?: string[];
  prop: SchemaProperty;
}

const NAMED: Record<string, string> = {
  hi: "Hindi", bn: "Bengali", or: "Odia", en: "English",
  whatsapp: "WhatsApp", ivr: "Voice call", opd: "Outpatient visit", day_care: "Day care",
  not_stated: "Prefer not to say", apl: "APL", bpl: "BPL", aay: "AAY (Antyodaya)",
};  // prettier-ignore

/** Helper text sits inside a label, which is set in capitals; messages read better in sentences. */
const PLAIN = { textTransform: "none", letterSpacing: "normal" } as const;

const words = (text: string) =>
  NAMED[text] ?? text.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** Follow a $ref and unwrap "X or null", the two shapes pydantic writes around a field. */
function resolve(key: string, raw: SchemaProperty, schema: FormSchema): Resolved {
  let prop = raw;
  let nullable = false;
  if (prop.anyOf) {
    nullable = prop.anyOf.some((o) => o.type === "null");
    const inner = prop.anyOf.find((o) => o.type !== "null") ?? {};
    prop = { ...inner, title: raw.title, description: raw.description, default: raw.default };
  }
  if (prop.$ref) {
    const target = schema.$defs?.[prop.$ref.split("/").pop() ?? ""] ?? {};
    prop = { ...target, title: raw.title ?? prop.title, description: raw.description, default: raw.default };
  }
  let kind: Resolved["kind"] = "text";
  if (prop.enum) kind = "select";
  else if (prop.type === "boolean") kind = "checkbox";
  else if (prop.type === "integer" || prop.type === "number") kind = "number";
  else if (prop.format === "date") kind = "date";
  else if (prop.pattern?.includes("@")) kind = "email";
  else if (/phone/i.test(key)) kind = "tel";
  else if ((prop.maxLength ?? 0) > 300) kind = "textarea";
  return {
    key,
    label: prop.title ?? words(key),
    hint: prop.description,
    required: schema.required?.includes(key) ?? false,
    nullable,
    kind,
    options: prop.enum,
    prop,
  };
}

const initialValue = (field: Resolved, saved: unknown): string | boolean => {
  const value = saved ?? field.prop.default;
  if (field.kind === "checkbox") return Boolean(value);
  return value == null ? "" : String(value);
};

/**
 * Draws any form from its JSON Schema, so a field added on the server appears
 * here with no change to this screen. Problems the server finds are shown next
 * to the field they belong to.
 */
export function SchemaForm({
  schema,
  initial,
  submitLabel = "Save",
  disabled = false,
  choices = {},
  onSave,
  onSaved,
}: {
  schema: FormSchema;
  initial: Record<string, unknown>;
  submitLabel?: string;
  disabled?: boolean;
  /** Fields whose options come from elsewhere (hospitals, doctors): drawn as a list to pick from. */
  choices?: Record<string, { value: string; label: string }[]>;
  onSave: (values: Record<string, unknown>) => Promise<unknown>;
  onSaved?: () => void;
}) {
  const fields = Object.entries(schema.properties).map(([k, p]) => resolve(k, p, schema));
  const [values, setValues] = useState<Values>(() =>
    Object.fromEntries(fields.map((f) => [f.key, initialValue(f, initial[f.key])])),
  );
  const [problems, setProblems] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const set = (key: string, value: string | boolean) => {
    setValues((prev) => ({ ...prev, [key]: value }));
    setProblems((prev) => {
      const { [key]: _gone, ...rest } = prev; // an error clears the moment the field is touched
      return rest;
    });
    setSaved(false);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setGeneral(null);
    setProblems({});
    const out: Record<string, unknown> = {};
    for (const f of fields) {
      const v = values[f.key];
      if (f.kind === "checkbox") out[f.key] = Boolean(v);
      else if (String(v).trim() === "") out[f.key] = f.nullable || f.kind === "date" || f.kind === "number" ? null : "";
      else out[f.key] = f.kind === "number" ? Number(v) : String(v).trim();
    }
    try {
      await onSave(out);
      setSaved(true);
      onSaved?.();
    } catch (e) {
      const found = fieldProblems(e);
      if (found) setProblems(Object.fromEntries(found.map((p) => [p.field, p.message])));
      else setGeneral(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate>
      <div className="iss-fields cc-form">
        {fields.map((f) => {
          const problem = problems[f.key];
          const id = `f-${f.key}`;
          const common = {
            id,
            disabled,
            "aria-invalid": problem ? true : undefined,
            "aria-describedby": problem ? `${id}-err` : undefined,
          };
          return (
            <label key={f.key} htmlFor={id} className={f.kind === "checkbox" ? "cc-check" : ""}>
              <span>
                {f.label}
                {f.required && <span aria-hidden> *</span>}
              </span>
              {f.kind === "select" || choices[f.key] ? (
                <select {...common} value={String(values[f.key])} onChange={(e) => set(f.key, e.target.value)}>
                  {(f.nullable || choices[f.key]) && <option value="">—</option>}
                  {(choices[f.key] ?? f.options?.map((o) => ({ value: o, label: words(o) })) ?? []).map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : f.kind === "checkbox" ? (
                <input {...common} type="checkbox" checked={Boolean(values[f.key])} onChange={(e) => set(f.key, e.target.checked)} />
              ) : f.kind === "textarea" ? (
                <textarea {...common} rows={3} value={String(values[f.key])} onChange={(e) => set(f.key, e.target.value)} />
              ) : (
                <input
                  {...common}
                  type={f.kind === "text" ? "text" : f.kind}
                  inputMode={f.kind === "number" ? "numeric" : undefined}
                  min={f.prop.minimum}
                  max={f.prop.maximum}
                  value={String(values[f.key])}
                  onChange={(e) => set(f.key, e.target.value)}
                />
              )}
              {f.hint && !problem && <span className="hint" style={PLAIN}>{f.hint}</span>}
              {problem && (
                <span id={`${id}-err`} className="auth-error" role="alert" style={PLAIN}>
                  {problem}
                </span>
              )}
            </label>
          );
        })}
      </div>
      <div className="iss-actions" style={{ marginTop: 12 }}>
        <button className="btn primary" disabled={busy || disabled}>
          {busy ? "saving…" : submitLabel}
        </button>
        {saved && <span className="hint" role="status">Saved.</span>}
      </div>
      {general && <Notice tone="warn">{general}</Notice>}
    </form>
  );
}
