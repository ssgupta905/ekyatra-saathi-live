import { useCallback, useEffect, useState } from "react";
import {
  consent,
  ApiError,
  type ConsentCapacity,
  type ConsentPurpose,
  type ConsentSnapshot,
} from "@saathi/api-client";
import { Notice } from "@saathi/ui-web";
import { Pill, SkeletonRows } from "../ui/kit";

const PURPOSE: Record<ConsentPurpose, string> = {
  care_coordination: "Coordinating visits",
  record_movement: "Moving records to a new centre",
  research: "Research (optional)",
};

/**
 * What the family has agreed to share, with whom, and for how long.
 *
 * Saathi asks; the family answers in their own words and can withdraw at any
 * time. Each purpose is asked separately and none is a condition of care. This
 * screen moves no clinical content: it says who may be told what exists.
 */
export function ConsentLayer({
  patientId,
  revision,
  canAsk,
  actor,
}: {
  patientId: string;
  revision: number;
  canAsk: boolean;
  actor: string;
}) {
  const [snap, setSnap] = useState<ConsentSnapshot | null>(null);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ask, setAsk] = useState({ purpose: "care_coordination" as ConsentPurpose, who: "", what: "visit status" });
  const [capacity, setCapacity] = useState<ConsentCapacity>("self");
  // The person who actually said yes: never inferred from who is signed in.
  const [answeredBy, setAnsweredBy] = useState("");

  const load = useCallback(() => {
    consent
      .snapshot(patientId)
      .then((s) => {
        setSnap(s);
        setUnavailable(null);
      })
      .catch((e: unknown) =>
        setUnavailable(
          e instanceof ApiError && e.status === 409
            ? "This family has no ABHA number on record, so there is nothing to consent about yet."
            : String(e),
        ),
      );
  }, [patientId]);

  useEffect(load, [load, revision]);

  const run = async (work: () => Promise<unknown>) => {
    setError(null);
    try {
      await work();
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  if (unavailable) return <Notice tone="calm">{unavailable}</Notice>;
  if (!snap) return <SkeletonRows rows={2} />;

  return (
    <div className="consent">
      <h3>Agreed</h3>
      {snap.grants.length === 0 ? (
        <Notice tone="calm">Nothing has been agreed yet, so nobody outside Saathi may be told anything.</Notice>
      ) : (
        <table className="cc-table">
          <tbody>
            {snap.grants.map((g) => (
              <tr key={g.id}>
                <td>{PURPOSE[g.purpose]}</td>
                <td>{g.requester}</td>
                <td>
                  agreed by {g.granted_by} ({g.capacity}) · until {g.expires_at.slice(0, 10)}
                </td>
                <td>{g.active ? <Pill tone="go">In force</Pill> : <Pill tone="neutral">{g.revoked_at ? "Withdrawn" : "Expired"}</Pill>}</td>
                <td>
                  {g.active && (
                    <button
                      type="button"
                      className="btn"
                      onClick={() => run(() => consent.revoke(patientId, g.id, { by: actor, reason: "withdrawn by the family" }))}
                    >
                      Withdraw
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 style={{ marginTop: 16 }}>Waiting for an answer</h3>
      {snap.pending.length === 0 ? (
        <p className="mono">Nothing is waiting on the family.</p>
      ) : (
        <table className="cc-table">
          <tbody>
            {snap.pending.map((r) => (
              <tr key={r.id}>
                <td>{PURPOSE[r.purpose]}</td>
                <td>{r.requester}</td>
                <td>asks for: {r.categories.join(", ")}</td>
                <td>
                  <input
                    value={answeredBy}
                    placeholder="Name of who said yes"
                    aria-label="Name of who said yes"
                    onChange={(e) => setAnsweredBy(e.target.value)}
                  />
                  <select value={capacity} onChange={(e) => setCapacity(e.target.value as ConsentCapacity)} aria-label="Who is answering">
                    <option value="self">the patient</option>
                    <option value="nominee">a named nominee</option>
                    <option value="guardian">a guardian</option>
                  </select>
                </td>
                <td>
                  <button
                    type="button"
                    className="btn primary"
                    disabled={!answeredBy.trim()}
                    onClick={() => run(() => consent.grant(patientId, r.id, { granted_by: answeredBy.trim(), capacity, channel: "whatsapp", days: 30 }))}
                  >
                    Record their yes
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {canAsk && (
        <div style={{ marginTop: 14 }}>
          <div className="iss-fields">
            <label>
              Purpose
              <select value={ask.purpose} onChange={(e) => setAsk({ ...ask, purpose: e.target.value as ConsentPurpose })}>
                {Object.entries(PURPOSE).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Who is asking
              <input value={ask.who} placeholder="e.g. day-care pharmacy" onChange={(e) => setAsk({ ...ask, who: e.target.value })} />
            </label>
            <label>
              What they would be told
              <input value={ask.what} onChange={(e) => setAsk({ ...ask, what: e.target.value })} />
            </label>
          </div>
          <div className="iss-actions" style={{ marginTop: 10 }}>
            <button
              type="button"
              className="btn primary"
              disabled={!ask.who.trim() || !ask.what.trim()}
              onClick={() =>
                run(async () => {
                  await consent.ask(patientId, {
                    purpose: ask.purpose,
                    requester_id: ask.who.trim().toLowerCase().replace(/\s+/g, "-"),
                    requester_name: ask.who.trim(),
                    categories: [ask.what.trim()],
                  });
                  setAsk({ ...ask, who: "" });
                })
              }
            >
              Ask the family
            </button>
          </div>
        </div>
      )}
      {error && <Notice tone="warn">{error}</Notice>}
    </div>
  );
}
