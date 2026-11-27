/**
 * Ranked options for one disrupted patient, and the decisions a person makes.
 *
 * Shared by the navigator, doctor and desk screens so there is exactly one
 * place that renders a `PlanOption` and exactly one place that calls
 * `disruptions.approve` — the role gate itself lives on the server, this
 * component only decides which name/role the decision is submitted under.
 *
 * Two verbs, because a desk needs both. **Approve** picks an option and books
 * it back into the hospital system. **Reject** says none of these will do and
 * the desk is taking the family on by hand — a real thing that happens, and
 * without it the only way to clear the queue is to approve something nobody
 * believes in.
 *
 * What an option costs the family is shown in nights, trips and dose delay,
 * never in rupees. The backend will not report a fare it was not given, and a
 * number invented here would be the one thing on the screen that nobody could
 * trace back to a source.
 */

import { useEffect, useState } from "react";
import { ApiError, disruptions, type OptionSet, type Role } from "@saathi/api-client";
import { Badge, Card } from "../primitives";

/** What went wrong, in words a desk can act on rather than a status code. */
function readFailure(error: unknown, verb: "approve" | "reject"): string {
  if (error instanceof ApiError) {
    if (error.status === 403) {
      return "This option touches treatment or dose timing — only a doctor can approve it.";
    }
    if (error.status === 502) {
      // The write-back was refused, so nothing was approved and nobody was
      // told. Say that plainly: the desk's next move is the hospital system,
      // not this screen.
      return `The hospital system refused this slot, so nothing was changed and the family has not been told. ${
        typeof error.detail === "string" ? error.detail : ""
      }`;
    }
    if (error.status === 404) return "These options are no longer waiting — someone else acted.";
  }
  return verb === "approve" ? "Approval failed." : "Could not record that.";
}

export function OptionsApprovalCard({
  disruptionId,
  patientId,
  approverRole,
  approverName,
  onApproved,
  /**
   * Whether the hospital caused this change. When it did, the desk is offered
   * the welfare fund, because a family should not pay for the hospital's own
   * rescheduling. Whether a given hospital *has* such a fund is a pilot
   * question, so this is off unless the caller says otherwise.
   */
  hospitalCaused = false,
  hospitalCause = null,
  welfareEstimate = null,
}: {
  disruptionId: string;
  patientId: string;
  approverRole: Role;
  approverName: string;
  onApproved: () => void;
  hospitalCaused?: boolean;
  /** Why the hospital is the cause, in the desk's words. */
  hospitalCause?: string | null;
  /** The published-rate estimate of what covering it would cost. */
  welfareEstimate?: string | null;
}) {
  const [optionSet, setOptionSet] = useState<OptionSet | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [coverCost, setCoverCost] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

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
        cover_from_welfare_fund: hospitalCaused && coverCost,
      });
      onApproved();
    } catch (e) {
      setError(readFailure(e, "approve"));
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    setBusy(true);
    setError(null);
    try {
      await disruptions.reject(disruptionId, {
        patient_id: patientId,
        rejected_by_role: approverRole,
        rejected_by: approverName,
        reason: reason.trim(),
      });
      setRejecting(false);
      setReason("");
      onApproved();
    } catch (e) {
      setError(readFailure(e, "reject"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={`Options for ${patientId}`} hint="Order is the only ranking — no score">
      {error && (
        <p className="hint" style={{ color: "var(--status-stop)" }} role="alert">
          {error}
        </p>
      )}

      {hospitalCaused && (
        <label className="opt-welfare">
          <input
            type="checkbox"
            checked={coverCost}
            onChange={(e) => setCoverCost(e.target.checked)}
            disabled={busy}
          />
          <span>
            Cover the extra cost from the patient welfare fund
            <small>
              {hospitalCause
                ? `The hospital caused this change (${hospitalCause}), so the family should not pay for it.`
                : "The hospital caused this change, so the family should not pay for it."}
              {welfareEstimate && ` Likely cost to the fund: ${welfareEstimate}, from published rates.`}
            </small>
          </span>
        </label>
      )}

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

      {rejecting ? (
        <div className="opt-reject">
          <label htmlFor={`reject-${patientId}`}>
            Why none of these will do — so the next person reading this knows
          </label>
          <input
            id={`reject-${patientId}`}
            type="text"
            value={reason}
            disabled={busy}
            placeholder="Already at the station; calling the family now"
            onChange={(e) => setReason(e.target.value)}
          />
          <p className="hint">
            The family is not messaged and nothing is booked. They go back on the list of
            people who need a person.
          </p>
          <div className="opt-reject-actions">
            <button type="button" className="btn" disabled={busy} onClick={() => setRejecting(false)}>
              Keep the options
            </button>
            <button type="button" className="btn danger" disabled={busy} onClick={reject}>
              Turn all down and take it on
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="btn subtle"
          disabled={busy}
          onClick={() => setRejecting(true)}
        >
          None of these — I'll take this one on
        </button>
      )}
    </Card>
  );
}
