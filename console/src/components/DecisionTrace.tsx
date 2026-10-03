import { useEffect, useState } from "react";
import { live, LANGUAGE_NAMES, type CareStep, type NarratedNode, type Patient, type PlanResponse } from "../lib/api";
import { buildTrace, type Basis, type TraceNode } from "../lib/explain";
import { Card, Cite, Chip } from "../ui/primitives";
import { Doc, Shield, Speaker, Wave } from "../ui/icons";
import { ReadinessInterval } from "./ReadinessInterval";

/**
 * Why this decision — the chain, top to bottom.
 *
 * Each link states one claim and names what licenses it. The connector down
 * the gutter is the inference: every node follows from the one above it, and
 * the last node is the verdict the hero already showed. A navigator who
 * disagrees with the outcome can point at the link they disagree with.
 */

const BASIS_GLYPH = {
  record: <Doc size={12} />,
  rule: <Shield size={12} />,
  model: <Wave size={12} />,
} as const;

function BasisChip({ basis }: { basis: Basis }) {
  const body = (
    <>
      {BASIS_GLYPH[basis.kind]}
      {basis.label}
    </>
  );
  if (basis.ledgerId) {
    return <Cite ledgerId={basis.ledgerId}>{basis.label}</Cite>;
  }
  return <Chip>{body}</Chip>;
}

function Node({
  node,
  queue,
  narration,
}: {
  node: TraceNode;
  queue: string | null;
  narration?: NarratedNode;
}) {
  return (
    <div className={`node ${node.tone}${node.accent ? ` d-${node.accent}` : ""}`}>
      <div className="gutter">
        <div className="pip" />
      </div>
      <div className="content">
        <div className="step-label">{node.step}</div>
        <div className="claim">{node.claim}</div>
        {node.because && <div className="because">{node.because}</div>}
        {narration &&
          (narration.held ? (
            <div className="narrated held">
              <span className="say-aloud" style={{ color: "var(--critical)" }}>
                held by the guard
              </span>
              {narration.reason ?? "this line cannot be said to the family as written"} —
              say it yourself.
            </div>
          ) : (
            <div className="narrated" lang={narration.language}>
              <span className="say-aloud">say aloud</span>
              {narration.text}
            </div>
          ))}
        {node.window && <ReadinessInterval window={node.window} queue={queue} />}
        {node.rule && (
          <div className="rule">
            <b>Rule applied.</b> {node.rule}
          </div>
        )}
        <div className="sources">
          <span
            style={{
              fontSize: 11,
              color: "var(--ink-4)",
              letterSpacing: 0,
              marginRight: 2,
            }}
          >
            based on
          </span>
          {node.basis.map((b, i) => (
            <BasisChip key={`${b.label}-${i}`} basis={b} />
          ))}
        </div>
      </div>
    </div>
  );
}

export function DecisionTrace({
  response,
  steps,
  patient,
}: {
  response: PlanResponse | null;
  steps: CareStep[];
  patient: Patient;
}) {
  const [narration, setNarration] = useState<Record<string, NarratedNode> | null>(null);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState<string | null>(null);

  // A new family is a new explanation; never carry one page's words onto another.
  useEffect(() => {
    setNarration(null);
    setUnavailable(null);
  }, [patient.id, response?.plan?.decision]);

  if (!response?.plan) return null;
  const nodes = buildTrace(response, steps);

  const language = LANGUAGE_NAMES[patient.language];

  const narrate = async () => {
    if (narration) {
      setNarration(null);
      return;
    }
    setLoading(true);
    try {
      const result = await live.narration(
        patient.id,
        nodes.map((n) => ({ id: n.id, text: `${n.step}. ${n.claim}` })),
      );
      if (!result.available) {
        setUnavailable(result.reason ?? "not available");
        return;
      }
      setNarration(Object.fromEntries(result.nodes.map((n) => [n.id, n])));
    } catch {
      setUnavailable("narration could not be produced");
    } finally {
      setLoading(false);
    }
  };
  const queueOf = (nodeId: string) => {
    const stepId = nodeId.replace(/^blocked-/, "");
    return steps.find((s) => s.id === stepId)?.queue ?? null;
  };

  return (
    <Card
      title="Why this decision"
      hint="every claim names its basis"
      aside={
        <button
          type="button"
          className={narration ? "btn small primary" : "btn small"}
          onClick={narrate}
          disabled={loading}
          title={`Read this out in ${language}`}
        >
          <span style={{ display: "inline-flex", verticalAlign: "-2px", marginRight: 5 }}>
            <Speaker size={12} />
          </span>
          {loading ? "translating…" : narration ? `hide ${language}` : `say in ${language}`}
        </button>
      }
      flush
      note={
        <>
          A claim with no basis is never shown to a family and never shown here. The
          language layer re-checks the rendered message against this plan, so a
          message that says “travel” under a WAIT plan is blocked even if the planner
          and the renderer both fail — and a translated line gets the same check
          before a navigator reads it out.
        </>
      }
    >
      {unavailable && (
        <div style={{ padding: "0 20px 14px" }}>
          <Chip>narration unavailable · {unavailable}</Chip>
        </div>
      )}
      <div className="trace trace-cap">
        {nodes.map((n) => (
          <Node key={n.id} node={n} queue={queueOf(n.id)} narration={narration?.[n.id]} />
        ))}
      </div>
    </Card>
  );
}
