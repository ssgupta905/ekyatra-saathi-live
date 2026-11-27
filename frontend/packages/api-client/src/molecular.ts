/**
 * The molecular register: which tests a patient has had, and where the reports
 * are. Mirrors `backend/saathi/api/molecular.py`.
 *
 * There is no result in any of these types, and there is no field one could be
 * put in. That is the point of the feature, so it is the shape of the client
 * too: a reader of this file should not have to be told the rule, because
 * there is nowhere here to break it.
 */

import { request } from "./client";

export type MolecularTest =
  | "karyotype"
  | "fish"
  | "ihc"
  | "single_gene"
  | "targeted_panel"
  | "exome"
  | "genome"
  | "transcriptome"
  | "proteomic"
  | "other";

/** Where the report is — the only state worth tracking. */
export type MolecularState = "awaited" | "held" | "elsewhere";

export interface MolecularRow {
  id: string;
  patient_id: string;
  test: MolecularTest;
  test_name: string;
  state: MolecularState;
  lab_name: string;
  ordered_by_centre: string;
  ordered_on: string | null;
  reported_on: string | null;
  document_ref: string;
  note: string;
  recorded_at: string;
  recorded_by: string;
  summary: string;
  can_be_fetched: boolean;
}

export interface MolecularRegister {
  patient_id: string;
  /** False means nobody has asked this family yet — not that they have no tests. */
  consented: boolean;
  reports: MolecularRow[];
  /** Reports that exist but cannot be fetched from here. What causes a repeat. */
  not_reachable: number;
  why?: string;
}

export interface NewMolecularRow {
  test: MolecularTest;
  state: MolecularState;
  lab_name?: string;
  ordered_by_centre?: string;
  ordered_on?: string | null;
  reported_on?: string | null;
  document_ref?: string;
  note?: string;
}

export const molecular = {
  register: (patientId: string) =>
    request<MolecularRegister>(`/patients/${patientId}/molecular`),
  record: (patientId: string, body: NewMolecularRow) =>
    request<{ id: string; summary: string; state: MolecularState }>(
      `/patients/${patientId}/molecular`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  forget: (patientId: string) =>
    request<{ patient_id: string; removed: number }>(
      `/patients/${patientId}/molecular`,
      { method: "DELETE" },
    ),
};
