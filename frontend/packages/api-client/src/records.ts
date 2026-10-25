/**
 * Entering and importing a hospital's records (the real world only).
 *
 * In the demo these answer 409, because the cohort is generated and a reset
 * would discard anything entered.
 */

import { request } from "./client";
import type { CareStep, Patient, StepStatus } from "./api";

export type Language = Patient["language"];

export interface PatientInput {
  id?: string;
  name?: string;
  abha_number?: string | null;
  home_district: string;
  home_distance_km: number;
  language: Language;
  caregiver_phone: string;
  hospital_id: string;
  plan_target?: string | null;
}

export interface StepInput {
  id?: string;
  kind: string;
  status: StepStatus;
  scheduled_for?: string | null;
  completed_on?: string | null;
  queue?: string | null;
  resource_id?: string | null;
}

/** Whether the system can say when a pending report will land, said at entry. */
export interface Forecast {
  queue: string | null;
  calibrated: boolean;
  observations: number;
  note: string | null;
}

export interface ImportIssue {
  where: string;
  message: string;
}

export interface ImportReport {
  counts: {
    patients: number;
    family_members: number;
    steps: number;
    errors: number;
    skipped: number;
  };
  errors: ImportIssue[];
  skipped: ImportIssue[];
  committed: { applied: boolean; released: number; replanned: number } | null;
}

export const records = {
  registerPatient: (body: PatientInput) =>
    request<Patient>("/patients", { method: "POST", body: JSON.stringify(body) }),

  addStep: (patientId: string, body: StepInput) =>
    request<{ step: CareStep; forecast: Forecast | null }>(`/patients/${patientId}/steps`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  editPatient: (patientId: string, changes: Partial<PatientInput>) =>
    request<Patient>(`/patients/${patientId}`, { method: "PATCH", body: JSON.stringify(changes) }),

  editStep: (stepId: string, changes: Partial<StepInput>) =>
    request<{ step: CareStep; forecast: Forecast | null }>(`/steps/${stepId}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  release: (stepId: string, by: string, note = "") =>
    request<{ step: CareStep }>(`/steps/${stepId}/release`, {
      method: "POST",
      body: JSON.stringify({ by, note }),
    }),

  /** Without `commit` this is a dry run: it writes nothing and says what it would. */
  importCsv: (text: string, commit: boolean) =>
    request<ImportReport>(`/import/csv?commit=${commit}`, {
      method: "POST",
      body: text,
      headers: { "content-type": "text/csv" },
    }),

  importFhir: (
    bundle: unknown,
    options: { hospitalId: string; commit: boolean; defaultDistanceKm?: number },
  ) => {
    const query = new URLSearchParams({
      hospital_id: options.hospitalId,
      commit: String(options.commit),
    });
    if (options.defaultDistanceKm !== undefined) {
      query.set("default_distance_km", String(options.defaultDistanceKm));
    }
    return request<ImportReport>(`/import/fhir?${query}`, {
      method: "POST",
      body: JSON.stringify(bundle),
    });
  },
};
