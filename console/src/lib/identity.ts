/**
 * Who is signed in to this console right now.
 *
 * A deliberate prototype simplification: identity lives in this browser tab's
 * localStorage, not behind real authentication. The roster below exists so
 * the demo can be presented exactly as the team brief's table describes it —
 * "sign in as Seema", "sign in as Dr Sinha" — but nothing here is a security
 * boundary. The role a mutation is approved under is a field on the request
 * body, checked server-side regardless of what this picker shows; swapping
 * personas here changes what the console *offers* to do, not what the
 * backend *allows*.
 */

import { useCallback, useEffect, useState } from "react";
import type { Role } from "./api";

export interface Persona {
  id: string;
  name: string;
  role: Role;
  /** A short label for the role-specific screen, e.g. "Radiology desk". */
  title: string;
  /** The resource id this desk reports against, for desks only. */
  deskResourceId?: string;
  /** The family this persona is focused on, for patient/caregiver personas. */
  patientFocus?: string;
}

//  Matches the brief's "How to present both stories" table (page 8).
export const ROSTER: Persona[] = [
  { id: "seema", name: "Seema Kamble", role: "navigator", title: "Patient navigator" },
  { id: "kavita", name: "Kavita Kumari", role: "navigator", title: "Patient navigator" },
  {
    id: "imran", name: "Imran Shaikh", role: "desk", title: "Radiology desk",
    deskResourceId: "MRI-2",
  },
  {
    id: "sanjay", name: "Sanjay Verma", role: "desk", title: "Cardiology desk",
    deskResourceId: "echo-cardiologist",
  },
  {
    id: "rekha", name: "Rekha Kumari", role: "desk", title: "Day-care desk",
    deskResourceId: "day-care-pharmacy",
  },
  { id: "menon", name: "Dr R. Menon", role: "doctor", title: "Head and neck surgeon" },
  { id: "sinha", name: "Dr Amrita Sinha", role: "doctor", title: "Treating oncologist" },
  {
    id: "vikash", name: "Vikash", role: "caregiver", title: "Caregiver — Shambhu Prasad",
    patientFocus: "P-SHAMBHU",
  },
  {
    id: "manoj", name: "Manoj Kumar", role: "caregiver", title: "Caregiver — Anita Devi",
    patientFocus: "P-ANITA",
  },
  {
    id: "priya", name: "Priya Kumari", role: "caregiver", title: "Caregiver — Anita Devi",
    patientFocus: "P-ANITA",
  },
  {
    id: "shambhu", name: "Shambhu Prasad", role: "patient", title: "Patient — simple mode",
    patientFocus: "P-SHAMBHU",
  },
  {
    id: "anita", name: "Anita Devi", role: "patient", title: "Patient — simple mode",
    patientFocus: "P-ANITA",
  },
  { id: "neha", name: "Neha", role: "admin", title: "Admin" },
  { id: "rohini", name: "Rohini", role: "admin", title: "Admin" },
];

const STORAGE_KEY = "saathi.persona";

function readStored(): Persona {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const found = ROSTER.find((p) => p.id === raw);
      if (found) return found;
    }
  } catch {
    /* private window / blocked storage — fall through to the default */
  }
  return ROSTER[0];
}

export function useIdentity(): [Persona, (id: string) => void] {
  const [persona, setPersona] = useState<Persona>(readStored);

  const choose = useCallback((id: string) => {
    const found = ROSTER.find((p) => p.id === id);
    if (!found) return;
    setPersona(found);
    try {
      window.localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* per-viewer convenience only — fine if it doesn't persist */
    }
  }, []);

  useEffect(() => {
    document.title = `Saathi — ${persona.name}`;
  }, [persona]);

  return [persona, choose];
}
