import { useState } from "react";
import { ApiError, apiUrl, records, type ImportReport } from "@saathi/api-client";
import { Card, Chip, Notice } from "@saathi/ui-web";

/**
 * Bring existing records in from a file, looked at before anything is written.
 *
 * Choosing a file only previews it. The button that writes appears once the
 * preview is clean, and nothing is half-entered: one bad row stops the file.
 * A FHIR bundle is read for status and dates only; its report content never
 * leaves the server's parser.
 */
export function ImportRecords({ onImported }: { onImported: () => void }) {
  const [file, setFile] = useState<{ name: string; text: string; kind: "csv" | "fhir" } | null>(null);
  const [hospital, setHospital] = useState("");
  const [distance, setDistance] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (source: NonNullable<typeof file>, commit: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const result =
        source.kind === "csv"
          ? await records.importCsv(source.text, commit)
          : await records.importFhir(JSON.parse(source.text), {
              hospitalId: hospital,
              commit,
              defaultDistanceKm: distance ? Number(distance) : undefined,
            });
      setReport(result);
      if (commit) {
        setFile(null);
        onImported();
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && typeof e.detail === "object" && e.detail) {
        setReport(e.detail as ImportReport);
      } else {
        setError(e instanceof SyntaxError ? "That file is not valid JSON." : String(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const choose = async (picked: File | undefined) => {
    if (!picked) return;
    const text = await picked.text();
    const kind = picked.name.toLowerCase().endsWith(".json") ? "fhir" : "csv";
    const next = { name: picked.name, text, kind } as const;
    setFile(next);
    setReport(null);
    if (kind === "csv" || hospital) await run(next, false);
  };

  const clean = report !== null && report.errors.length === 0 && report.committed === null;
  const needsHospital = file?.kind === "fhir" && !hospital;

  return (
    <Card
      title="Import records"
      hint="a CSV from the template, or a FHIR bundle"
      note="Choosing a file only previews it. Nothing is written until you press Import, and a file with any error is not written at all."
    >
      <div className="iss-actions">
        <input
          type="file"
          accept=".csv,.json"
          onChange={(e) => choose(e.target.files?.[0])}
          aria-label="Choose a CSV or FHIR file"
        />
        <a className="btn small" href={apiUrl("/import/template.csv")} download="saathi-template.csv">
          Download the CSV template
        </a>
      </div>

      {file?.kind === "fhir" && (
        <div className="iss-fields" style={{ marginTop: 10 }}>
          <label>
            Hospital id
            <input value={hospital} onChange={(e) => setHospital(e.target.value)} />
          </label>
          <label>
            Distance if the bundle has none (km)
            <input type="number" min={0} value={distance} onChange={(e) => setDistance(e.target.value)} />
          </label>
          <label>
            &nbsp;
            <button type="button" className="btn" disabled={busy || needsHospital} onClick={() => run(file, false)}>
              Preview
            </button>
          </label>
        </div>
      )}

      {error && <Notice tone="warn">{error}</Notice>}

      {report && (
        <div className="iss-reading">
          <div className="iss-read-as">
            <Chip tone={report.errors.length ? "wait" : "go"}>
              {report.errors.length ? `${report.errors.length} to fix` : "clean"}
            </Chip>
            <span>
              {report.counts.patients} families, {report.counts.family_members} family members,{" "}
              {report.counts.steps} steps
              {report.counts.skipped > 0 && `, ${report.counts.skipped} skipped`}
            </span>
          </div>
          {report.errors.length > 0 && (
            <ul>
              {report.errors.map((issue, i) => (
                <li key={i}>
                  <strong>{issue.where}</strong>: {issue.message}
                </li>
              ))}
            </ul>
          )}
          {report.committed && (
            <Notice tone="calm">
              Imported. {report.committed.replanned} families re-planned
              {report.committed.released > 0 && `, ${report.committed.released} reports recorded as released`}.
            </Notice>
          )}
          {clean && file && (
            <div className="iss-actions">
              <button type="button" className="btn primary" disabled={busy} onClick={() => run(file, true)}>
                Import {file.name}
              </button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
