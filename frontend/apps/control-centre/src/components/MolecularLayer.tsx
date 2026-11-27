import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  molecular,
  type MolecularRegister,
  type MolecularState,
  type MolecularTest,
} from "@saathi/api-client";
import { Notice } from "@saathi/ui-web";
import { Pill, SkeletonRows, useToast } from "../ui/kit";

/**
 * Which molecular tests this patient has had, and where the reports are.
 *
 * WHY THIS SCREEN HOLDS NO RESULTS
 *
 * Because the system does not have any, and should not. No hospital system in
 * this project's reach exposes a structured molecular result — OpenEMR has no
 * genomics resource at all; asking its FHIR API for `MolecularSequence`
 * returns a 404 because the route does not exist. A panel in India is ordered,
 * often at an outside lab, and comes back as a PDF that is handed over.
 *
 * So what is worth holding is not the science. It is the fact of the test:
 * which panel, when, which lab, did the report come back, and where the
 * document is. That fact is a logistics fact, and losing it costs a family
 * real money — a patient moving from a district hospital to a tertiary centre
 * is routinely re-tested because nobody can find the panel done three months
 * ago. Twenty-five to eighty thousand rupees and several weeks, in a household
 * counting a nine-hundred-rupee bus fare.
 *
 * WHY THE HEADLINE NUMBER IS "CANNOT BE FETCHED"
 *
 * A doctor scanning a list of tests will read "this was done" as "so I need
 * not order it". That is only true if the report can actually be produced. The
 * count of reports that exist but are not reachable from here is the one
 * number on this screen that changes what somebody does next, so it leads —
 * and a report that is merely still awaited is counted separately, because
 * waiting and lost call for different actions.
 */

const STATE_WORDS: Record<MolecularState, { label: string; tone: "go" | "wait" | "critical" }> = {
  held: { label: "report held", tone: "go" },
  awaited: { label: "not back yet", tone: "wait" },
  elsewhere: { label: "not held here", tone: "critical" },
};

const TESTS: { id: MolecularTest; label: string }[] = [
  { id: "targeted_panel", label: "Targeted panel" },
  { id: "single_gene", label: "Single-gene test" },
  { id: "ihc", label: "Immunohistochemistry" },
  { id: "fish", label: "FISH" },
  { id: "karyotype", label: "Karyotyping" },
  { id: "exome", label: "Exome sequencing" },
  { id: "genome", label: "Genome sequencing" },
  { id: "transcriptome", label: "Transcriptomic panel" },
  { id: "proteomic", label: "Proteomic panel" },
  { id: "other", label: "Other" },
];

const BLANK = {
  test: "targeted_panel" as MolecularTest,
  state: "held" as MolecularState,
  lab_name: "",
  ordered_by_centre: "",
  ordered_on: "",
  reported_on: "",
  document_ref: "",
  note: "",
};

