import { useState } from "react";
import { ApiError, records, type Language } from "@saathi/api-client";
import { Card, Notice } from "@saathi/ui-web";

const LANGUAGES: Record<Language, string> = { hi: "Hindi", bn: "Bengali", or: "Odia", en: "English" };

/**
 * Putting a family on record. The fields are the ones the planner and the
 * messages actually use: where they live (how far, and for the journey), which
 * language they are written to, and who to reach. Nothing about the illness.
 */
export function RegisterFamily({ onRegistered }: { onRegistered: (patientId: string) => void }) {
  const [form, setForm] = useState({
    name: "",
    home_district: "",
    home_distance_km: "",
    language: "hi" as Language,
    caregiver_phone: "",
    hospital_id: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const ready =
    form.home_district.trim() &&
    form.caregiver_phone.trim().length >= 5 &&
    form.hospital_id.trim() &&
    Number(form.home_distance_km) >= 0 &&
    form.home_distance_km !== "";

  const submit = async () => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const patient = await records.registerPatient({
        name: form.name.trim(),
        home_district: form.home_district.trim(),
        home_distance_km: Number(form.home_distance_km),
        language: form.language,
        caregiver_phone: form.caregiver_phone.trim(),
        hospital_id: form.hospital_id.trim(),
      });
      setDone(patient.id);
      onRegistered(patient.id);
      setForm({ ...form, name: "", home_district: "", home_distance_km: "", caregiver_phone: "" });
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409 ? "That family is already on record." : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Register a family" hint="who they are and how to reach them">
      <div className="iss-fields">
        <label>
          Family name
          <input value={form.name} onChange={(e) => set({ name: e.target.value })} />
        </label>
        <label>
          District
          <input value={form.home_district} onChange={(e) => set({ home_district: e.target.value })} />
        </label>
        <label>
          Distance to hospital (km)
          <input
            type="number"
            min={0}
            value={form.home_distance_km}
            onChange={(e) => set({ home_distance_km: e.target.value })}
          />
        </label>
        <label>
          Language
          <select value={form.language} onChange={(e) => set({ language: e.target.value as Language })}>
            {Object.entries(LANGUAGES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Caregiver phone
          <input value={form.caregiver_phone} onChange={(e) => set({ caregiver_phone: e.target.value })} />
        </label>
        <label>
          Hospital id
          <input
            value={form.hospital_id}
            placeholder="e.g. TMH-MUM"
            onChange={(e) => set({ hospital_id: e.target.value })}
          />
        </label>
      </div>
      <div className="iss-actions" style={{ marginTop: 10 }}>
        <button type="button" className="btn primary" disabled={busy || !ready} onClick={submit}>
          {busy ? "saving…" : "Register"}
        </button>
      </div>
      {error && <Notice tone="warn">{error}</Notice>}
      {done && <Notice tone="calm">Registered {done}. Add their steps below and they are planned at once.</Notice>}
    </Card>
  );
}
