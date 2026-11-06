import { useState } from "react";
import { partner, type PartnerAnswer, type PartnerJob } from "@saathi/api-client";

/**
 * One job, and the three answers a vendor actually gives.
 *
 * "Cannot" asks for a reason before it will send, because a navigator is about
 * to book somebody else and needs to know what went wrong — a refusal with no
 * reason costs them a phone call to find out.
 *
 * A date appears only when the plan promises one. A contact appears only when
 * the family has agreed to share it, and when they have not the card says so,
 * because a blank space looks like a bug and reads as one.
 */

const NEED_WORDS: Record<string, string> = {
  transport: "A ride",
  stay: "A room",
  medicine: "Pharmacy items",
  insurance: "Scheme approval",
};

const day = (iso: string | null) =>
  iso
    ? new Intl.DateTimeFormat("en-IN", {
        weekday: "long",
        day: "numeric",
        month: "long",
      }).format(new Date(`${iso}T00:00:00`))
    : null;

export function Job({
  job,
  onAnswered,
  settled = false,
}: {
  job: PartnerJob;
  onAnswered: () => void;
  settled?: boolean;
}) {
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<PartnerAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = async (answer: PartnerAnswer) => {
    if (answer === "cannot" && !reason.trim()) {
      setAsking(true);
      return;
    }
    setBusy(answer);
    setError(null);
    try {
      await partner.answer(job.item_id, answer, reason.trim());
      setAsking(false);
      setReason("");
      onAnswered();
    } catch (e) {
      setError(e instanceof Error ? e.message : "that did not send");
    } finally {
      setBusy(null);
    }
  };

  const when = day(job.family.on);

  return (
    <article className={settled ? "pt-job settled" : "pt-job"}>
      <h3 className="pt-need">{NEED_WORDS[job.need] ?? job.need}</h3>

      <dl className="pt-facts">
        <div>
          <dt>For</dt>
          <dd>{job.family.first_name}</dd>
        </div>
        <div>
          <dt>From</dt>
          <dd>{job.family.district}</dd>
        </div>
        <div>
          <dt>Day</dt>
          <dd>{when ?? <span className="pt-none">not fixed yet</span>}</dd>
        </div>
        <div>
          <dt>Contact</dt>
          <dd>
            {job.family.contact ?? (
              <span className="pt-none">
                {job.family.contact_withheld
                  ? "the family has not agreed to share it; the navigator will call"
                  : "—"}
              </span>
            )}
          </dd>
        </div>
      </dl>

      {job.detail && <p className="pt-detail">{job.detail}</p>}
      {error && <p className="pt-error">{error}</p>}

      {!settled && (
        <>
          {asking && (
            <label className="pt-reason">
              What went wrong?
              <input
                value={reason}
                autoFocus
                placeholder="no car in that district tonight"
                onChange={(event) => setReason(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && send("cannot")}
              />
            </label>
          )}

          <div className="pt-actions">
            <button
              type="button"
              className="pt-btn primary"
              disabled={busy !== null}
              onClick={() => send("ready")}
            >
              {busy === "ready" ? "sending…" : "It is arranged"}
            </button>
            <button
              type="button"
              className="pt-btn"
              disabled={busy !== null}
              onClick={() => send("accepted")}
            >
              We have it
            </button>
            <button
              type="button"
              className="pt-btn danger"
              disabled={busy !== null}
              onClick={() => send("cannot")}
            >
              {busy === "cannot" ? "sending…" : "We cannot"}
            </button>
          </div>
        </>
      )}
    </article>
  );
}