export function MolecularLayer({
  patientId,
  revision,
  canRecord,
}: {
  patientId: string;
  revision: number;
  canRecord: boolean;
}) {
  const [register, setRegister] = useState<MolecularRegister | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState(BLANK);
  const [refused, setRefused] = useState<string | null>(null);
  const toast = useToast();

  const load = useCallback(() => {
    molecular
      .register(patientId)
      .then((r) => {
        setRegister(r);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(
          e instanceof ApiError && e.status === 403
            ? "Only a doctor may read this register."
            : String(e),
        ),
      );
  }, [patientId]);

  useEffect(load, [load, revision]);

  const save = async () => {
    setRefused(null);
    try {
      const saved = await molecular.record(patientId, {
        test: draft.test,
        state: draft.state,
        lab_name: draft.lab_name,
        ordered_by_centre: draft.ordered_by_centre,
        ordered_on: draft.ordered_on || null,
        reported_on: draft.reported_on || null,
        document_ref: draft.document_ref,
        note: draft.note,
      });
      toast(saved.summary);
      setDraft(BLANK);
      setAdding(false);
      load();
    } catch (e: unknown) {
      // The server's refusals here are the feature working, not a failure, so
      // they are shown where the typing happened rather than as an error.
      setRefused(e instanceof ApiError ? String(e.message ?? e) : String(e));
    }
  };

  const withdraw = async () => {
    const gone = await molecular.forget(patientId);
    toast(
      gone.removed
        ? `${gone.removed} record(s) deleted. Not hidden — deleted.`
        : "Nothing was held.",
    );
    load();
  };

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (register === null) return <SkeletonRows rows={4} />;

  if (!register.consented) {
    return (
      <Notice tone="warn">
        {/* The server's sentence, punctuated here: it is written to be read
            aloud as a reason, not to be glued to the sentence after it. */}
        {(register.why ?? "No consent for a molecular register").replace(/\.?$/, ".")} Ask
        for it under
        “What the family has agreed to share” — it is its own purpose, so
        agreeing here does not touch anything else they have agreed to, and
        withdrawing it later does not affect their care.
        <br />
        <br />
        This is not the same as “this patient has had no tests”. Nobody has
        asked yet, so nobody knows.
      </Notice>
    );
  }

  const awaited = register.reports.filter((r) => r.state === "awaited").length;

  return (
    <>
      <div className="log-filter">
        <Pill tone={register.not_reachable ? "critical" : "go"}>
          {register.not_reachable} report(s) cannot be fetched from here
        </Pill>
        {awaited > 0 && <Pill tone="wait">{awaited} still awaited</Pill>}
        <Pill>{register.reports.length} test(s) on record</Pill>
      </div>

      {register.not_reachable > 0 && (
        <Notice tone="warn">
          A test shown here as done is only a reason not to repeat it if the
          report can actually be produced. {register.not_reachable} of these
          cannot be, from this system — ask the centre that ordered it before
          assuming a repeat is unnecessary.
        </Notice>
      )}

      {register.reports.length === 0 ? (
        <p className="muted">
          The family has agreed to a register, and nothing is on it yet.
        </p>
      ) : (
        <div className="widget-scroll">
          <table className="audit-table">
            <thead>
              <tr>
                <th>Test</th>
                <th>Taken</th>
                <th>Reported</th>
                <th>Lab</th>
                <th>Ordered by</th>
                <th>Report</th>
                <th>Where</th>
              </tr>
            </thead>
            <tbody>
              {register.reports.map((row) => {
                const word = STATE_WORDS[row.state];
                return (
                  <tr key={row.id}>
                    <td>{row.test_name}</td>
                    <td className="mono">{row.ordered_on || <span className="muted">—</span>}</td>
                    <td className="mono">{row.reported_on || <span className="muted">—</span>}</td>
                    <td>{row.lab_name || <span className="muted">—</span>}</td>
                    <td>{row.ordered_by_centre || <span className="muted">—</span>}</td>
                    <td>
                      <Pill tone={word.tone}>{word.label}</Pill>
                    </td>
                    <td className="mono">
                      {row.document_ref || <span className="muted">nowhere to point</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="muted">
        No result appears above because this system holds none. It records that
        a test happened and where its report is; what the report says stays in
        the report, with the clinicians reading it.
      </p>

      {canRecord && !adding && (
        <div className="log-filter">
          <button type="button" className="btn" onClick={() => setAdding(true)}>
            Record a test
          </button>
          {register.reports.length > 0 && (
            <button type="button" className="btn" onClick={withdraw}>
              Delete the register (withdrawal)
            </button>
          )}
        </div>
      )}

      {canRecord && adding && (
        <div className="iss-fields-wrap" style={{ marginTop: 14 }}>
          {refused && <Notice tone="warn">{refused}</Notice>}
          <div className="iss-fields">
          <label>
            Which test
            <select
              value={draft.test}
              onChange={(e) => setDraft({ ...draft, test: e.target.value as MolecularTest })}
            >
              {TESTS.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Where the report is
            <select
              value={draft.state}
              onChange={(e) => setDraft({ ...draft, state: e.target.value as MolecularState })}
            >
              <option value="held">Held — we can produce it</option>
              <option value="elsewhere">Exists, but not reachable from here</option>
              <option value="awaited">Ordered, not back yet</option>
            </select>
          </label>
          <label>
            Lab that ran it
            <input
              value={draft.lab_name}
              onChange={(e) => setDraft({ ...draft, lab_name: e.target.value })}
              placeholder="Tata Memorial molecular pathology"
            />
          </label>
          <label>
            Centre that ordered it
            <input
              value={draft.ordered_by_centre}
              onChange={(e) => setDraft({ ...draft, ordered_by_centre: e.target.value })}
              placeholder="TMH Mumbai"
            />
          </label>
          <label>
            Taken on
            <input
              type="date"
              value={draft.ordered_on}
              onChange={(e) => setDraft({ ...draft, ordered_on: e.target.value })}
            />
          </label>
          <label>
            Reported on
            <input
              type="date"
              value={draft.reported_on}
              onChange={(e) => setDraft({ ...draft, reported_on: e.target.value })}
            />
          </label>
          <label>
            Where the document is
            <input
              value={draft.document_ref}
              onChange={(e) => setDraft({ ...draft, document_ref: e.target.value })}
              placeholder="tmh/lab/7781, or “family holds the paper copy”"
            />
          </label>
          <label>
            Note
            <input
              value={draft.note}
              onChange={(e) => setDraft({ ...draft, note: e.target.value })}
              placeholder="anything the fields above cannot hold — not a finding"
            />
          </label>
          </div>
          <div className="iss-actions" style={{ marginTop: 10 }}>
            <button type="button" className="btn primary" onClick={save}>
              Record it
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setAdding(false);
                setRefused(null);
              }}
            >
              Cancel
            </button>
          </div>
          <p className="muted">
            A finding typed into any of these fields is refused by the server,
            naming the word that tripped it. Deliberately blunt: a false refusal
            costs a rephrase, a false accept puts a clinical claim inside a
            logistics system.
          </p>
        </div>
      )}
    </>
  );
}
