/**
 * Ranked options for one disrupted patient, and the single approval action.
 *
 * Shared by the navigator, doctor and desk screens so there is exactly one
 * place that renders a `PlanOption` and exactly one place that calls
 * `disruptions.approve` — the role gate itself lives on the server, this
 * component only decides which name/role the approval is submitted under.
 */

import { useEffect, useState } from "react";
import { disruptions, type OptionSet, type Role } from "@saathi/api-client";
import { Badge, Card } from "../primitives";

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
    <Card title={`Options for ${patientId}`} hint="Order is the only ranking — no score">
      {error && <p className="hint" style={{ color: "var(--status-stop)" }}>{error}</p>}
      <div className="options-list">
        {optionSet.options.map((option, index) => (
          <div key={index} className="option-card">
            <Badge
              tone={
                option.decision === "go" ? "go" : option.decision === "wait" || option.decision === "replan" ? "wait" : "uncertain"
              }
            >
              {option.decision.toUpperCase()}
            </Badge>
            <span>{option.nights_added >= 0 ? "+" : ""}{option.nights_added} nights</span>
            <span>{option.extra_trips >= 0 ? "+" : ""}{option.extra_trips} trips</span>
            {option.dose_delay_days > 0 && <span>{option.dose_delay_days}d dose delay</span>}
            {/* Not a cost like the others: a reserved berth cannot be had at
                this notice, so this option may not be a plan at all. Said in
                words, because a navigator must not read it as "+1 something". */}
            {option.short_notice_journeys > 0 && (
              <span className="opt-unbookable">
                needs a seat booked at short notice
              </span>
            )}
            <button type="button" disabled={busy} onClick={() => approve(index)}>
              Approve as {approverName}
            </button>
          </div>
        ))}
      </div>
    </Card>
  );
}
