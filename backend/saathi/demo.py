"""Runnable demo: the deck's journey, end to end, on synthetic data.

    python -m saathi.demo

Runs with no credentials and no services. With ANTHROPIC_API_KEY set it also
renders the caregiver messages through the language layer.
"""

from __future__ import annotations

import argparse
from datetime import date

from .api.deps import build_state
from .domain.enums import Decision, StepKind
from .synthetic.generate import evaluate, would_be_wasted

RULE = "-" * 72


def main() -> None:
    parser = argparse.ArgumentParser(description="EKYATRA Saathi prototype demo")
    parser.add_argument("--patients", type=int, default=6, help="how many journeys to print")
    args = parser.parse_args()

    state = build_state()
    cohort = state.cohort

    print(RULE)
    print("EKYATRA Saathi — prototype run on synthetic patients")
    print(f"cohort: {len(cohort.patients)} patients · "
          f"turnaround history: {len(cohort.turnaround)} observations")
    print(RULE)

    decisions: dict[str, date | None] = {}

    for patient in cohort.patients:
        result = state.planner.plan_visit(
            patient=patient,
            steps=list(cohort.steps[patient.id]),
            target_kind=StepKind.REVIEW_CONSULT,
        )
        plan = result.get("plan")
        travel_on = plan.travel_on if plan and plan.decision is Decision.GO else None
        decisions[patient.id] = travel_on

        if cohort.patients.index(patient) >= args.patients:
            continue

        truth = cohort.ground_truth[patient.id]
        print(f"\n{patient.id}  {patient.home_district} "
              f"({patient.home_distance_km:.0f} km, {patient.language.value})")
        wasted_note = (
            "  <- would have been a wasted trip"
            if would_be_wasted(truth, truth.naive_return_date)
            else ""
        )
        print(f"  hospital said: come {truth.naive_return_date}{wasted_note}")
        if plan is None:
            print("  saathi: no plan")
            continue
        print(f"  saathi: {plan.decision.value.upper()}"
              f"{f' — travel {plan.travel_on}' if plan.travel_on else ''}")
        print(f"  why: {plan.rationale}")
        if plan.blocked_by:
            for blocked in plan.blocked_by:
                window = blocked.expected_ready
                span = (f"{window.earliest}..{window.latest} "
                        f"({int((1 - window.alpha) * 100)}% coverage, n={window.n_calibration})"
                        if window else "no calibrated window")
                print(f"       waiting on {blocked.kind.value}: {span}")
        if plan.where_to_go_first:
            print(f"  go first to: {plan.where_to_go_first}")
        if plan.evidence:
            print(f"  evidence: {len(plan.evidence)} ledger entries")
        message = result.get("message")
        if message and message.body:
            print(f"  message ({message.language.value}): {message.body}")
        elif result.get("escalation"):
            print(f"  escalated: {result['escalation']}")

    print(f"\n{RULE}")
    print("Scored against planted ground truth")
    print(RULE)
    scores = evaluate(cohort, decisions)
    print(f"  patients                       {int(scores['patients'])}")
    print(f"  wasted trips, hospital default {int(scores['baseline_wasted_trips'])} "
          f"({scores['baseline_waste_rate']:.0%})")
    print(f"  wasted trips, with Saathi      {int(scores['saathi_wasted_trips'])} "
          f"({scores['saathi_waste_rate']:.0%})")
    print(f"  wasted trips avoided           {int(scores['wasted_trips_avoided'])}")
    print(f"  non-medical cost avoided       Rs {scores['non_medical_cost_avoided_inr']:,.0f}")
    print(f"\n  evidence ledger intact         {state.ledger.verify()}")
    print(RULE)


if __name__ == "__main__":
    main()
