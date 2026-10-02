import { useEffect, useState } from "react";
import { live, type CallBrief as Brief } from "../lib/api";
import { Card, Cite, Chip } from "../ui/primitives";
import { Spark } from "../ui/icons";

/**
 * Four lines to read before dialling.
 *
 * The model summarises records the navigator already has, which is the only
 * reason it is allowed anywhere near this page. The enforcement is in code, not
 * in the prompt: a line whose citations do not resolve in the ledger is dropped
 * before it reaches the screen, so every chip here opens a real row.
 */
export function CallBrief({
  patientId,
  revision,
}: {
  patientId: string;
  /** Bumped when something about this family changed — refetch, don't cache. */
  revision: number;
}) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    live
      .brief(patientId)
      .then((result) => {
        if (!cancelled) setBrief(result);
      })
      .catch(() => {
        if (!cancelled) setBrief(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId, revision]);

  if (!brief?.available && !loading) return null;

  return (
    <Card
      title="Before you call"
      hint={brief?.model}
      aside={
        <Chip tone="info">
          <Spark size={11} />
          summary of records already on this page
        </Chip>
      }
      note="Every line cites the ledger rows it rests on, and a line whose citation does not resolve is dropped rather than shown. The model reads; it does not decide."
    >
      {loading && !brief ? (
        <div style={{ display: "grid", gap: 9, maxWidth: 460 }}>
          <div className="skeleton" />
          <div className="skeleton" style={{ width: "82%" }} />
          <div className="skeleton" style={{ width: "64%" }} />
        </div>
      ) : brief && brief.lines.length === 0 ? (
        <p className="empty">Nothing worth saying ahead of the call yet.</p>
      ) : (
        <div className="brief">
          {brief?.lines.map((line, index) => (
            <div className="brief-line" key={`${index}-${line.text.slice(0, 16)}`}>
              <span className="bullet">
                <Spark size={13} />
              </span>
              <span className="say">
                {line.text}
                <span className="cites">
                  {line.ledger_ids.map((id) => (
                    <Cite key={id} ledgerId={id}>
                      source
                    </Cite>
                  ))}
                </span>
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
