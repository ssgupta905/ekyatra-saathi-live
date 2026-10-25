/**
 * The hospital network's registries and staff accounts. Mirrors backend/saathi/api/registry.py.
 */

import { request } from "./client";
import type { Role } from "./api";

export interface Hospital {
  id: string;
  name: string;
  place: string;
  timezone: string;
  departments: string[];
  active: boolean;
}

export interface NetworkCentre {
  id: string;
  hospital_id: string;
  name: string;
  place: string;
  kind: "hub" | "day_care";
  handles: string[];
  active: boolean;
}

export interface Clinician {
  id: string;
  name: string;
  specialty: string;
  hospital_id: string;
  department: string;
  username: string | null;
  active: boolean;
}

export interface ResourceRecord {
  id: string;
  kind: "machine" | "staff" | "supply";
  display_name: string;
  hospital_id: string;
  department: string;
}

export interface StaffAccount {
  id: string;
  username: string;
  name: string;
  role: Role;
  active: boolean;
}

const send = <T>(method: string, path: string, body: unknown) =>
  request<T>(path, { method, body: JSON.stringify(body) });

export const registry = {
  hospitals: () => request<Hospital[]>("/registry/hospitals"),
  addHospital: (h: Omit<Hospital, "active"> & { active?: boolean }) =>
    send<Hospital>("POST", "/registry/hospitals", h),
  editHospital: (id: string, changes: Partial<Hospital>) =>
    send<Hospital>("PATCH", `/registry/hospitals/${encodeURIComponent(id)}`, changes),

  centres: () => request<NetworkCentre[]>("/registry/centres"),
  addCentre: (c: Omit<NetworkCentre, "active"> & { active?: boolean }) =>
    send<NetworkCentre>("POST", "/registry/centres", c),
  editCentre: (id: string, changes: Partial<NetworkCentre>) =>
    send<NetworkCentre>("PATCH", `/registry/centres/${encodeURIComponent(id)}`, changes),

  clinicians: () => request<Clinician[]>("/registry/clinicians"),
  addClinician: (c: Omit<Clinician, "active"> & { active?: boolean }) =>
    send<Clinician>("POST", "/registry/clinicians", c),
  editClinician: (id: string, changes: Partial<Clinician>) =>
    send<Clinician>("PATCH", `/registry/clinicians/${encodeURIComponent(id)}`, changes),

  resources: () => request<ResourceRecord[]>("/resources"),
  editResource: (id: string, changes: Partial<ResourceRecord>) =>
    send<ResourceRecord>("PATCH", `/resources/${encodeURIComponent(id)}`, changes),

  users: () => request<StaffAccount[]>("/admin/users"),
  addUser: (u: { username: string; name: string; role: Role; password: string }) =>
    send<StaffAccount>("POST", "/admin/users", u),
  editUser: (username: string, changes: Partial<StaffAccount> & { password?: string }) =>
    send<StaffAccount>("PATCH", `/admin/users/${encodeURIComponent(username)}`, changes),
};
