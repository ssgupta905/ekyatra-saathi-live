import type { PlanResponse } from "../lib/api";
import { Card, Chip, Notice } from "../ui/primitives";
import { CheckCircle, Pin } from "../ui/icons";

/**
 * What the family carries, and where they walk in.
 *
 * This is the half of the plan that saves a second journey: a family that
 * reaches the hub without its blocks, slips or scheme card has travelled for
 * nothing just as surely as one whose report had not landed. The list is
 * produced by the planner from the centre's prerequisite rules — it is not
 * advice, and nothing clinical appears on it.
 */
export function VisitChecklist({ response }: { response: PlanResponse | null }) {
  const plan = response?.plan;
  if (!plan) return null;

  const { what_to_bring, where_to_go_first, decision } = plan;

  if (what_to_bring.length === 0 && !where_to_go_first) {
    return (
      <Card title="Visit checklist" hint="issued with a travel date">
        <Notice tone="calm">
          No checklist yet. Saathi issues one only alongside a {decision === "wait" ? "GO" : "travel"}{" "}
          decision — a list sent under WAIT reads as permission to set out.
        </Notice>
      </Card>
    );
  }

  return (
    <Card
      title="Visit checklist"
      hint="sent to the family with the travel date"
      note="Drawn from the centre's prerequisite rules for this stage. Documents and entitlements only — never a medicine, a dose or a preparation instruction."
    >
      {where_to_go_first && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
          <span style={{ color: "var(--blue-600)", display: "flex" }}>
            <Pin size={16} />
          </span>
          <span style={{ fontSize: 15 }}>
            Go first to <b style={{ fontWeight: 590 }}>{where_to_go_first}</b>
          </span>
        </div>
      )}

      {what_to_bring.length > 0 && (
        <>
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              color: "var(--ink-4)",
              marginBottom: 8,
            }}
          >
            Carry {what_to_bring.length} item{what_to_bring.length === 1 ? "" : "s"}
          </div>
          <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: 8 }}>
            {what_to_bring.map((item) => (
              <li key={item} style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
                <span style={{ color: "var(--ink-4)", display: "flex", marginTop: 2 }}>
                  <CheckCircle size={15} />
                </span>
                <span style={{ fontSize: 14.5 }}>{item}</span>
              </li>
            ))}
          </ul>
          <div style={{ marginTop: 14 }}>
            <Chip>Read aloud on the voice line, item by item, with keypad confirmation</Chip>
          </div>
        </>
      )}
    </Card>
  );
}
