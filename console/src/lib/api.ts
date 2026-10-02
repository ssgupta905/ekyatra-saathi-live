/**
 * Typed client for the Saathi API.
 *
 * The types here mirror backend/saathi/domain/models.py. They are intentionally
 * narrow: the console can display a plan and its evidence, and nothing else. It
 * has no endpoint that returns report content because the backend has no such
 * endpoint to call.
 */

export type Decision = "go" | "wait" | "uncertain";

export type StepStatus =
  | "not_scheduled"
  | "scheduled"
  | "completed"
  | "pending_result"
  | "result_available"
  | "cancelled";

export interface Patient {
  id: string;
  home_distance_km: number;
  home_district: string;
  language: "hi" | "bn" | "or" | "en";
  caregiver_phone: string;
  hospital_id: string;
}

export interface CareStep {
  id: string;
  patient_id: string;
  kind: string;
  status: StepStatus;
  scheduled_for: string | null;
  completed_on: string | null;
  result_available_on: string | null;
  queue: string | null;
}

export interface ReadinessWindow {
  step_id: string;
  earliest: string;
  latest: string;
  alpha: number;
  calibrated: boolean;
  n_calibration: number;
}

export interface BlockedPrerequisite {
  step_id: string;
  kind: string;
  status: StepStatus;
  expected_ready: ReadinessWindow | null;
}

export interface EvidenceRef {
  ledger_id: string;
  source: string;
  source_record_id: string;
}

export interface VisitPlan {
  patient_id: string;
  target_step_id: string;
  decision: Decision;
  travel_on: string | null;
  bundled_step_ids: string[];
  blocked_by: BlockedPrerequisite[];
  what_to_bring: string[];
  where_to_go_first: string | null;
  evidence: EvidenceRef[];
  rationale: string;
}

export interface PlanResponse {
  plan: VisitPlan | null;
  message_body: string | null;
  routed_to_care_team: boolean;
  escalation: string | null;
  /** Provenance of the run itself — when it was decided and what it cost. Null
   *  on a forced recompute, which has no place in the world's history. */
  computed_at: string | null;
  sim_date: string | null;
  plan_ms: number | null;
  render_ms: number | null;
  rendered_by: string | null;
}

export interface Alert {
  id: string;
  patient_id: string;
  kind: string;
  raised_at: string;
  detail: string;
}

export interface Metrics {
  patients: number;
  baseline_wasted_trips: number;
  saathi_wasted_trips: number;
  wasted_trips_avoided: number;
  baseline_waste_rate: number;
  saathi_waste_rate: number;
  non_medical_cost_avoided_inr: number;
}

export interface LedgerEntry {
  id: string;
  source: string;
  source_record_id: string;
  claim: string;
  recorded_at: string;
  entry_hash: string;
}

export interface LedgerView {
  intact: boolean;
  entries: LedgerEntry[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  patients: () => request<Patient[]>("/patients"),
  steps: (patientId: string) => request<CareStep[]>(`/patients/${patientId}/steps`),
  plan: (patientId: string) =>
    request<PlanResponse>("/plan", {
      method: "POST",
      body: JSON.stringify({ patient_id: patientId }),
    }),
  alerts: () => request<Alert[]>("/alerts"),
  metrics: () => request<Metrics>("/metrics"),
  ledger: (patientId: string) => request<LedgerView>(`/ledger/${patientId}`),
};

export const LANGUAGE_NAMES: Record<Patient["language"], string> = {
  hi: "Hindi",
  bn: "Bengali",
  or: "Odia",
  en: "English",
};

/* ──────────────────────────────────────────────────────────────────────────
   The live world
   --------------------------------------------------------------------------
   The console reads the world through these and, with two exceptions, cannot
   change it. The exceptions are both *inputs* rather than decisions: a desk
   clerk confirming a record, and a person putting a message in a family's
   mouth. Everything that follows happens because the system reacted.
   ────────────────────────────────────────────────────────────────────────── */

export interface LiveSnapshot {
  start: string;
  current: string;
  day: number;
  seconds_per_day: number;
  running: boolean;
  patients: number;
  watched: string[];
  pending_reports: number;
  desk_queue: number;
  counters: Record<string, number>;
  metrics: Metrics | Record<string, never>;
  language_layer: string | null;
  actors_enabled: boolean;
  inbound_every_seconds: number;
  alerts: number;
}

export interface DeskCandidate {
  id: string;
  patient_id: string;
  step_id: string;
  step_kind: string;
  note: string;
  parsed: Record<string, unknown>;
  raised_on: string;
  raised_at: string;
  ticks_until_auto: number;
  drafted_by: "groq" | "template";
}

export interface InboundMessage {
  id: string;
  patient_id: string;
  text: string;
  gloss: string | null;
  language: string;
  answerable: boolean;
  reason: string | null;
  triggers: string[];
  received_at: string;
  sim_date: string;
  origin: "actor" | "typed";
}

export interface BriefLine {
  text: string;
  ledger_ids: string[];
}

export interface CallBrief {
  available: boolean;
  lines: BriefLine[];
  reason?: string;
  model?: string;
}

export interface NarratedNode {
  id: string;
  text: string;
  held: boolean;
  reason: string | null;
  language: string;
}

export interface Narration {
  available: boolean;
  nodes: NarratedNode[];
  reason?: string;
  language?: string;
  model?: string;
}

export type ControlAction = "play" | "pause" | "step" | "reset" | "speed";

export const live = {
  snapshot: () => request<LiveSnapshot>("/live"),
  control: (action: ControlAction, seconds_per_day?: number) =>
    request<LiveSnapshot>("/live/control", {
      method: "POST",
      body: JSON.stringify({ action, seconds_per_day }),
    }),
  deskQueue: () => request<DeskCandidate[]>("/desk/queue"),
  confirm: (candidate_id: string) =>
    request<{ confirmed: boolean }>("/desk/confirm", {
      method: "POST",
      body: JSON.stringify({ candidate_id }),
    }),
  inject: (patient_id: string, kind?: string, text?: string) =>
    request<InboundMessage>("/live/inject", {
      method: "POST",
      body: JSON.stringify({ patient_id, kind, text }),
    }),
  inbound: (patientId?: string) =>
    request<InboundMessage[]>(patientId ? `/inbound?patient_id=${patientId}` : "/inbound"),
  brief: (patientId: string) => request<CallBrief>(`/patients/${patientId}/brief`),
  narration: (patientId: string, nodes: { id: string; text: string }[]) =>
    request<Narration>(`/patients/${patientId}/narration`, {
      method: "POST",
      body: JSON.stringify({ nodes }),
    }),
};
