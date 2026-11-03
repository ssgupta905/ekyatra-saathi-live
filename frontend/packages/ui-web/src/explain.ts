/**
 * The explanation model.
 *
 * The planner returns a decision. This module turns that decision back into the
 * chain of claims that produced it, so a navigator reads the reasoning rather
 * than trusting it. Three rules hold here:
 *
 *   1. Nothing is invented. Every node is derived from a field the API actually
 *      returned — never from a guess about what the planner was probably doing.
 *   2. Every claim names its basis: a hospital record, a stated rule, or one of
 *      Saathi's own models. A claim with no basis is a bug, not a sentence.
 *   3. The rule text is quoted, not paraphrased, so the reader can check the
 *      decision against the rule instead of against their own expectations.
 */

import type {
  BlockedPrerequisite,
  CareStep,
  Decision,
  PlanResponse,
  ReadinessWindow,
} from "@saathi/api-client";
import {
  fmtDate,
  fmtWhen,
  isSatisfied,
  pct,
  queueLabel,
  statusLabel,
  stepName,
} from "./format";

export type Tone = "info" | "satisfied" | "blocking" | "unknown" | "verdict";

/** Where a claim comes from. `ledgerId` makes it clickable in the ledger. */
export interface Basis {
  kind: "record" | "rule" | "model";
  label: string;
  ledgerId?: string;
}

export interface TraceNode {
  id: string;
  /** The role this link plays in the chain — "Target", "Decision", … */
  step: string;
  tone: Tone;
  /** The assertion itself, in a navigator's language. */
  claim: string;
  /** How the assertion was reached. */
  because?: string;
  /** The governing rule, quoted. */
  rule?: string;
  basis: Basis[];
  /** Attached when this node is a bounded wait rather than a flat one. */
  window?: ReadinessWindow;
  /** Set on the verdict node, so the chain ends in the decision's own colour. */
  accent?: Decision;
}

/** The decision rules, quoted verbatim in the trace. */
export const DECISION_RULES: Record<Decision, string> = {
  go:
    "GO needs every transitive prerequisite of the target step to be satisfied. " +
    "All of them are, so the planner names a travel date.",
  wait:
    "WAIT is returned while any prerequisite is unsatisfied. Under WAIT the " +
    "planner never names a travel date — the family is told what is still " +
    "outstanding and when it is expected, nothing more.",
  uncertain:
    "UNCERTAIN is returned when a prerequisite's readiness cannot be bounded " +
    "from the records on hand. No date is promised and a navigator is asked to " +
    "call, because a guessed date costs the family a journey.",
  replan:
    "REPLAN is returned when a party outside the care steps — a ride, a stay, a " +
    "slot, a pharmacy — cannot go ahead and another way exists. No date is " +
    "promised; staff approve the new plan before the family is told.",
};

export const DECISION_PLAIN: Record<Decision, string> = {
  go: "Travel. Everything this visit depends on is ready.",
  wait: "Do not travel yet. Something this visit depends on is still outstanding.",
  uncertain: "Do not travel on this. Saathi cannot tell when this visit becomes possible.",
  replan: "Do not travel yet. Part of the plan has fallen through and the care team is changing it.",
};

const windowBasis = (w: ReadinessWindow): Basis => ({
  kind: "model",
  label: w.calibrated ? "Conformal readiness model" : "Readiness model · uncalibrated",
});

function windowSentence(w: ReadinessWindow, rawQueue: string | null): string {
  const queue = queueLabel(rawQueue);
  if (!w.calibrated) {
    return (
      `Only ${w.n_calibration} comparable case${w.n_calibration === 1 ? "" : "s"} in ` +
      `${queue ? `the ${queue} queue` : "this queue"} — too few to stand behind an ` +
      `interval, so Saathi offers none.`
    );
  }
  return (
    `Split conformal prediction over ${queue ? `the ${queue} queue's` : "this queue's"} own ` +
    `turnaround history: ${w.n_calibration} past cases, interval chosen to cover the true ` +
    `ready date at least ${pct(1 - w.alpha)} of the time.`
  );
}

function prerequisiteNode(b: BlockedPrerequisite, step: CareStep | undefined): TraceNode {
  const bounded = b.expected_ready?.calibrated ?? false;
  const basis: Basis[] = [
    { kind: "record", label: `Step record ${b.step_id}` },
  ];
  if (b.expected_ready) basis.push(windowBasis(b.expected_ready));

  return {
    id: `blocked-${b.step_id}`,
    step: "Outstanding",
    tone: bounded ? "blocking" : "unknown",
    claim: `${stepName(b.kind)} — ${statusLabel(b.status).toLowerCase()}.`,
    because: b.expected_ready
      ? windowSentence(b.expected_ready, step?.queue ?? null)
      : "No readiness history exists for this step, so Saathi cannot bound it.",
    basis,
    window: b.expected_ready ?? undefined,
  };
}

