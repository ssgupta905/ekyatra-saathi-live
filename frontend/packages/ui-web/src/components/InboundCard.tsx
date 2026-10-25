import { LANGUAGE_NAMES, type InboundMessage } from "@saathi/api-client";
import { fmtStamp } from "../format";
import { CheckCircle, Inbox, Shield, Spark, Stop } from "../icons";
import { Badge, Card, Chip } from "../primitives";

/**
 * What the family wrote in, and what the guard did with it.
 *
 * This is the clearest thing in the console: a real message arrives, the real
 * `screen_inbound` reads it, and a clinical question is answered by nobody. The
 * trigger terms are shown because "the model decided" is not an explanation a
 * clinician can audit — a word list is.
 */
export function InboundCard({
  messages,
  language,
}: {
  messages: InboundMessage[];
  /** The family's language code, as the board reports it. */
  language: string;
}) {
  const recent = messages.slice(-4).reverse();

  return (
    <Card
      title="What the family wrote in"
      hint={(LANGUAGE_NAMES as Record<string, string>)[language] ?? language}
      aside={
        recent.some((m) => !m.answerable) ? (
          <Badge tone="critical" icon={<Shield size={13} />}>
            Routed to a person
          </Badge>
        ) : undefined
      }
      note="Anything clinical is never answered — it is logged and a navigator calls. The screening is a word list, deliberately dumb and deterministic, so a clinician can read exactly what it catches."
    >
      {recent.length === 0 ? (
        <p className="empty">
          <span style={{ display: "inline-flex", verticalAlign: "-2px", marginRight: 6 }}>
            <Inbox size={13} />
          </span>
          Nothing from this family yet.
        </p>
      ) : (
        <div style={{ display: "grid", gap: 16 }}>
          {recent.map((message) => (
            <div key={message.id}>
              <div className="bubble inbound" lang={message.language}>
                {message.text}
              </div>
              {message.gloss && <div className="gloss">“{message.gloss}”</div>}

              <div className="verdict-line">
                {message.answerable ? (
                  <Badge tone="go" icon={<CheckCircle size={13} />}>
                    Saathi may answer this
                  </Badge>
                ) : (
                  <Badge tone="critical" icon={<Stop size={13} />}>
                    Not answered · {message.reason}
                  </Badge>
                )}
                {message.triggers.map((trigger) => (
                  <Chip key={trigger} tone="critical">
                    “{trigger}”
                  </Chip>
                ))}
                <Chip>
                  {message.origin === "actor" ? (
                    <>
                      <Spark size={11} />
                      written by the caregiver actor
                    </>
                  ) : (
                    "typed by a person"
                  )}
                </Chip>
                <span style={{ fontSize: 11.5, color: "var(--ink-4)", letterSpacing: 0 }}>
                  {fmtStamp(message.received_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
