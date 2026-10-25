import { useState, type FormEvent } from "react";
import { ApiError } from "@saathi/api-client";
import { Card, Notice } from "@saathi/ui-web";

/** One field of a registry form. Lists are typed comma-separated and stored as arrays. */
export interface Field {
  key: string;
  label: string;
  type?: "text" | "list" | "select" | "checkbox" | "password";
  options?: { value: string; label: string }[];
  /** Fixed once created: ids are what other records point at. */
  lockedWhenEditing?: boolean;
  placeholder?: string;
}

type Values = Record<string, unknown>;

const toInput = (field: Field, value: unknown): string | boolean => {
  if (field.type === "checkbox") return Boolean(value);
  if (field.type === "list") return Array.isArray(value) ? value.join(", ") : "";
  return value == null ? "" : String(value);
};

const fromInput = (field: Field, value: string | boolean): unknown => {
  if (field.type === "checkbox") return value;
  if (field.type === "list")
    return String(value)
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
  const text = String(value).trim();
  return text === "" ? null : text;
};

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (typeof e.detail === "string") return e.detail;
    if (Array.isArray(e.detail)) {
      return e.detail
        .map((d: { loc?: string[]; msg?: string }) => `${(d.loc ?? []).slice(-1)[0] ?? ""}: ${d.msg ?? ""}`)
        .join("; ");
    }
    return e.message;
  }
  return String(e);
}

/**
 * Add or edit one registry record. Only the changed fields are sent on an edit,
 * so the ledger row says exactly what changed.
 */
export function RecordForm({
  title,
  fields,
  initial,
  editing,
  onSave,
  onClose,
}: {
  title: string;
  fields: Field[];
  initial: Values;
  editing: boolean;
  onSave: (values: Values) => Promise<unknown>;
  onClose: () => void;
}) {
  const [values, setValues] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(fields.map((f) => [f.key, toInput(f, initial[f.key])])),
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const out: Values = {};
    for (const field of fields) {
      if (editing && field.lockedWhenEditing) continue;
      const next = fromInput(field, values[field.key]);
      const before = fromInput(field, toInput(field, initial[field.key]));
      if (editing && JSON.stringify(next) === JSON.stringify(before)) continue;
      if (next === null && field.type === "password") continue;
      out[field.key] = next;
    }
    try {
      await onSave(out);
      onClose();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={title} aside={<button type="button" className="btn small" onClick={onClose}>Close</button>}>
      <form onSubmit={submit}>
        <div className="iss-fields cc-form">
          {fields.map((field) => {
            const locked = editing && field.lockedWhenEditing;
            const value = values[field.key];
            const set = (v: string | boolean) => setValues((prev) => ({ ...prev, [field.key]: v }));
            return (
              <label key={field.key} className={field.type === "checkbox" ? "cc-check" : ""}>
                {field.label}
                {field.type === "select" ? (
                  <select value={String(value)} disabled={locked} onChange={(e) => set(e.target.value)}>
                    {field.options?.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : field.type === "checkbox" ? (
                  <input type="checkbox" checked={Boolean(value)} onChange={(e) => set(e.target.checked)} />
                ) : (
                  <input
                    type={field.type === "password" ? "password" : "text"}
                    value={String(value)}
                    readOnly={locked}
                    placeholder={field.placeholder}
                    onChange={(e) => set(e.target.value)}
                  />
                )}
              </label>
            );
          })}
        </div>
        <div className="iss-actions" style={{ marginTop: 12 }}>
          <button className="btn primary" disabled={busy}>
            {busy ? "saving…" : editing ? "Save changes" : "Add"}
          </button>
          <span className="hint">Every change is written to the audit log with your name.</span>
        </div>
        {error && <Notice tone="warn">{error}</Notice>}
      </form>
    </Card>
  );
}
