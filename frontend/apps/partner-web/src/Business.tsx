import { useCallback, useEffect, useState } from "react";
import {
  partner,
  type RateIn,
  type VendorEarnings,
  type VendorSelf,
} from "@saathi/api-client";

/**
 * The vendor's own business: what it charges, how it stands, what it is owed.
 *
 * Three things, in the order a vendor cares about them.
 *
 * *Rates* can be changed here, wholesale. Line-by-line editing was the obvious
 * design and the wrong one: a half-updated price list is worse than an old one,
 * because somebody quotes from the line that did not change.
 *
 * *Standing* is counted, never scored. There is no rating on this screen and no
 * field for one in the API behind it. A vendor with four refusals out of nine
 * can see exactly that and argue with it; a vendor with three and a half stars
 * can only resent it.
 *
 * *Money* states what the family pays beside what the vendor keeps, with the
 * commission between them — because the single thing a vendor most needs to
 * believe, and most reasonably doubts, is that our cut is not being quietly
 * added to the family's price. The two figures are shown together so the claim
 * is checkable rather than reassuring.
 */
export function Business() {
  const [me, setMe] = useState<VendorSelf | null>(null);
  const [books, setBooks] = useState<VendorEarnings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rates, setRates] = useState<RateIn[] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    partner
      .me()
      .then(setMe)
      .catch((e: Error) => setError(e.message));
    partner
      .earnings()
      .then(setBooks)
      .catch(() => undefined);
  }, []);

  useEffect(load, [load]);

  if (error) return <p className="pt-error">{error}</p>;
  if (!me) return <p className="pt-empty">…</p>;

  const editing = rates ?? me.rate_card;

  const save = async () => {
    setBusy(true);
    try {
      const usable = editing.filter((r) => r.service.trim() && Number(r.amount_inr) > 0);
      await partner.setRates(
        usable.map((r) => ({
          service: r.service.trim(),
          unit: r.unit?.trim() || "per trip",
          amount_inr: Number(r.amount_inr),
          note: r.note?.trim() || "",
        })),
      );
      setRates(null);
      load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h2 className="pt-h2">You</h2>
      <dl className="pt-facts">
        <div>
          <dt>Name</dt>
          <dd>{me.name}</dd>
        </div>
        <div>
          <dt>Covers</dt>
          <dd>{me.districts.length ? me.districts.join(", ") : <span className="pt-none">anywhere</span>}</dd>
        </div>
        <div>
          <dt>Offers</dt>
          <dd>{me.services.length ? me.services.join(", ") : <span className="pt-none">not said</span>}</dd>
        </div>
        <div>
          <dt>In network</dt>
          <dd>
            {me.active
              ? me.approved_on
                ? `yes, since ${me.approved_on}`
                : "yes"
              : "not yet — your application is with the hospital"}
          </dd>
        </div>
      </dl>

      <h2 className="pt-h2">Your rates</h2>
      <p className="pt-detail">
        Your prices, in your words. We never change them and never show a family
        a figure as yours that you did not give us.
      </p>
      {editing.length === 0 && <p className="pt-none">You have not given us any rates yet.</p>}
      {editing.map((rate, index) => (
        <div className="pt-rate" key={index}>
          <label>
            Service
            <input
              value={rate.service}
              onChange={(e) =>
                setRates(editing.map((r, i) => (i === index ? { ...r, service: e.target.value } : r)))
              }
            />
          </label>
          <label>
            Charged by
            <input
              value={rate.unit ?? ""}
              onChange={(e) =>
                setRates(editing.map((r, i) => (i === index ? { ...r, unit: e.target.value } : r)))
              }
            />
          </label>
          <label>
            Rupees
            <input
              inputMode="numeric"
              value={rate.amount_inr || ""}
              onChange={(e) =>
                setRates(
                  editing.map((r, i) =>
                    i === index ? { ...r, amount_inr: Number(e.target.value.replace(/\D/g, "")) } : r,
                  ),
                )
              }
            />
          </label>
          <label>
            Anything that changes the price
            <input
              value={rate.note ?? ""}
              onChange={(e) =>
                setRates(editing.map((r, i) => (i === index ? { ...r, note: e.target.value } : r)))
              }
            />
          </label>
        </div>
      ))}
      <div className="pt-actions">
        <button
          type="button"
          className="pt-btn"
          onClick={() => setRates([...editing, { service: "", unit: "per trip", amount_inr: 0, note: "" }])}
        >
          Add a rate
        </button>
        {rates !== null && (
          <>
            <button type="button" className="pt-btn primary" disabled={busy} onClick={save}>
              {busy ? "Saving…" : "Save the whole list"}
            </button>
            <button type="button" className="pt-btn" onClick={() => setRates(null)}>
              Undo
            </button>
          </>
        )}
      </div>

      <h2 className="pt-h2">How you stand</h2>
      <dl className="pt-facts">
        <div>
          <dt>Asked</dt>
          <dd>{me.standing.asked}</dd>
        </div>
        <div>
          <dt>Confirmed</dt>
          <dd>{me.standing.confirmed}</dd>
        </div>
        <div>
          <dt>Could not</dt>
          <dd>{me.standing.could_not}</dd>
        </div>
        <div>
          <dt>Waiting</dt>
          <dd>{me.standing.waiting_on_you}</dd>
        </div>
        {me.standing.past_the_time_promised > 0 && (
          <div>
            <dt>Late</dt>
            <dd>{me.standing.past_the_time_promised} past the time promised</dd>
          </div>
        )}
      </dl>
      <p className="pt-none">{me.standing.how_this_is_worked_out}</p>

      <h2 className="pt-h2">Your money</h2>
      {books === null ? (
        <p className="pt-none">…</p>
      ) : (
        <>
          <dl className="pt-facts">
            <div>
              <dt>You quoted</dt>
              <dd>₹{books.quoted_inr.toLocaleString("en-IN")}</dd>
            </div>
            <div>
              <dt>Family pays</dt>
              <dd>₹{books.family_pays_inr.toLocaleString("en-IN")}</dd>
            </div>
            <div>
              <dt>Our share</dt>
              <dd>
                ₹{books.commission_inr.toLocaleString("en-IN")} ({books.commission_pct}%, capped at{" "}
                {me.commission_cap_pct}%)
              </dd>
            </div>
            <div>
              <dt>You keep</dt>
              <dd>₹{books.you_keep_inr.toLocaleString("en-IN")}</dd>
            </div>
          </dl>
          <p className="pt-detail">{books.note}</p>
          {books.lines.length > 0 && (
            <>
              <h2 className="pt-h2">Line by line</h2>
              {books.lines.map((line) => (
                <div className="pt-job settled" key={`${line.job}-${line.on}`}>
                  <p className="pt-need">₹{line.amount_inr.toLocaleString("en-IN")}</p>
                  <dl className="pt-facts">
                    <div>
                      <dt>On</dt>
                      <dd>{line.on}</dd>
                    </div>
                    <div>
                      <dt>For</dt>
                      <dd>{line.category}</dd>
                    </div>
                    <div>
                      <dt>Job</dt>
                      <dd className="pt-none">{line.job}</dd>
                    </div>
                    <div>
                      <dt>Status</dt>
                      <dd>{line.status}</dd>
                    </div>
                  </dl>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </>
  );
}
