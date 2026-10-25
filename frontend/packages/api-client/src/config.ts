/**
 * Each hospital's rules, what is switched on, and the audit log's filters.
 * Mirrors backend/saathi/api/admin.py and GET /ledger.
 */

import { request } from "./client";
import type { NetworkCentre } from "./registry";

export interface StepRule {
  kind: string;
  lead_days: Record<string, number>;
  weekdays: number[];
  slot_times: string[];
  shift_tolerance_days: number | null;
  confirmed: boolean;
  confirmed_by: string | null;
}

export interface HospitalRules {
  hospital_id: string;
  steps: Record<string, StepRule>;
  stay_rather_than_travel_hours: number;
  reservation_lead_days: number;
  reserved_journey_hours: number;
  unknown_journey_gap_days: number;
  centres: unknown[];
  requirements: Record<string, string[]>;
}

export interface RulesView {
  hospital_id: string;
  policy: HospitalRules;
  version: number;
  saved_by: string | null;
  source: "default" | "saved";
  /** True once this hospital has saved a version: the planner then reads it. */
  used_by_planner: boolean;
  note: string;
  /** Exactly what the planner takes from saved rules, and what it does not yet. */
  read_by_planner: string[];
  not_read_yet: string[];
  centres: NetworkCentre[];
}

export interface RulesVocabulary {
  step_kinds: string[];
  entitlements: Record<string, string>;
  weekdays: string[];
}

export interface Integrations {
  world: string;
  environment: string;
  login: { on: boolean; provider: string; secret_is_default: boolean };
  records_database: string | null;
  language_layer: string | null;
  actors: boolean;
  speech_to_text: string | null;
  reference_cache: { present: boolean; network_lookups: boolean };
  geocoder: string | null;
  router: string | null;
  feeds: { hospital: string | null; schemes: string | null; abdm: boolean };
  channels: { whatsapp: boolean; bhashini: boolean };
  graph_database: boolean;
}

export interface AuditEntry {
  id: string;
  patient_id: string;
  source: string;
  source_record_id: string;
  claim: string;
  recorded_at: string;
  entry_hash: string;
  metadata: Record<string, unknown>;
}

export interface AuditPage {
  intact: boolean;
  total: number;
  offset: number;
  limit: number;
  entries: AuditEntry[];
}

export const config = {
  vocabulary: () => request<RulesVocabulary>("/admin/policy-vocabulary"),
  rules: (hospitalId: string) => request<RulesView>(`/admin/policy/${encodeURIComponent(hospitalId)}`),
  saveRules: (hospitalId: string, rules: HospitalRules) =>
    request<{ version: number; note: string }>(`/admin/policy/${encodeURIComponent(hospitalId)}`, {
      method: "PUT",
      body: JSON.stringify(rules),
    }),
  integrations: () => request<Integrations>("/admin/integrations"),
  audit: (filters: { source?: string; patient_id?: string; q?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams(
      Object.entries(filters)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)]),
    ).toString();
    return request<AuditPage>(`/ledger${query ? `?${query}` : ""}`);
  },
};
