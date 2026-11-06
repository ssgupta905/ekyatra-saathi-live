/**
 * The network directory, and taking a family on. Mirrors backend/saathi/api/directory.py
 * and api/onboarding.py.
 */

import { ApiError, request } from "./client";

const send = <T>(method: string, path: string, body?: unknown) =>
  request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

// ---------------------------------------------------------------- the directory

export type OrgType =
  | "hospital" | "lab" | "pharmacy" | "medicine_distributor" | "equipment_distributor" | "shop"
  | "cab" | "travel" | "hotel" | "insurer" | "ambulance";

export interface Organisation {
  id: string;
  name: string;
  type: OrgType;
  services: string[];
  districts: string[];
  hospital_ids: string[];
  address: string;
  contact: string;
  hours: string;
  mode: "simulated" | "people";
  answer: "ready" | "cannot";
  delay_seconds: number;
  alternate_id: string | null;
  linked_ids: string[];
  active: boolean;
}

export interface RoleSummary {
  role: string;
  blurb: string;
  routes: number;
  accounts: number;
}

export const directory = {
  types: () => request<{ id: OrgType; label: string }[]>("/directory/types"),
  list: (filter: { type?: OrgType | ""; q?: string; district?: string } = {}) => {
    const params = new URLSearchParams();
    if (filter.type) params.set("type", filter.type);
    if (filter.q) params.set("q", filter.q);
    if (filter.district) params.set("district", filter.district);
    const query = params.toString();
    return request<Organisation[]>(`/directory${query ? `?${query}` : ""}`);
  },
  add: (org: Partial<Organisation> & Pick<Organisation, "id" | "name" | "type">) =>
    send<Organisation>("POST", "/directory", org),
  edit: (id: string, changes: Partial<Organisation>) =>
    send<Organisation>("PATCH", `/directory/${id}`, changes),
  roles: () => request<RoleSummary[]>("/admin/roles"),
};

// ---------------------------------------------------------------- onboarding

/** A JSON Schema as pydantic writes it; only the parts the form renderer reads. */
export interface FormSchema {
  title?: string;
  required?: string[];
  properties: Record<string, SchemaProperty>;
  $defs?: Record<string, SchemaProperty>;
}

export interface SchemaProperty {
  title?: string;
  description?: string;
  type?: string;
  format?: string;
  enum?: string[];
  maxLength?: number;
  minLength?: number;
  minimum?: number;
  maximum?: number;
  pattern?: string;
  default?: unknown;
  $ref?: string;
  anyOf?: SchemaProperty[];
}

export interface OnboardingStage {
  id: string;
  title: string;
  done: boolean;
  missing: string[];
  owner: string;
}

export interface OnboardingStatus {
  patient_id: string;
  name: string;
  stages: OnboardingStage[];
  done: number;
  total: number;
  ready: boolean;
  activated: { by: string; at: string } | null;
}

export interface OnboardingRow {
  patient_id: string;
  name: string;
  done: number;
  total: number;
  ready: boolean;
  activated: { by: string; at: string } | null;
}

export interface ProfileDocument {
  id: string;
  patient_id: string;
  kind: string;
  number_masked: string;
  issuer: string;
  filename: string;
  content_type: string;
  size: number;
  uploaded_by: string;
  verified_by: string | null;
  synthetic: boolean;
}

export interface AdmissionRecord {
  id: string;
  patient_id: string;
  hospital_id: string;
  department: string;
  clinician_id: string | null;
  pathway_id: string;
  type: string;
  referral_source: string;
  expected_on: string | null;
  ward: string;
  bed: string;
  status: string;
  synthetic: boolean;
}

export interface FieldProblem {
  field: string;
  message: string;
}

/** The per-field problems a form save answered with, if that is what went wrong. */
export function fieldProblems(error: unknown): FieldProblem[] | null {
  if (error instanceof ApiError && Array.isArray(error.detail)) {
    const rows = error.detail.filter(
      (d): d is FieldProblem => typeof d === "object" && d !== null && "field" in d && "message" in d,
    );
    return rows.length ? rows : null;
  }
  return null;
}

export interface DemoFamily {
  patient_id: string;
  name: string;
  email: string | null;
  story: string;
}

export const demo = {
  /** Load, or reset, three scripted families whose sign-in codes go to these addresses. */
  loadCast: (emails: string[]) =>
    send<{ families: DemoFamily[] }>("POST", "/demo/cast", { emails }),
};

export const onboarding = {
  forms: () =>
    request<{
      sections: string[];
      documents: { kind: string; label: string }[];
      pathways: { id: string; name: string }[];
    }>("/forms"),
  schema: (name: string) => request<FormSchema>(`/forms/${name}`),
  everyone: () => request<OnboardingRow[]>("/onboarding"),
  status: (patientId: string) => request<OnboardingStatus>(`/patients/${patientId}/onboarding`),
  section: (patientId: string, name: string) =>
    request<{ saved: boolean; data: Record<string, unknown>; by?: string; at?: string }>(
      `/patients/${patientId}/profile/${name}`,
    ),
  saveSection: (patientId: string, name: string, data: Record<string, unknown>) =>
    send<{ saved: boolean }>("PUT", `/patients/${patientId}/profile/${name}`, data),
  documents: (patientId: string) => request<ProfileDocument[]>(`/patients/${patientId}/documents`),
  upload: (
    patientId: string,
    doc: { kind: string; number?: string; issuer?: string; filename: string; content_type: string; data_base64: string },
  ) => send<ProfileDocument>("POST", `/patients/${patientId}/documents`, doc),
  verify: (patientId: string, documentId: string) =>
    send<ProfileDocument>("POST", `/patients/${patientId}/documents/${documentId}/verify`),
  admissions: (patientId: string) => request<AdmissionRecord[]>(`/patients/${patientId}/admissions`),
  addAdmission: (patientId: string, body: Record<string, unknown>) =>
    send<AdmissionRecord>("POST", `/patients/${patientId}/admissions`, body),
  activate: (patientId: string) => send<OnboardingStatus>("POST", `/patients/${patientId}/activate`),
};
