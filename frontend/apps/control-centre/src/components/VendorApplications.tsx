import { useCallback, useEffect, useState } from "react";
import { partner, type VendorApplicationRow } from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { EmptyState, SkeletonRows, useToast } from "../ui/kit";
import { Building } from "../ui/icons";

/**
 * Vendors asking to join, and the decision somebody has to make about each.
 *
 * WHY THIS SCREEN EXISTS AT ALL
 *
 * The vendor app can be applied to without an account. That is only safe
 * because of what an application is: an organisation with `active` false, which
 * every selection rule in this system already skips. Nothing routes to it,
 * nothing is shown to a family, and it can see nothing. The safety is in the
 * flag — and the flag is only worth anything if somebody actually turns it on
 * deliberately, which is what this screen is for.
 *
 * WHAT THE REVIEWER IS SHOWN
 *
 * Everything the applicant said about itself, including its prices, because
 * the prices are the part a reviewer can sanity-check against what families
 * already report paying. A vendor quoting four times the going rate for a
 * station pickup is the thing to catch here, and it is invisible if the rate
 * card is collapsed behind a link.
 *
 * WHY DECLINING KEEPS THE RECORD
 *
 * A declined vendor that vanished would reapply, be reviewed by somebody who
 * never saw the first decision, and be declined again — or not. The reason
 * stays with the record so the second reviewer inherits the first one's work.
 */
export function VendorApplications({
  canDecide,
  onDecided,
}: {
  canDecide: boolean;
  /** Told when a decision lands, so the network list beside this one stops
   *  showing the row as it was before. Without it an administrator approves,
   *  switches tab, and sees "applied" — which reads as a failure. */
  onDecided?: () => void;
}) {
  const [rows, setRows] = useState<VendorApplicationRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [terms, setTerms] = useState({ commission_pct: 0, username: "", password: "" });
  const [reason, setReason] = useState("");
  const toast = useToast();

  const load = useCallback(() => {
    partner
      .applications()
      .then((all) => {
        setRows(all);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  const approve = async (row: VendorApplicationRow) => {
    try {
      const done = await partner.approve(row.id, {
        commission_pct: Number(terms.commission_pct) || 0,
        ...(terms.username && terms.password
          ? { username: terms.username.trim(), password: terms.password }
          : {}),
      });
      toast(
        done.account
          ? `${row.name} is in, and can sign in as ${done.account}.`
          : `${row.name} is in. Create their login under People and roles.`,
      );
      setDeciding(null);
      setTerms({ commission_pct: 0, username: "", password: "" });
      load();
      onDecided?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const decline = async (row: VendorApplicationRow) => {
    try {
      await partner.decline(row.id, reason.trim());
      toast(`${row.name} declined. The reason is on the record.`);
      setDeciding(null);
      setReason("");
      load();
      onDecided?.();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (rows === null) return <SkeletonRows rows={4} />;

  if (rows.length === 0) {
    return (
      <Card title="Applications" hint="vendors asking to join">
        <EmptyState title="Nobody is waiting" icon={<Building />}>
          A vendor who applies from the partner app appears here. Until somebody
          approves them they are in the directory switched off, so no family's
          journey can reach them.
        </EmptyState>
      </Card>
    );
  }

  return (
    <Card title="Applications" hint={`${rows.length} waiting on a decision`}>
      <Notice tone="calm">
        An application is already in the directory, switched off. Nothing routes
        to it and it can see nothing. Approving is the moment that changes.
      </Notice>

      {rows.map((row) => (
        <div key={row.id} className="ui-layer open" style={{ marginBottom: 12 }}>
          <div className="ui-layer-body">
            <h3>
              {row.name} <Chip tone="uncertain">awaiting review</Chip>
            </h3>
            <table className="audit-table">
              <tbody>
                <tr>
                  <th>Short name</th>
                  <td className="mono">{row.id}</td>
                </tr>
                <tr>
                  <th>Kind</th>
                  <td>{row.type}</td>
                </tr>
                <tr>
                  <th>Applied</th>
                  <td>{row.applied_on ?? "—"}</td>
                </tr>
                <tr>
                  <th>Covers</th>
                  <td>{row.districts.length ? row.districts.join(", ") : "anywhere"}</td>
                </tr>
                <tr>
                  <th>Offers</th>
                  <td>{row.services.length ? row.services.join(", ") : "—"}</td>
                </tr>
                <tr>
                  <th>Contact</th>
                  <td>{row.contact}</td>
                </tr>
                <tr>
                  <th>Hours</th>
                  <td>{row.hours || "—"}</td>
                </tr>
              </tbody>
            </table>

            {row.applicant_note && <p className="muted">“{row.applicant_note}”</p>}

            <h4>What they say they charge</h4>
            {row.rate_card.length === 0 ? (
              <p className="muted">
                No rates given. Worth asking for before approving: a vendor
                whose prices nobody has seen cannot be checked against what
                families already report paying.
              </p>
            ) : (
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Charged by</th>
                    <th>Rupees</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {row.rate_card.map((rate, index) => (
                    <tr key={`${rate.service}-${index}`}>
                      <td>{rate.service}</td>
                      <td>{rate.unit}</td>
                      <td className="mono">₹{rate.amount_inr.toLocaleString("en-IN")}</td>
                      <td>{rate.note || <span className="muted">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {!canDecide && (
              <p className="muted">
                Letting a vendor into the network is an administrator's
                decision. This is here so you can see who is asking.
              </p>
            )}

            {canDecide && deciding !== row.id && (
              <div className="log-filter" style={{ marginTop: 12 }}>
                <button type="button" className="btn primary" onClick={() => setDeciding(row.id)}>
                  Decide
                </button>
              </div>
            )}

            {canDecide && deciding === row.id && (
              <>
                <div className="iss-fields" style={{ marginTop: 12 }}>
                  <label>
                    Commission agreed (%)
                    <input
                      inputMode="decimal"
                      value={terms.commission_pct || ""}
                      onChange={(e) =>
                        setTerms({ ...terms, commission_pct: Number(e.target.value || 0) })
                      }
                      placeholder="0"
                    />
                  </label>
                  <label>
                    Their sign-in name (optional)
                    <input
                      value={terms.username}
                      onChange={(e) => setTerms({ ...terms, username: e.target.value })}
                      placeholder={row.id}
                    />
                  </label>
                  <label>
                    First password (optional)
                    <input
                      type="password"
                      value={terms.password}
                      onChange={(e) => setTerms({ ...terms, password: e.target.value })}
                      placeholder="at least 8 characters"
                    />
                  </label>
                </div>
                <p className="muted">
                  The commission is capped, and it comes off our side: the
                  family is told the vendor's price and pays the vendor's price.
                  Leave the login blank to create it separately under People and
                  roles.
                </p>

                <div className="iss-fields">
                  <label>
                    Or decline, saying why
                    <input
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="no commercial vehicle permit on file"
                    />
                  </label>
                </div>

                <div className="iss-actions" style={{ marginTop: 10 }}>
                  <button type="button" className="btn primary" onClick={() => approve(row)}>
                    Approve
                  </button>
                  <button
                    type="button"
                    className="btn"
                    disabled={reason.trim().length < 3}
                    onClick={() => decline(row)}
                  >
                    Decline
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => {
                      setDeciding(null);
                      setReason("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      ))}
    </Card>
  );
}