export function buildTrace(response: PlanResponse, steps: CareStep[]): TraceNode[] {
  const plan = response.plan;
  if (!plan) return [];

  const byId = new Map(steps.map((s) => [s.id, s]));
  const target = byId.get(plan.target_step_id);
  const satisfied = steps.filter(isSatisfied);
  const nodes: TraceNode[] = [];

  // 1 — what trip is even being considered.
  nodes.push({
    id: "target",
    step: "The trip in question",
    tone: "info",
    claim: target
      ? `${stepName(target.kind)}${
          target.scheduled_for
            ? `, scheduled ${fmtDate(target.scheduled_for)} (${fmtWhen(target.scheduled_for)})`
            : ", not yet scheduled"
        }.`
      : `Step ${plan.target_step_id}.`,
    because:
      "The family would travel for this step. Report steps are excluded by " +
      "design — nobody should make a journey just to collect a result.",
    basis: [{ kind: "record", label: `Step record ${plan.target_step_id}` }],
  });

  // 2 — the gate itself: a walk of the dependency graph.
  const blocked = plan.blocked_by;
  nodes.push({
    id: "gate",
    step: "Prerequisite gate",
    tone: blocked.length === 0 ? "satisfied" : "blocking",
    claim:
      blocked.length === 0
        ? "Every prerequisite of this step is satisfied."
        : `${blocked.length} prerequisite${blocked.length === 1 ? "" : "s"} ` +
          `${blocked.length === 1 ? "is" : "are"} still outstanding.`,
    because:
      `The planner walks the care-step graph, collects every transitive ` +
      `prerequisite of the target, and checks each one's status. ` +
      `${satisfied.length} of this patient's ${steps.length} recorded steps ` +
      `${satisfied.length === 1 ? "is" : "are"} complete.`,
    basis: [
      { kind: "rule", label: "Care-step dependency graph" },
      { kind: "record", label: `${steps.length} step records` },
    ],
  });

  // 3 — one node per thing in the family's way, each with its own window.
  for (const b of blocked) nodes.push(prerequisiteNode(b, byId.get(b.step_id)));

  // 4 — trips the planner was able to collapse into one journey.
  if (plan.bundled_step_ids.length > 0) {
    nodes.push({
      id: "bundle",
      step: "Bundling",
      tone: "satisfied",
      claim:
        `${plan.bundled_step_ids.length} further step${
          plan.bundled_step_ids.length === 1 ? "" : "s"
        } can happen on the same journey.`,
      because:
        "Steps that are ready and need no separate appointment are collapsed " +
        "into the target visit, so the family travels once instead of twice.",
      basis: plan.bundled_step_ids.map((id) => ({
        kind: "record" as const,
        label: `Step record ${id}`,
      })),
    });
  }

  // 5 — the verdict, with the rule it was reached under.
  nodes.push({
    id: "verdict",
    step: "Decision",
    tone: "verdict",
    accent: plan.decision,
    claim:
      plan.decision === "go" && plan.travel_on
        ? `GO — travel ${fmtDate(plan.travel_on)} (${fmtWhen(plan.travel_on)}).`
        : `${plan.decision.toUpperCase()} — no travel date given.`,
    because: plan.rationale || undefined,
    rule: DECISION_RULES[plan.decision],
    basis: [
      { kind: "rule", label: "Visit planner" },
      ...plan.evidence.map((e) => ({
        kind: "record" as const,
        label: e.source_record_id,
        ledgerId: e.ledger_id,
      })),
    ],
  });

  return nodes;
}

/** The signals behind an alert — shown as signals, never rolled into a score. */
export const ALERT_LABELS: Record<string, string> = {
  disengagement: "Going quiet",
  clinical_question: "Clinical question",
  uncertain_plan: "Plan uncertain",
};

export const ALERT_MEANING: Record<string, string> = {
  disengagement:
    "This caregiver's reply latency shifted away from their own baseline — a " +
    "change point in their series, not a comparison with anybody else.",
  clinical_question:
    "The family asked something clinical. Saathi answered nothing and routed it " +
    "here; a person has to call.",
  uncertain_plan:
    "The planner could not bound a prerequisite, so no date was promised and " +
    "this was raised for a call.",
};

export const ALERT_TONE: Record<string, "wait" | "critical" | "uncertain"> = {
  disengagement: "wait",
  clinical_question: "critical",
  uncertain_plan: "uncertain",
};
