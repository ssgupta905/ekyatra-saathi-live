import { useCallback, useEffect, useState } from "react";
import { family, type BudgetAsk, type BudgetOption, type BudgetTopic, type CostTier } from "@saathi/api-client";
import type { Lang, Strings } from "@saathi/i18n";
import { Shield } from "@saathi/ui-web";

/**
 * What the family can manage.
 *
 * The one screen here that asks rather than tells. Everything else in this app
 * reports what the hospital and the planner have worked out; this admits the
 * thing neither of them can know — whether this household can pay for the ride
 * that was picked for them.
 *
 * Three deliberate absences.
 *
 * **No prices.** Not because they would be hard to fetch, but because the
 * backend will not report a fare it was not given, and a number invented for a
 * screen would be the same mistake wearing a different hat. The family is
 * choosing between *kinds of thing* — a patient-quota berth, a state bus, an
 * app cab — which is the choice they actually make.
 *
 * **Nothing pre-selected.** The row the system would have picked is marked, and
 * it is not ticked. A default that was merely not changed is not an answer to
 * "what can you manage", and treating it as one turns the question into
 * decoration.
 *
 * **No confirmation that anything happened.** Tapping records a proposal and
 * says a person will confirm it, because that is the truth. A screen that said
 * "booked" would be lying by one step.
 */

const TIER_WORD: Record<CostTier, keyof Strings> = {
  subsidised: "tierSubsidised",
  modest: "tierModest",
  standard: "tierStandard",
};

const TOPIC_WORD: Record<BudgetTopic, keyof Strings> = {
  travel: "budgetTravel",
  stay: "budgetStay",
  medicine: "budgetMedicine",
};

function Option({
  option,
  s,
  disabled,
  onPick,
}: {
  option: BudgetOption;
  s: Strings;
  disabled: boolean;
  onPick: () => void;
}) {
  return (
    <button type="button" className="fx-budget-option" disabled={disabled} onClick={onPick}>
      <span className="fx-budget-name">{option.name}</span>
      <span className={`fx-tier fx-tier-${option.cost_tier}`}>{s[TIER_WORD[option.cost_tier]]}</span>
      {/* The organisation's own words from the directory. Not a sales line. */}
      {option.what.length > 0 && <span className="fx-budget-what">{option.what.join(" · ")}</span>}
      {option.suggested && <span className="fx-budget-suggested">{s.budgetSuggested}</span>}
    </button>
  );
}

export function Budget({
  patientId,
  lang,
  s,
  onAnswered,
}: {
  patientId: string;
  lang: Lang;
  s: Strings;
  onAnswered: () => void;
}) {
  const [asks, setAsks] = useState<BudgetAsk[] | null>(null);
  const [sent, setSent] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    family
      .budget(patientId)
      .then((body) => setAsks(body.asks))
      // A question that cannot be loaded is simply not asked. This screen is
      // never the reason a family cannot see their plan.
      .catch(() => setAsks([]));
  }, [patientId]);

  useEffect(load, [load]);

  const answer = async (
    topic: BudgetTopic,
    reply: { organisation_id?: string; cannot_manage?: boolean },
  ) => {
    setBusy(topic);
    try {
      await family.answerBudget(patientId, topic, reply);
      setSent((was) => new Set(was).add(topic));
      onAnswered();
    } catch {
      /* The family taps again. Nothing was recorded, so nothing is half-done. */
    } finally {
      setBusy(null);
    }
  };

  const open = (asks ?? []).filter((ask) => !ask.answered && !sent.has(ask.topic));
  if (open.length === 0) return null;

  return (
    <section className="fx-budget" lang={lang}>
      <h2>{s.budgetTitle}</h2>
      <p className="fx-budget-why">
        <Shield size={12} />
        {s.budgetWhy}
      </p>

      {open.map((ask) => (
        <div key={ask.topic} className="fx-budget-topic">
          <h3>{s[TOPIC_WORD[ask.topic]]}</h3>
          <p className="fx-budget-choose">{s.budgetChoose}</p>
          <div className="fx-budget-options">
            {ask.options.map((option) => (
              <Option
                key={option.organisation_id}
                option={option}
                s={s}
                disabled={busy !== null}
                onPick={() => answer(ask.topic, { organisation_id: option.organisation_id })}
              />
            ))}
          </div>
          {/* Last, and always there. The most important answer, and the one a
              list of things to buy has no room for. */}
          <button
            type="button"
            className="fx-budget-cannot"
            disabled={busy !== null}
            onClick={() => answer(ask.topic, { cannot_manage: true })}
          >
            {s.budgetCannotManage}
          </button>
        </div>
      ))}
    </section>
  );
}

export function BudgetThanks({ s, show }: { s: Strings; show: boolean }) {
  if (!show) return null;
  return <p className="fx-budget-sent">{s.budgetSent}</p>;
}
