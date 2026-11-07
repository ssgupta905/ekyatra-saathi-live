import { useCallback, useEffect, useState } from "react";
import { budget as budgetApi, type BudgetWaiting } from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { SkeletonRows, useToast } from "../ui/kit";

/**
 * What families have said they can manage, waiting on a person.
 *
 * Sits beside the re-plan queue because it is the same kind of thing: the
 * family has said something about their own circumstances and nothing has
 * happened yet. A family who answered a question and was never confirmed has
 * been asked for nothing, which is worse than not asking — it teaches them the
 * screen does not listen, and they stop reading it.
 *
 * Two rows that look alike and are not. A chosen organisation is a booking to
 * move. "We cannot manage any of this" is a person to call, and it sorts to the
 * top and is marked, because confirming it changes no journey: it raises a
 * social-work alert and leaves the plan exactly where it was.
 */
export function BudgetQueue({ revision }: { revision: number }) {
  const [rows, setRows] = useState<BudgetWaiting[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const load = useCallback(() => {
    budgetApi
      .waiting()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load, revision]);

  const confirm = async (row: BudgetWaiting) => {
    const key = `${row.patient_id}:${row.topic}`;
    setBusy(key);
    try {
      await budgetApi.confirm(row.patient_id, row.topic);
      toast(
        row.needs_help
          ? `Raised with the social-work desk for ${row.name}. No journey changed.`
          : `${row.name}'s ${row.topic} will go to ${row.organisation}.`,
      );
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not confirm");
    } finally {
      setBusy(null);
    }
  };

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (rows === null) return <SkeletonRows rows={2} />;
  if (rows.length === 0) return null;

  return (
    <Card
      title="What families say they can manage"
      hint="Their own answer about cost. Nothing moved until you agree it is what they meant."
    >
      <table>
        <thead>
          <tr>
            <th>Family</th>
            <th>About</th>
            <th>They said</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = `${row.patient_id}:${row.topic}`;
            return (
              <tr key={key}>
                <td>
                  <strong>{row.name}</strong>
                  <span className="hint" style={{ display: "block" }}>
                    {row.patient_id}
                  </span>
                </td>
                <td>{row.topic}</td>
                <td>
                  {row.needs_help ? (
                    <>
                      <Chip tone="critical">cannot manage it</Chip>
                      <span className="hint" style={{ display: "block", marginTop: 4 }}>
                        Confirming raises the social-work desk. It books nothing.
                      </span>
                    </>
                  ) : (
                    <Chip tone="neutral">{row.organisation ?? row.organisation_id}</Chip>
                  )}
                  {/* Their own words, when they spoke rather than tapped, so a
                      navigator can check the transcription against the option
                      it was matched to. */}
                  {row.said && (
                    <span className="hint" style={{ display: "block", marginTop: 4 }}>
                      “{row.said}”
                    </span>
                  )}
                </td>
                <td style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    className="btn primary small"
                    disabled={busy !== null}
                    onClick={() => confirm(row)}
                  >
                    {busy === key ? "…" : row.needs_help ? "Raise it" : "Confirm"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
