/**
 * Ranked options for one disrupted patient, and the single approval action.
 *
 * Shared by the navigator, doctor and desk screens so there is exactly one
 * place that renders a `PlanOption` and exactly one place that calls
 * `disruptions.approve` — the role gate itself lives on the server, this
 * component only decides which name/role the approval is submitted under.
 */

import { useEffect, useState } from "react";
import { disruptions, type OptionSet, type PlanOption, type Role } from "../lib/api";
import { fmtDate } from "../lib/format";
import { Badge, Card } from "../ui/primitives";

export function OptionsApprovalCard({
  disruptionId,
  patientId,
  approverRole,
  approverName,
  onApproved,
}: {
  disruptionId: string;
  patientId: string;
  approverRole: Role;
  approverName: string;
  onApproved: () => void;
}) {
  const [optionSet, setOptionSet] = useState<OptionSet | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    disruptions
      .options(disruptionId, patientId)
      .then((set) => !cancelled && setOptionSet(set))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [disruptionId, patientId]);

  if (!optionSet || optionSet.options.length === 0) return null;

  const approve = async (index: number) => {
    setBusy(true);
    setError(null);
    try {
      await disruptions.approve(disruptionId, {
        patient_id: patientId,
        option_index: index,
        approved_by_role: approverRole,
        approved_by: approverName,
      });
      onApproved();
    } catch (e) {
      setError(
        e instanceof Error && e.message.includes("403")
          ? "This option touches treatment or dose timing — only a doctor can approve it."
          : "Approval failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={`Options for ${patientId}`} hint="Listed fewest journeys first — no score">
      {error && <p className="hint" style={{ color: "var(--critical)" }}>{error}</p>}
      <div className="options-list">
        {optionSet.options.map((option, index) => (
          <div key={index} className="option-card">
            <div className="option-main">
              <div className="option-title">
                <span className="option-letter">{String.fromCharCode(65 + index)}</span>
                {optionLabel(option)}
              </div>
              <div className="option-tradeoffs">
                <span>{nightsText(option.nights_added)}</span>
                <span>{tripsText(option.extra_trips)}</span>
                {option.dose_delay_days > 0 && <span>dose {option.dose_delay_days} days later</span>}
                <Badge
                  tone={option.decision === "go" ? "go" : option.decision === "wait" ? "wait" : "uncertain"}
                >
                  {option.decision === "go"
                    ? `travel ${option.travel_on ? fmtDate(option.travel_on) : ""}`.trim()
                    : option.decision === "wait"
                      ? "then wait"
                      : "date still open"}
                </Badge>
              </div>
            </div>
            <button type="button" className="btn" disabled={busy} onClick={() => approve(index)}>
              Choose {String.fromCharCode(65 + index)}
            </button>
          </div>
        ))}
      </div>
    </Card>
  );
}

/** What an option *is*, in the words of the brief's option tables. */
function optionLabel(option: PlanOption): string {
  if (option.extra_trips < 0) return "Fold it into a visit that's already booked";
  if (option.extra_trips > 0) return "Go home now and come back for it";
  return "Stay — it moves to the first free day";
}

const nightsText = (n: number) =>
  n === 0 ? "no extra nights" : n > 0 ? `${n} more night${n === 1 ? "" : "s"} away` : `${-n} fewer night${n === -1 ? "" : "s"} away`;

const tripsText = (n: number) =>
  n === 0 ? "no extra journeys" : n > 0 ? `${n} extra journey${n === 1 ? "" : "s"}` : `${-n} journey${n === -1 ? "" : "s"} saved`;
