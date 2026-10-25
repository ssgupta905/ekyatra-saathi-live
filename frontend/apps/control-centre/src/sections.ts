import type { Role } from "@saathi/api-client";

/**
 * Every screen of the control centre, and who it is for.
 *
 * The list decides what the left-hand navigation offers each role; it is a
 * convenience, not the boundary. The server checks the role on every action that
 * matters, whatever this list says.
 */
export interface Section {
  id: string;
  label: string;
  hint: string;
  roles: Role[];
  /** Only meaningful in the simulated world (the clock, the scripted stories). */
  demoOnly?: boolean;
}

const STAFF: Role[] = ["navigator", "desk", "doctor", "admin"];

export const SECTIONS: Section[] = [
  { id: "families", label: "Families", hint: "One family at a time: the answer, why, and everything behind it", roles: STAFF },
  { id: "boards", label: "Plan boards", hint: "Every family's pathway at once: what is waiting on what", roles: STAFF },
  { id: "approvals", label: "Disruptions & approvals", hint: "Outages in force and the re-plans waiting on a person", roles: ["navigator", "doctor", "admin"] },
  { id: "desk", label: "Desk", hint: "Report what went wrong; confirm and release reports; enter records", roles: ["desk", "admin"] },
  { id: "cohort", label: "Cohort", hint: "Who needs a person, and what the whole cohort has been spared", roles: ["navigator", "doctor", "admin"] },
  { id: "story", label: "Story view", hint: "The brief's two stories, beat by beat, with what each cost", roles: STAFF, demoOnly: true },
  { id: "operator", label: "Operator", hint: "The simulated clock and the family's words", roles: ["navigator", "admin"], demoOnly: true },
  { id: "config", label: "Configuration", hint: "Readiness rules, languages, channels, integrations", roles: ["admin"] },
  { id: "audit", label: "Audit log", hint: "Every fact the system has asserted, hash-chained", roles: ["admin"] },
];

/** Where each role lands first: the screen their day starts on. */
export const HOME: Record<Role, string> = {
  navigator: "families",
  desk: "desk",
  doctor: "approvals",
  admin: "config",
  caregiver: "families",
  patient: "families",
};

export function sectionsFor(role: Role, demo: boolean): Section[] {
  return SECTIONS.filter((s) => s.roles.includes(role) && (demo || !s.demoOnly));
}
