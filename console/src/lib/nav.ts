/**
 * What each role can open, in the order they'd open it.
 *
 * Every page answers one question. A role sees only its own pages, so a desk
 * clerk never wades past a navigator's cohort metrics to find the button that
 * reports a machine down.
 */

import type { Role } from "./api";

export type PageId =
  | "today"
  | "families"
  | "decisions"
  | "activity"
  | "stories"
  | "report"
  | "records"
  | "rules"
  | "audit"
  | "plan";

export type NavIcon = "grid" | "people" | "check" | "wave" | "play" | "bell" | "inbox" | "shield" | "doc" | "pin";

export interface NavItem {
  id: PageId;
  label: string;
  /** The one question this page answers — shown as the page subtitle. */
  question: string;
  icon: NavIcon;
}

export const NAV: Record<Role, NavItem[]> = {
  navigator: [
    { id: "today", label: "Today", question: "What needs me right now?", icon: "grid" },
    { id: "families", label: "Families", question: "Should this family travel, and why?", icon: "people" },
    { id: "decisions", label: "Decisions", question: "Which disrupted families are waiting on a person?", icon: "check" },
    { id: "activity", label: "Activity", question: "What has the system just done?", icon: "wave" },
    { id: "stories", label: "Stories", question: "Walk a disruption through, one step at a time.", icon: "play" },
  ],
  desk: [
    { id: "report", label: "Report an issue", question: "Is something you run unavailable?", icon: "bell" },
    { id: "records", label: "Records", question: "Which finished records need your confirmation?", icon: "inbox" },
  ],
  doctor: [
    { id: "decisions", label: "Decisions", question: "Which date changes touch treatment?", icon: "check" },
    { id: "families", label: "Families", question: "The context behind each decision.", icon: "people" },
  ],
  admin: [
    { id: "rules", label: "Rules", question: "What readiness rules is the system running with?", icon: "shield" },
    { id: "audit", label: "Audit log", question: "Every action, and who or what it came from.", icon: "doc" },
  ],
  caregiver: [{ id: "plan", label: "Your plan", question: "Should we travel?", icon: "pin" }],
  patient: [{ id: "plan", label: "Your plan", question: "Should we travel?", icon: "pin" }],
};

export function firstPage(role: Role): PageId {
  return NAV[role][0].id;
}

export function navItem(role: Role, page: PageId): NavItem {
  return NAV[role].find((item) => item.id === page) ?? NAV[role][0];
}
