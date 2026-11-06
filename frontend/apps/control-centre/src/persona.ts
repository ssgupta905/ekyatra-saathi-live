import type { Role } from "@saathi/api-client";

/**
 * The people the control centre can be used as.
 *
 * In the demo there is no password: a presenter picks a person, as the brief's
 * "sign in as Seema" table describes, and the console offers what that role does.
 * The server still decides what the role may do. Signed in for real, the person is
 * whoever logged in, and this list only lends them a title.
 */
export interface Persona {
  id: string;
  name: string;
  role: Role;
  /** What the role-specific screens call them, e.g. "Radiology desk". */
  title: string;
  /** For a family persona: the family they belong to. */
  patientFocus?: string;
}

export const STAFF_ROLES: Role[] = ["navigator", "desk", "doctor", "admin"];

//  Matches the brief's "How to present both stories" table.
export const ROSTER: Persona[] = [
  { id: "seema", name: "Seema Kamble", role: "navigator", title: "Patient navigator" },
  { id: "kavita", name: "Kavita Kumari", role: "navigator", title: "Patient navigator" },
  { id: "imran", name: "Imran Shaikh", role: "desk", title: "Radiology desk" },
  { id: "sanjay", name: "Sanjay Verma", role: "desk", title: "Cardiology desk" },
  { id: "rekha", name: "Rekha Kumari", role: "desk", title: "Day-care desk" },
  { id: "menon", name: "Dr R. Menon", role: "doctor", title: "Head and neck surgeon" },
  { id: "sinha", name: "Dr Amrita Sinha", role: "doctor", title: "Treating oncologist" },
  { id: "neha", name: "Neha", role: "admin", title: "Administrator" },
  { id: "rohini", name: "Rohini", role: "admin", title: "Administrator" },
  { id: "vikash", name: "Vikash", role: "caregiver", title: "Caregiver — Shambhu Prasad", patientFocus: "P-SHAMBHU" },
  { id: "manoj", name: "Manoj Kumar", role: "caregiver", title: "Caregiver — Anita Devi", patientFocus: "P-ANITA" },
  { id: "priya", name: "Priya Kumari", role: "caregiver", title: "Caregiver — Anita Devi", patientFocus: "P-ANITA" },
];

export const ROLE_TITLES: Record<Role, string> = {
  navigator: "Patient navigator",
  desk: "Hospital desk",
  doctor: "Doctor",
  admin: "Administrator",
  caregiver: "Caregiver",
  patient: "Patient",
  //: Listed for completeness; a partner signs in to its own app, not this one.
  partner: "Network partner",
};

export const ROLE_GROUPS: { role: Role; label: string; does: string }[] = [
  { role: "navigator", label: "Navigators", does: "Families, plans, alerts, approvals that do not touch treatment" },
  { role: "desk", label: "Hospital desks", does: "Report outages, confirm and release reports, enter records" },
  { role: "doctor", label: "Doctors", does: "Approve re-plans that touch treatment or a dose date" },
  { role: "admin", label: "Administrators", does: "Registries, configuration, the audit log, the operator panel" },
  { role: "caregiver", label: "Families", does: "Open the family's own app, as that family sees it" },
];

const STORAGE_KEY = "saathi.persona";

export function storedPersona(): Persona | null {
  const fromUrl = new URLSearchParams(window.location.search).get("persona");
  const id = fromUrl ?? safeGet();
  return ROSTER.find((p) => p.id === id && STAFF_ROLES.includes(p.role)) ?? null;
}

export function rememberPersona(persona: Persona | null): void {
  try {
    if (persona) window.localStorage.setItem(STORAGE_KEY, persona.id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* a private window keeps it for this tab only */
  }
}

function safeGet(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}
