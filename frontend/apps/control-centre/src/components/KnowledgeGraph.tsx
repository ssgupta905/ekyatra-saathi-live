import { useCallback, useEffect, useState } from "react";
import { requests as requestsApi, type GraphEdge, type GraphNode } from "@saathi/api-client";
import { Card, Notice } from "@saathi/ui-web";
import { SkeletonRows } from "../ui/kit";

/**
 * One family's situation as a graph of things that exist.
 *
 * The honesty of this screen is entirely in what the server sends, and the
 * server sends only what it is holding: a family with no pending order has no
 * pending-order node, and an edge is drawn only when both of its ends are
 * really there. A four-node graph is the right graph when there are four
 * things. This component's job is to not undermine that — so it draws what it
 * is given, says where each node came from, and adds nothing.
 *
 * **Laid out in columns by kind rather than by a force simulation.** A force
 * layout looks more impressive and is harder to read: nodes drift, two runs of
 * the same data look different, and nobody can point at a path and follow it.
 * These journeys read left to right — what the hospital published, what the
 * family said, what we decided — and that is the order a person explains them
 * in out loud.
 *
 * **Every node carries its source.** That line is the whole point of showing a
 * graph rather than a sentence: "OpenEMR calendar" and "the family, in their
 * own words" are different kinds of claim, and a reader should never have to
 * guess which one they are looking at.
 */

//: Left to right, in the order a person tells the story. A kind not listed
//: lands in the last column rather than vanishing — an unplaced node is still
//: a node, and dropping it would make the graph quietly incomplete.
const COLUMNS: { kind: string; heading: string }[] = [
  { kind: "patient", heading: "The family" },
  { kind: "visit", heading: "In the hospital" },
  { kind: "leave", heading: "What changed" },
  { kind: "order", heading: "Outstanding" },
  { kind: "question", heading: "What we asked" },
  { kind: "constraint", heading: "What they said" },
  { kind: "budget", heading: "What it costs them" },
  { kind: "plan", heading: "What we decided" },
];

export function KnowledgeGraph({
  patientId,
  revision,
}: {
  patientId: string;
  revision: number;
}) {
  const [graph, setGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    requestsApi
      .graph(patientId)
      .then(setGraph)
      .catch((e: Error) => setError(e.message));
  }, [patientId]);

  useEffect(load, [load, revision]);

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (graph === null) return <SkeletonRows rows={3} />;

  const placed = new Set<string>();
  const columns = COLUMNS.map(({ kind, heading }) => {
    const nodes = graph.nodes.filter((node) => node.kind === kind);
    nodes.forEach((node) => placed.add(node.id));
    return { heading, nodes };
  }).filter((column) => column.nodes.length > 0);

  // Anything whose kind this component does not know about. Shown rather than
  // dropped: a node the server thought worth sending is not ours to hide.
  const rest = graph.nodes.filter((node) => !placed.has(node.id));
  if (rest.length) columns.push({ heading: "Also", nodes: rest });

  const label = (id: string) =>
    graph.nodes.find((node) => node.id === id)?.label ?? id;

  return (
    <Card
      title="What this is built from"
      hint={
        graph.nodes.length === 0
          ? "Nothing yet."
          : `${graph.nodes.length} things, ${graph.edges.length} relationships — each one a record, not a drawing.`
      }
    >
      {graph.nodes.length === 0 ? (
        <p className="muted">
          Nothing is known about this family yet. The graph fills as the
          hospital publishes and the family answers.
        </p>
      ) : (
        <>
          <div className="kg">
            {columns.map((column) => (
              <div key={column.heading} className="kg-col">
                <h4>{column.heading}</h4>
                {column.nodes.map((node) => (
                  <div key={node.id} className={`kg-node kg-${node.kind}`}>
                    <strong>{node.label}</strong>
                    {node.detail && <span className="kg-detail">{node.detail}</span>}
                    {/* Where it came from. Not decoration: it is the
                        difference between a hospital's record and a
                        family's sentence, and they are not the same claim. */}
                    {node.source && <span className="kg-source">{node.source}</span>}
                  </div>
                ))}
              </div>
            ))}
          </div>

          <details className="kg-edges">
            <summary>{graph.edges.length} relationships</summary>
            <ul>
              {graph.edges.map((edge) => (
                <li key={`${edge.from}-${edge.verb}-${edge.to}`}>
                  <span>{label(edge.from)}</span>
                  <em>{edge.verb.replace(/_/g, " ")}</em>
                  <span>{label(edge.to)}</span>
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </Card>
  );
}
