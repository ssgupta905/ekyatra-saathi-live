import { useCallback, useEffect, useState } from "react";
import { research, type BurdenRelease } from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";
import { Panel, SkeletonRows } from "../ui/kit";

/**
 * What this system can give back to cancer research — and what it will not.
 *
 * India has registries full of staging, treatment and survival. What it has
 * almost none of is the thing that decides whether a patient finishes
 * treatment at all: how far they had to come, what it cost them, how many
 * journeys were wasted, how long they waited. Clinicians call it loss to
 * follow-up; the cause is usually a bus fare and a working day, and nobody
 * has the numbers.
 *
 * This system holds exactly those numbers as a side effect of doing its job.
 *
 * WHY THIS SCREEN LEADS WITH THE EXCLUSIONS
 *
 * The temptation in a screen like this is to show the rows and let the
 * absences speak for themselves. They do not. A file of one row from a cohort
 * of four is a different scientific claim from one row out of one, and a
 * reader who cannot tell the difference will assume the flattering reading.
 * So the counts of who was left out, and why, are given the same weight as
 * the data — and the commonest reason for exclusion, no research consent, is
 * stated as a number rather than implied by a gap.
 *
 * WHAT THIS SCREEN CANNOT DO
 *
 * It cannot send anything. There is no button here that transmits, and that
 * is deliberate: the release is assembled for a person to read and then
 * decide about. Nor can it broker clinical records — this contributes what
 * EKYATRA itself observed, and nothing it would have to reach into a
 * hospital to fetch.
 */

/** Columns whose emptiness means something a reader should be told. */
const WHY_EMPTY: Record<string, string> = {
  trips_wasted:
    "only knowable for a journey this system watched end to end; empty for a family onboarded recently",
  clinic_late_minutes:
    "needs the hospital's own arrival timestamps, which only some deployments can read",
  stated_cost_inr: "the family's own figure, and empty until they state one — never an estimate",
  days_delayed: "empty until a step actually moves from its first booked date",
};

export function Research() {
  const [release, setRelease] = useState<BurdenRelease | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    research
      .release()
      .then(setRelease)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (release === null) return <SkeletonRows rows={6} />;

  const { manifest, rows } = release;
  // Columns that are empty for every single row. Called out once, rather than
  // leaving a reader to scan the table and infer it.
  const alwaysEmpty = manifest.columns.filter(
    (column) => rows.length > 0 && rows.every((row) => !row[column]),
  );

  return (
    <>
      <Panel title="Contribute to cancer research">
        <Card
          title={manifest.release}
          hint={`Prepared for ${manifest.recipient} · schema ${manifest.schema_version}`}
        >
          <div className="log-filter">
            <Chip tone="go">{manifest.rows} row(s) in the release</Chip>
            <Chip tone="uncertain">
              {manifest.excluded_no_research_consent} withheld — no research consent
            </Chip>
            {manifest.excluded_too_little_data > 0 && (
              <Chip tone="uncertain">
                {manifest.excluded_too_little_data} withheld — nothing measured yet
              </Chip>
            )}
            <Chip>{manifest.families_considered} families considered</Chip>
          </div>
          <p className="muted">{manifest.consent_basis}</p>
          {manifest.rows === 0 && (
            <Notice tone="warn">
              No family has an active research grant, so there is nothing to
              contribute. This is the correct result, not a failure: consent is
              asked for per family, is revocable, and is never a condition of
              care.
            </Notice>
          )}
        </Card>

        <Card
          title="Removed before anything leaves"
          hint="Each one with the reason it would re-identify somebody"
        >
          <ol className="reasoning">
            {manifest.removed_before_export.map((item) => (
              <li key={item.field} className="step step-guard">
                <Chip tone="uncertain">removed</Chip>
                <span className="step-text">
                  {item.field}
                  <em className="step-again"> — {item.why}</em>
                </span>
              </li>
            ))}
          </ol>
          <p className="muted">{manifest.re_identification_note}</p>
          {!manifest.contains_clinical_data && (
            <p className="muted">
              No clinical value appears above because there is none in this
              system to leak. It never collected a result, a stage or a
              diagnosis.
            </p>
          )}
        </Card>
      </Panel>

      <Panel title="The data itself">
        <Card
          title={`${rows.length} row(s)`}
          hint="Every value as it would be written to the file. An empty cell is a measurement nobody made."
        >
          {rows.length === 0 ? (
            <p className="muted">Nothing to show until a family grants research consent.</p>
          ) : (
            <div className="widget-scroll">
              <table className="audit-table">
                <thead>
                  <tr>
                    {manifest.columns.map((column) => (
                      <th key={column} title={WHY_EMPTY[column] ?? ""}>
                        {column.replace(/_/g, " ")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={`${row.release}-${index}`}>
                      {manifest.columns.map((column) => (
                        <td key={column} className="mono">
                          {row[column] || <span className="muted">—</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {alwaysEmpty.length > 0 && (
            <p className="muted">
              Empty for every row here, and why:{" "}
              {alwaysEmpty
                .map((column) => `${column.replace(/_/g, " ")} — ${WHY_EMPTY[column] ?? "not measured"}`)
                .join("; ")}
              . Left empty rather than zeroed: a zero would read as "the clinic
              was on time" or "nothing was wasted".
            </p>
          )}
        </Card>
      </Panel>
    </>
  );
}
