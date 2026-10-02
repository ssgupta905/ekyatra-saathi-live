import type { Patient, PlanResponse } from "../lib/api";
import { LANGUAGE_NAMES } from "../lib/api";
import { Badge, Card, Cite, Chip, Disclosure, Notice } from "../ui/primitives";
import { CheckCircle, Phone, Shield, Stop } from "../ui/icons";

/**
 * What the family actually hears, and the four gates it had to clear.
 *
 * The gates are shown even when they all pass, because the useful fact is not
 * "a message went out" — it is *which stage would have stopped it*. When the
 * guard does stop one, this is the only place a navigator learns that the
 * family is waiting on a human rather than on Saathi.
 */

type GateState = "pass" | "stop" | "off";

function Gate({
  name,
  state,
  verdict,
  why,
}: {
  name: string;
  state: GateState;
  verdict: string;
  why: string;
}) {
  return (
    <div className={`gate ${state}`}>
      <div className="gname">{name}</div>
      <div className="gstate">
        {state === "pass" ? <CheckCircle size={14} /> : state === "stop" ? <Stop size={14} /> : null}
        {verdict}
      </div>
      <div className="gwhy">{why}</div>
    </div>
  );
}

export function MessagePipeline({
  response,
  patient,
}: {
  response: PlanResponse | null;
  patient: Patient;
}) {
  const plan = response?.plan ?? null;
  const blocked = Boolean(response?.routed_to_care_team);
  const body = response?.message_body ?? null;
  const language = LANGUAGE_NAMES[patient.language];
  // Name the backend that actually ran. Saying "Claude" when Groq rendered it
  // is the kind of small untruth that makes a reader doubt the big claims.
  const renderedBy = response?.rendered_by ?? "The language layer";

  const planGate: GateState = plan ? "pass" : "off";
  const draftGate: GateState = blocked ? "off" : body ? "pass" : "off";
  const guardGate: GateState = blocked ? "stop" : body ? "pass" : "off";
  const sendGate: GateState = blocked ? "stop" : body ? "pass" : "off";

  return (
    <Card
      title="Message to the family"
      hint={`${language} · WhatsApp and voice`}
      aside={
        blocked ? (
          <Badge tone="critical" icon={<Shield size={13} />}>
            Held by the guard
          </Badge>
        ) : body ? (
          <Badge tone="go" icon={<Shield size={13} />}>
            Cleared the guard
          </Badge>
        ) : (
          <Chip>Language layer off</Chip>
        )
      }
      note="Saathi states status and logistics. It never gives a result, a diagnosis, a medicine or a symptom answer — those route to the care team, every time, by design rather than by prompt."
    >
      <div className="gates">
        <Gate
          name="1 · Plan"
          state={planGate}
          verdict={plan ? plan.decision.toUpperCase() : "none"}
          why={
            plan
              ? `Decided in code, with ${plan.evidence.length} evidence reference${
                  plan.evidence.length === 1 ? "" : "s"
                }.`
              : "Nothing to say without a plan."
          }
        />
        <Gate
          name="2 · Render"
          state={draftGate}
          verdict={blocked ? "skipped" : body ? renderedBy.split(" · ")[0].toLowerCase() : "off"}
          why={
            blocked
              ? "Nothing was rendered — the question needed a person."
              : body
                ? `${renderedBy}${
                    response?.render_ms ? ` · ${Math.round(response.render_ms)} ms` : ""
                  } wrote ${language} from approved templates. No tools, schema-constrained, plan as its only input.`
                : "No language credentials set. The plan above was still decided in full."
          }
        />
        <Gate
          name="3 · Guard"
          state={guardGate}
          verdict={blocked ? "held" : body ? "clean" : "—"}
          why={
            blocked
              ? response?.escalation ?? "Routed to the care team."
              : body
                ? "Re-checked against the plan: no clinical content, no claim the plan does not support."
                : "Nothing to check."
          }
        />
        <Gate
          name="4 · Send"
          state={sendGate}
          verdict={blocked ? "not sent" : body ? "queued" : "—"}
          why={
            blocked
              ? "A navigator calls instead."
              : body
                ? `WhatsApp, and read aloud on the voice line in ${language}.`
                : "Nothing queued."
          }
        />
      </div>

      {blocked ? (
        <div style={{ marginTop: 16 }}>
          <Notice tone="stop">
            <strong>Not sent.</strong>{" "}
            {response?.escalation ??
              "The guard routed this to the care team rather than answering it."}{" "}
            The family has been told a person will call — nothing else.
          </Notice>
        </div>
      ) : body ? (
        <div className="handset">
          <div className="hs-head">
            <Phone />
            {patient.caregiver_phone} · {language}
          </div>
          <div className="bubble" lang={patient.language}>
            {body}
          </div>
          <div className="hs-foot">
            <span style={{ fontSize: 11, color: "var(--ink-4)", letterSpacing: 0 }}>
              sourced from
            </span>
            {(plan?.evidence ?? []).map((e) => (
              <Cite key={e.ledger_id} ledgerId={e.ledger_id}>
                {e.source_record_id}
              </Cite>
            ))}
            {(plan?.evidence ?? []).length === 0 && <Chip>no references</Chip>}
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 16 }}>
          <Notice tone="calm">
            No message composed — the language layer is off. The decision, the window and
            the evidence above were all produced without it; language is the last mile,
            not the reasoning.
          </Notice>
        </div>
      )}

      <div style={{ marginTop: 14 }}>
        <Disclosure summary="What the guard blocks, and on which side">
          <div style={{ fontSize: 13, color: "var(--ink-2)", letterSpacing: 0, maxWidth: "72ch" }}>
            <p style={{ margin: "0 0 8px" }}>
              <b>Inbound.</b> A family message that reads as clinical — a symptom, a
              medicine, a reading, a request to interpret a report — is never answered.
              It is logged as an alert and a navigator calls.
            </p>
            <p style={{ margin: 0 }}>
              <b>Outbound.</b> A drafted message is re-validated against the plan it came
              from. Any sentence asserting something the plan does not contain — a date
              under WAIT, a result, a reassurance — fails the check and the message is
              held rather than trimmed.
            </p>
          </div>
        </Disclosure>
      </div>
    </Card>
  );
}
