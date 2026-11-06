/**
 * Typed client for the Saathi API.
 *
 * The types here mirror backend/saathi/domain/models.py. They are intentionally
 * narrow: the console can display a plan and its evidence, and nothing else. It
 * has no endpoint that returns report content because the backend has no such
 * endpoint to call.
 */

import { ApiError, apiUrl, authHeaders, request } from "./client";

export type Decision = "go" | "wait" | "uncertain" | "replan";

export type StepStatus =
  | "not_scheduled"
  | "scheduled"
  | "completed"
  | "pending_result"
  | "result_available"
  | "cancelled";

export interface FamilyMember {
  id: string;
  patient_id: string;
  role: string;
  name: string;
  phone: string;
  preferred_channel: "whatsapp" | "ivr";
  language: "hi" | "bn" | "or" | "en";
}

export interface Patient {
  id: string;
  name?: string;
  abha_number?: string | null;
  family_members?: FamilyMember[];
  home_distance_km: number;
  home_district: string;
  language: "hi" | "bn" | "or" | "en";
  caregiver_phone: string;
  caregiver_email?: string | null;
  hospital_id: string;
  /** Which care pathway the family is on; see `pathways.list`. */
  pathway_id?: string;
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
  resource_id?: string | null;
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
  /** "real" when these are a hospital's own records on the real calendar. */
  world?: "demo" | "real";
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

/* ──────────────────────────────────────────────────────────────────────────
   Disruptions
   --------------------------------------------------------------------------
   A desk's one-tap report, the ranked options it produces, and the single
   approval action that fans them out. Order in `options` is the only
   ranking — there is no score field anywhere here, by design.
   ────────────────────────────────────────────────────────────────────────── */

export type DisruptionKind = "machine_down" | "staff_unavailable" | "stock_delay";
/** Everyone who can sign in. `partner` is a vendor answering for one
 *  organisation — not staff, and never able to read a family. */
export type Role =
  | "navigator"
  | "doctor"
  | "desk"
  | "admin"
  | "patient"
  | "caregiver"
  | "partner";

export interface Disruption {
  id: string;
  resource_id: string;
  kind: DisruptionKind;
  raised_by: string;
  raised_at: string;
  unavailable_from: string;
  unavailable_to: string | null;
  note: string;
}

export interface PlanOption extends VisitPlan {
  nights_added: number;
  extra_trips: number;
  dose_delay_days: number;
  /** Journeys needed sooner than a reserved seat can be obtained. Not a cost
   *  like the others — it is a reason the option may be impossible. */
  short_notice_journeys: number;
}

export interface OptionSet {
  patient_id: string;
  disruption_id: string;
  created_at: string;
  options: PlanOption[];
}

export interface PendingOption {
  patient_id: string;
  disruption_id: string;
  option_count: number;
  requires_doctor: boolean;
  created_at: string;
}

/** What the agent took a work-log line to mean. A proposal, never an action. */
export interface WorkLogReading {
  understood: boolean;
  reason?: string;
  resource_id?: string;
  resource_name?: string;
  kind: string;
  unavailable_from?: string;
  unavailable_to?: string | null;
  confidence: "high" | "medium" | "low";
  /** One sentence: what it took the line to mean. */
  read_as: string;
  /** The model that read it, or "pattern match" when none was available. */
  read_by: string;
  note?: string;
}

export const disruptions = {
  pending: () => request<PendingOption[]>("/disruptions/pending"),
  read: (text: string) =>
    request<WorkLogReading>("/disruptions/read", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  raise: (body: {
    resource_id: string;
    kind: DisruptionKind;
    unavailable_from: string;
    unavailable_to?: string | null;
    note?: string;
  }) =>
    request<{ disruption: Disruption; affected_patient_ids: string[] }>("/disruptions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  list: () => request<Disruption[]>("/disruptions"),
  options: (disruptionId: string, patientId: string) =>
    request<OptionSet>(`/disruptions/${disruptionId}/options/${patientId}`),
  approve: (
    disruptionId: string,
    body: { patient_id: string; option_index: number; approved_by_role: Role; approved_by: string },
  ) =>
    request<unknown>(`/disruptions/${disruptionId}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export const ivr = {
  confirm: (confirmation_id: string, digit: string) =>
    request<{ confirmed: boolean }>("/live/ivr-confirm", {
      method: "POST",
      body: JSON.stringify({ confirmation_id, digit }),
    }),
};

export interface AdminConfig {
  readiness: {
    conformal_alpha: number;
    coverage: number;
    queue_turnaround_profiles: Record<
      string,
      { median_days: number; tail_probability: number; tail_extra_days: number }
    >;
  };
  staff: {
    watched_families: number;
    auto_confirm_ticks: number;
    inbound_every_seconds: number;
  };
  languages: string[];
  channels: string[];
  language_layer_enabled: boolean;
  actors_enabled: boolean;
}

export const admin = {
  config: () => request<AdminConfig>("/admin/config"),
  ledger: (params?: { source?: string; since?: string }) => {
    const qs = params
      ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v) as string[][])
      : "";
    return request<LedgerView & { entries: (LedgerEntry & { patient_id: string })[] }>(
      `/ledger${qs}`,
    );
  },
};

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

/* ──────────────────────────────────────────────────────────────────────────
   The two stories
   --------------------------------------------------------------------------
   Rendered from the backend's own beat list rather than a copy of the brief's
   table, so what the story bar promises and what Advance actually runs cannot
   drift apart.
   ────────────────────────────────────────────────────────────────────────── */

export type StoryLane = "desk" | "agents" | "decision" | "family";

export interface StoryBeat {
  action: string;
  actor: string;
  lane: StoryLane;
  headline: string;
  /** The brief's narration time. Durations shown elsewhere are measured. */
  at: string;
  patient_id: string | null;
}

export interface Story {
  id: string;
  title: string;
  who: string;
  patient_id: string;
  total: number;
  index: number;
  done: boolean;
  next: StoryBeat | null;
  beats: StoryBeat[];
}

export interface StoryState {
  stories: Story[];
  scripted: boolean;
}

export const stories = {
  state: () => request<StoryState>("/story"),
  advance: (story: string) =>
    request<LiveSnapshot & { story_beat?: unknown }>("/live/control", {
      method: "POST",
      body: JSON.stringify({ action: "advance_story", story }),
    }),
};

/* ──────────────────────────────────────────────────────────────────────────
   Plan boards
   --------------------------------------------------------------------------
   The pathway layout is computed by the backend, not here. Depth through the
   dependency DAG is a property of the care pathway, and a console that worked
   it out for itself would be a second place the hospital's model of care
   lived — two copies that drift.
   ────────────────────────────────────────────────────────────────────────── */

export interface BoardNode {
  id: string;
  kind: string;
  label: string;
  status: StepStatus;
  scheduled_for: string | null;
  completed_on: string | null;
  result_available_on: string | null;
  queue: string | null;
  resource_id: string | null;
  column: number;
  satisfied: boolean;
  is_target: boolean;
  is_blocking: boolean;
  /** Report steps: a result arrives, nobody travels for it. */
  no_journey: boolean;
  depends_on: string[];
}

export interface BoardWait {
  step_id: string;
  label: string;
  status: string;
  earliest: string | null;
  latest: string | null;
  calibrated: boolean;
  /** A booking is a fact, not a forecast — don't quote coverage at it. */
  from_booking: boolean;
}

export interface PlanBoard {
  patient: { id: string; district: string; language: string; distance_km: number };
  decision: Decision | null;
  travel_on: string | null;
  rationale: string;
  target_step_id: string | null;
  computed_at: string | null;
  plan_ms: number | null;
  sim_date: string;
  nodes: BoardNode[];
  edges: { from: string; to: string }[];
  columns: number;
  waiting_on: BoardWait[];
}

export const boards = {
  one: (patientId: string) => request<PlanBoard>(`/patients/${patientId}/board`),
  /** Watched families by default; `{ everyone: true }` for the whole cohort. */
  all: (opts: { everyone?: boolean } = {}) =>
    request<{ boards: PlanBoard[]; sim_date: string }>(
      opts.everyone ? "/boards?watched=false&limit=500" : "/boards",
    ),
};

/* ──────────────────────────────────────────────────────────────────────────
   The family's own app
   --------------------------------------------------------------------------
   A separate surface, not a persona inside the hospital console. One read
   (`home`) carries everything the phone shows, because this screen is opened
   on a 2G connection and five round trips means five chances to render a
   half-built page.

   `language` is a real change to the family's record — logged, and the current
   plan re-rendered through the language layer and re-checked by the guard. It
   is not a translation of the view.
   ────────────────────────────────────────────────────────────────────────── */

export interface FamilyStep {
  id: string;
  /** The pathway's own step kind. Translated by `i18n.stepWord`. */
  kind: string;
  what: string;
  when: string | null;
  state: "done" | "waiting" | "ahead";
  /** False for reports: a result arrives, nobody travels for it. */
  travels: boolean;
  is_next: boolean;
}

export interface FamilyWait {
  kind: string;
  what: string;
  earliest: string | null;
  latest: string | null;
  /** A booking is a fact; a forecast is a range. */
  certain: boolean;
}

export interface FamilyMessage {
  body: string;
  language: string;
  kind: string;
  sent_at: string;
  /** Held by the guard, so never sent. The phone says a person will call. */
  held: boolean;
  written_by: string | null;
}

export interface FamilyHome {
  patient: {
    id: string;
    district: string;
    language: Patient["language"];
    distance_km: number;
    hours_each_way: number | null;
  };
  decision: Decision | null;
  travel_on: string | null;
  waiting_for: FamilyWait[];
  message: FamilyMessage | null;
  steps: FamilyStep[];
  /** What to carry and the first desk to reach; present once the family may travel. */
  what_to_bring?: string[];
  where_to_go_first?: string | null;
  /** The whole journey in order, with what the family should do now. */
  guide?: JourneyGuide | null;
  sim_date: string;
  updated_at: string | null;
}

export type StageKind =
  | "tests" | "reports" | "insurance" | "pharmacy" | "appointment" | "doctor" | "ride"
  | "stay" | "bed" | "documents" | "visit" | "next_session";
export type StageState = "done" | "waiting" | "problem" | "upcoming";
export type FamilyAction =
  | "nothing_yet" | "wait_for_team" | "keep_documents_ready"
  | "be_ready_for_pickup" | "go_to_first_stop" | "none";

export interface GuideStage {
  id: string;
  kind: StageKind;
  state: StageState;
  /** The first stage not yet done: the one to look at. */
  is_now: boolean;
  action: FamilyAction;
  /** Who has it: "Uber", "the lab". */
  party: string | null;
  detail: string;
  steps: { kind: string; done: boolean; on: string | null }[];
  /** A forecast, never a promise. */
  window: [string, string] | null;
  /** Only the visit, and only when the plan is a GO. */
  on: string | null;
  first_stop: string | null;
  bring: string[];
}

export interface JourneyGuide {
  patient_id: string;
  decision: Decision | null;
  stages: GuideStage[];
  now_stage_id: string | null;
  done: number;
  total: number;
}

export interface NetworkFamily {
  patient_id: string;
  name: string;
  district: string;
  pathway_id: string;
  decision: Decision | null;
  now: string | null;
  done: number;
  total: number;
  stuck: boolean;
  stages: { kind: StageKind; state: StageState; party: string | null; detail: string }[];
}

export interface NetworkBoard {
  families: NetworkFamily[];
  parties: { party: string; waiting: number; problem: number }[];
}

export const network = {
  board: () => request<NetworkBoard>("/network"),
  guide: (patientId: string) => request<JourneyGuide>(`/patients/${patientId}/guide`),
};

export interface ThreadEntry {
  id: string;
  direction: "to_family" | "from_family";
  kind: string;
  body: string;
  language: string;
  channel: string;
  sent_at: string;
  held?: boolean;
  reason?: string | null;
  gloss?: string | null;
  answerable?: boolean;
}

export interface Thread {
  patient_id: string;
  language: string;
  thread: ThreadEntry[];
  unread: number;
}

export interface Transcript {
  text: string;
  language: string;
  model: string;
  bytes: number;
  /** Always false: transcription hands back words, it does not send them. */
  sent: boolean;
}

/** A recording: a browser Blob, or a file on a phone. */
export type AudioUpload = Blob | { uri: string; name: string; type: string };

/** Audio for a message already written and already passed by the guard.
 *  Returns null when no voice is configured, so a caller can hide the control
 *  rather than offer one that does nothing. */
export async function speakMessage(
  patientId: string,
  text: string,
  language?: string,
): Promise<Blob | null> {
  const response = await fetch(apiUrl(`/patients/${encodeURIComponent(patientId)}/voice/say`), {
    method: "POST",
    headers: { "content-type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ text, language }),
  });
  if (!response.ok) return null;
  return response.blob();
}

export const family = {
  home: (patientId: string) => request<FamilyHome>(`/patients/${patientId}/home`),
  thread: (patientId: string) => request<Thread>(`/patients/${patientId}/notifications`),
  chooseLanguage: (patientId: string, language: Patient["language"], chosen_by?: string) =>
    request<{
      patient_id: string;
      language: string;
      changed: boolean;
      rendered: boolean;
      message: { body: string; held: boolean } | null;
    }>(`/patients/${patientId}/language`, {
      method: "PATCH",
      body: JSON.stringify({ language, chosen_by: chosen_by ?? "family" }),
    }),
  /** Speech to text. Returns the words for the family to confirm, nothing more. */
  transcribe: async (patientId: string, audio: AudioUpload, language?: string) => {
    const form = new FormData();
    if ("uri" in audio) {
      // React Native: a file on the device, described rather than loaded.
      form.append("audio", audio as unknown as Blob);
    } else {
      form.append("audio", audio, "reply.webm");
    }
    form.append("patient_id", patientId);
    if (language) form.append("language", language);
    // No content-type header: the runtime sets the multipart boundary itself.
    const response = await fetch(apiUrl("/voice/transcribe"), {
      method: "POST",
      headers: await authHeaders(),
      body: form,
    });
    if (!response.ok) {
      throw new ApiError(
        (await response.text()).slice(0, 200) || `HTTP ${response.status}`,
        response.status,
      );
    }
    return (await response.json()) as Transcript;
  },
  say: (patientId: string, text: string) => live.inject(patientId, undefined, text),
};

/* ──────────────────────────────────────────────────────────────────────────
   The partner's own queue
   --------------------------------------------------------------------------
   A cab firm, a hotel desk, a pharmacy or a scheme desk sees the jobs its own
   organisation was asked to do, and nothing else. A job carries a first name,
   a district and — only when the plan promises one — a day. A contact appears
   only when the family has agreed to share it, and `contact_withheld` says so
   when they have not, rather than leaving a blank nobody can explain.
   ────────────────────────────────────────────────────────────────────────── */

export type PartnerAnswer = "accepted" | "ready" | "cannot";

export interface PartnerJob {
  item_id: string;
  need: string;
  status: string;
  detail: string;
  family: {
    first_name: string;
    district: string;
    /** Null unless the plan promises a date. Never guess one. */
    on: string | null;
    contact: string | null;
    contact_withheld: boolean;
  };
}

export interface PartnerQueue {
  organisation: { id: string; name: string };
  jobs: PartnerJob[];
}

export const partner = {
  jobs: () => request<PartnerQueue>("/partner/jobs"),
  answer: (itemId: string, answer: PartnerAnswer, reason = "") =>
    request<{ item_id: string; status: string; detail: string }>(
      `/partner/jobs/${encodeURIComponent(itemId)}`,
      { method: "POST", body: JSON.stringify({ answer, reason }) },
    ),
};
