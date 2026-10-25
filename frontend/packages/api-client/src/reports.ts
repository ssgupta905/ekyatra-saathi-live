/**
 * Report status, timing and provenance — never content. Mirrors backend/saathi/api/reports.py.
 */

import { request } from "./client";
import type { ReadinessWindow, StepStatus } from "./api";

/** Where a report stands against its window, as one sortable word. */
export type ReportState =
  | "overdue"
  | "due"
  | "waiting"
  | "no_forecast"
  | "no_window"
  | "released"
  | "cancelled";

export interface ReportRow {
  step_id: string;
  patient_id: string;
  patient_name: string;
  district: string;
  hospital_id: string;
  kind: string;
  queue: string | null;
  status: StepStatus;
  sample_taken_on: string | null;
  released_on: string | null;
  turnaround_days: number | null;
  window: ReadinessWindow | null;
  state: ReportState;
  release: { ledger_id: string; by: string | null; recorded_at: string } | null;
}

export interface ReportList {
  today: string;
  counts: Partial<Record<ReportState, number>>;
  reports: ReportRow[];
}

export interface QueueForecast {
  queue: string;
  observations: number;
  calibrated: boolean;
  interval_days: [number, number] | null;
  pending: number;
  released: number;
  observed_coverage: number | null;
}

export interface QueueForecasts {
  alpha: number;
  coverage_target: number;
  min_calibration: number;
  queues: QueueForecast[];
}

export const reports = {
  list: (filters: { patient_id?: string; queue?: string; hospital?: string; report_state?: string } = {}) => {
    const query = new URLSearchParams(
      Object.entries(filters).filter((e): e is [string, string] => Boolean(e[1])),
    ).toString();
    return request<ReportList>(`/reports${query ? `?${query}` : ""}`);
  },
  queues: () => request<QueueForecasts>("/readiness/queues"),
};
