import type { Role } from "@saathi/api-client";

/**
 * Every screen of the control centre, which role's work it is, and where it sits.
 *
 * The navigation shows a role only its own work, in the order that work happens:
 * a navigator's day starts at Today and goes to a family; a desk's starts with
 * what went wrong. It is a convenience, not the boundary: the server checks the
 * role on every action that matters, whatever this list says.
 */
export type Icon =
  | "home" | "users" | "approve" | "file" | "graph" | "alert" | "inbox" | "userplus"
  | "chart" | "building" | "sliders" | "ledger" | "film" | "dial" | "network";

export interface Section {
  id: string;
  label: string;
  hint: string;
  icon: Icon;
  roles: Role[];
  group: "work" | "records" | "hospital" | "demo";
  /** Only meaningful in the simulated world (the clock, the scripted stories). */
  demoOnly?: boolean;
  /** Only meaningful on real records (entering them; the demo's are generated). */
  realOnly?: boolean;
}

const STAFF: Role[] = ["navigator", "desk", "doctor", "admin"];

export const GROUPS: Record<Section["group"], string> = {
  work: "Work",
  records: "Records",
  hospital: "Hospital",
  demo: "Demo",
};

export const SECTIONS: Section[] = [
  { id: "today", label: "Today", hint: "What needs you now", icon: "home", roles: STAFF, group: "work" },
  { id: "families", label: "Families", hint: "One family at a time: the answer, then the detail you ask for", icon: "users", roles: STAFF, group: "work" },
  { id: "network", label: "Network board", hint: "Every journey against every party: who is holding what up", icon: "network", roles: STAFF, group: "work", realOnly: true },
  { id: "approvals", label: "Approvals", hint: "Re-plans waiting on a person, and the outages behind them", icon: "approve", roles: ["navigator", "doctor", "admin"], group: "work" },
  { id: "issues", label: "Report an issue", hint: "Say what went wrong, the way you would write it in the log", icon: "alert", roles: ["desk", "admin"], group: "work" },
  { id: "releases", label: "Releases", hint: "Reports to confirm or mark released", icon: "inbox", roles: ["desk", "admin"], group: "work" },
  { id: "reports", label: "Reports", hint: "Every report against the window it should land in", icon: "file", roles: STAFF, group: "records" },
  { id: "boards", label: "Plan boards", hint: "Every family's pathway at once", icon: "graph", roles: ["navigator", "doctor", "admin"], group: "records" },
  { id: "onboarding", label: "Onboarding", hint: "Take a family on: what they tell us, then what the hospital adds", icon: "userplus", roles: ["desk", "navigator", "doctor", "admin"], group: "records", realOnly: true },
  { id: "records", label: "Enter records", hint: "Register a family, add steps, import a file", icon: "userplus", roles: ["desk", "navigator", "admin"], group: "records", realOnly: true },
  { id: "cohort", label: "Cohort", hint: "Who needs a person, and what the cohort has been spared", icon: "chart", roles: ["navigator", "doctor", "admin"], group: "records" },
  { id: "directory", label: "Directory", hint: "Every lab, pharmacy, distributor, cab, hotel and insurer a journey runs through", icon: "network", roles: STAFF, group: "hospital" },
  { id: "registries", label: "Registries", hint: "Hospitals, centres, doctors, resources, staff accounts", icon: "building", roles: STAFF, group: "hospital" },
  { id: "config", label: "Configuration", hint: "Each hospital's rules and what is switched on", icon: "sliders", roles: ["admin"], group: "hospital" },
  { id: "audit", label: "Audit log", hint: "Every fact asserted, hash-chained", icon: "ledger", roles: ["admin"], group: "hospital" },
  { id: "story", label: "Story view", hint: "The brief's two stories, beat by beat", icon: "film", roles: STAFF, group: "demo", demoOnly: true },
  { id: "operator", label: "Operator", hint: "The simulated clock and the family's words", icon: "dial", roles: ["navigator", "admin"], group: "demo", demoOnly: true },
];

/** Where each role's day starts. */
export const HOME: Record<Role, string> = {
  navigator: "today",
  desk: "today",
  doctor: "today",
  admin: "today",
  caregiver: "today",
  patient: "today",
  //: A partner never reaches this app — `AuthGate` turns the role away — but
  //: the map is exhaustive so a new role cannot be forgotten here silently.
  partner: "today",
};

export function sectionsFor(role: Role, demo: boolean): Section[] {
  return SECTIONS.filter(
    (s) => s.roles.includes(role) && (demo ? !s.realOnly : !s.demoOnly),
  );
}
