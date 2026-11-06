/**
 * The journey beyond the care steps: which pathway a family is on, what every
 * other party (a ride, a stay, a pharmacy, an insurer) has said, and what the
 * family has agreed to share.
 *
 * Logistics only. A readiness item is a status, a party and a date; a consent
 * grant says who may be told what, never what a record contains.
 */

import { request } from "./client";
import type { Decision } from "./api";

export interface PathwayInfo {
  id: string;
  name: string;
  default_target: string;
  steps: string[];
}

export type ReadinessKind =
  | "slot" | "doctor" | "bed" | "medicine" | "insurance" | "transport" | "stay";
export type ReadinessStatus = "ready" | "pending" | "blocked" | "unknown";

export interface ReadinessItem {
  id: string;
  patient_id: string;
  step_id: string | null;
  kind: ReadinessKind;
  party: string;
  status: ReadinessStatus;
  ready_by: string | null;
  detail: string;
  alternative_available: boolean;
  source: string;
  /** The directory organisation this was asked of, when it came from the directory. */
  partner_id?: string | null;
}

export interface ReadinessInput {
  kind: ReadinessKind;
  party: string;
  status: ReadinessStatus;
  detail?: string;
  alternative_available?: boolean;
  source?: "partner" | "navigator";
}

export const pathways = {
  list: () => request<PathwayInfo[]>("/pathways"),
};

export const readiness = {
  list: (patientId: string) =>
    request<{ patient_id: string; decision: Decision | null; items: ReadinessItem[] }>(
      `/patients/${patientId}/readiness`,
    ),
  put: (patientId: string, body: ReadinessInput) =>
    request<{ item: ReadinessItem; decision: Decision | null; rationale: string }>(
      `/patients/${patientId}/readiness`,
      { method: "PUT", body: JSON.stringify(body) },
    ),
  /** Ask one particular organisation from the directory for a need. */
  ask: (patientId: string, kind: ReadinessKind, organisationId: string) =>
    request<{ item: ReadinessItem; decision: Decision | null }>(
      `/patients/${patientId}/readiness/request`,
      { method: "POST", body: JSON.stringify({ kind, organisation_id: organisationId }) },
    ),
  /** Ask the alternate of an organisation that could not. */
  rebook: (patientId: string, itemId: string) =>
    request<{ item: ReadinessItem; decision: Decision | null }>(
      `/patients/${patientId}/readiness/${itemId}/rebook`,
      { method: "POST" },
    ),
  clear: (patientId: string, itemId: string) =>
    request<{ decision: Decision | null }>(`/patients/${patientId}/readiness/${itemId}`, {
      method: "DELETE",
    }),
};

export type ConsentPurpose = "care_coordination" | "record_movement" | "research";
export type ConsentCapacity = "self" | "nominee" | "guardian";

export interface ConsentGrantView {
  id: string;
  purpose: ConsentPurpose;
  requester: string;
  categories: string[];
  granted_by: string;
  capacity: ConsentCapacity;
  channel: string;
  language: string;
  expires_at: string;
  active: boolean;
  revoked_at: string | null;
}

export interface ConsentPendingView {
  id: string;
  purpose: ConsentPurpose;
  requester: string;
  categories: string[];
  reason: string;
  language: string;
}

export interface ConsentSnapshot {
  records: number;
  grants: ConsentGrantView[];
  pending: ConsentPendingView[];
}

export const consent = {
  snapshot: (patientId: string) => request<ConsentSnapshot>(`/patients/${patientId}/consent`),
  ask: (
    patientId: string,
    body: {
      purpose: ConsentPurpose;
      requester_id: string;
      requester_name: string;
      categories: string[];
      reason?: string;
    },
  ) =>
    request<{ id: string }>(`/patients/${patientId}/consent/requests`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  grant: (
    patientId: string,
    requestId: string,
    body: { granted_by: string; capacity: ConsentCapacity; channel: "whatsapp" | "ivr"; days?: number },
  ) =>
    request<ConsentGrantView>(`/patients/${patientId}/consent/requests/${requestId}/grant`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  revoke: (patientId: string, grantId: string, body: { by: string; reason?: string }) =>
    request<ConsentGrantView>(`/patients/${patientId}/consent/grants/${grantId}/revoke`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
