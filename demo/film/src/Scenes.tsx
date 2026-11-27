import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT } from "./theme";

/**
 * The parts of the film that are drawn rather than recorded.
 *
 * Everything here explains; nothing here claims. A scene may state a fact
 * about the world — how far Darbhanga is from Mumbai, how many comprehensive
 * cancer centres India has — but any claim about what *this system* does is
 * made by a clip of it doing the thing, never by an illustration of it. That
 * division is deliberate: an illustration can show anything, which is exactly
 * why it must not be the evidence.
 *
 * Drawn in plain SVG and CSS. No stock art, no icon set, nothing that needs a
 * licence check before this can be shown to anybody.
 */

/**
 * Fade and lift, the only entrance used anywhere, so cuts feel of a piece.
 *
 * A component rather than a hook, deliberately. As a hook it was being called
 * inside `.map()` callbacks to stagger a list, which breaks the rules of hooks
 * — React throws during render, Remotion reports only "root component failed
 * to load", and the render quietly emits a truncated file with exit code 0.
 * Wrapping is the version that can be used in a loop.
 */
const Rise: React.FC<{
  delay?: number;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ delay = 0, style, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 200 }, durationInFrames: 22 });
  return (
    <div
      style={{
        opacity: s,
        transform: `translateY(${interpolate(s, [0, 1], [14, 0])}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

const Shell: React.FC<{ children: React.ReactNode; dark?: boolean }> = ({ children, dark }) => (
  <AbsoluteFill
    style={{
      backgroundColor: dark ? C.ground : C.paper,
      color: dark ? C.paper : C.ink,
      fontFamily: FONT,
      padding: "90px 120px",
      justifyContent: "center",
    }}
  >
    {children}
  </AbsoluteFill>
);

const Kicker: React.FC<{ children: React.ReactNode; dark?: boolean }> = ({ children, dark }) => (
  <Rise
    style={{
      fontSize: 22,
      letterSpacing: 3,
      textTransform: "uppercase",
      color: dark ? "rgba(247,248,251,.55)" : C.inkSoft,
      marginBottom: 22,
    }}
  >
    {children}
  </Rise>
);

const Head: React.FC<{ children: React.ReactNode; delay?: number }> = ({ children, delay = 6 }) => (
  <Rise delay={delay} style={{ fontSize: 62, lineHeight: 1.12, fontWeight: 650, maxWidth: 1400 }}>
    {children}
  </Rise>
);

/* ─────────────────────────────── the logo ──────────────────────────────── */

export const Logo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const draw = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 40 });
  return (
    <Shell dark>
      <div style={{ display: "flex", alignItems: "center", gap: 34 }}>
        <svg width={118} height={118} viewBox="0 0 100 100">
          {/* Two places and the line between them: the whole product in a mark. */}
          <circle cx="22" cy="72" r="9" fill={C.blue} opacity={draw} />
          <circle cx="78" cy="28" r="9" fill={C.paper} opacity={draw} />
          <path
            d="M22 72 C 40 72, 52 48, 78 28"
            stroke={C.blue}
            strokeWidth={5}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={120}
            strokeDashoffset={interpolate(draw, [0, 1], [120, 0])}
          />
        </svg>
        <div>
          <Rise delay={8} style={{ fontSize: 78, fontWeight: 700, letterSpacing: -1 }}>
            EKYATRA <span style={{ color: C.blue }}>Saathi</span>
          </Rise>
          <Rise delay={16} style={{ fontSize: 27, color: "rgba(247,248,251,.62)", marginTop: 10 }}>
            Care logistics for families who travel a long way to be treated
          </Rise>
        </div>
      </div>
    </Shell>
  );
};

/* ───────────────────────────── the problem ─────────────────────────────── */

export const Distance: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const draw = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 55 });
  return (
    <Shell>
      <Kicker>The distance</Kicker>
      <Head>
        28 comprehensive cancer centres.
        <br />
        1.4 billion people.
      </Head>
      <div style={{ marginTop: 56, position: "relative", height: 260 }}>
        <svg width={1400} height={260}>
          <line x1={90} y1={62} x2={1180} y2={196} stroke={C.line} strokeWidth={2} strokeDasharray="7 7" />
          <line
            x1={90}
            y1={62}
            x2={interpolate(draw, [0, 1], [90, 1180])}
            y2={interpolate(draw, [0, 1], [62, 196])}
            stroke={C.blue}
            strokeWidth={4}
            strokeLinecap="round"
          />
          <circle cx={90} cy={62} r={11} fill={C.ink} />
          <circle cx={1180} cy={196} r={11} fill={C.blue} opacity={draw} />
          <text x={74} y={34} fontSize={26} fontFamily={FONT} fill={C.ink} fontWeight={600}>
            Darbhanga, Bihar
          </text>
          <text x={1066} y={234} fontSize={26} fontFamily={FONT} fill={C.blue} fontWeight={600}>
            Mumbai
          </text>
          <text x={520} y={150} fontSize={34} fontFamily={FONT} fill={C.inkSoft} fontWeight={600}>
            1,867 km
          </text>
        </svg>
      </div>
      <Rise delay={40} style={{ fontSize: 30, color: C.inkSoft, maxWidth: 1180 }}>
        Each way. For treatment that runs two years.
      </Rise>
    </Shell>
  );
};

export const Money: React.FC = () => (
  <Shell>
    <Kicker>The cost</Kicker>
    <Head>The treatment may be free. The getting there is not.</Head>
    <div style={{ display: "flex", gap: 26, marginTop: 58 }}>
      {[
        { big: "₹900", small: "the fare, each way, in her own words" },
        { big: "₹300", small: "a day's earning in the household" },
        { big: "2 yrs", small: "of journeys this has to be found for" },
      ].map((card, i) => (
        <Rise
          key={card.big}
          delay={14 + i * 7}
          style={{
            flex: 1,
            background: "#fff",
            border: `1px solid ${C.line}`,
            borderRadius: 18,
            padding: "34px 32px",
          }}
        >
          <div style={{ fontSize: 60, fontWeight: 700, color: i === 0 ? C.blue : C.ink }}>{card.big}</div>
          <div style={{ fontSize: 23, color: C.inkSoft, marginTop: 12, lineHeight: 1.4 }}>{card.small}</div>
        </Rise>
      ))}
    </div>
  </Shell>
);

export const Wasted: React.FC = () => (
  <Shell dark>
    <Kicker dark>Why people stop coming</Kicker>
    <Head>It is rarely the medicine. It is the wasted journey.</Head>
    <div style={{ marginTop: 54, display: "flex", flexDirection: "column", gap: 18 }}>
      {[
        "Travelled two days. The doctor was away.",
        "Arrived. The report was not back.",
        "Came for one test. Came again for another.",
      ].map((line, i) => (
        <Rise
          key={line}
          delay={10 + i * 9}
          style={{
            fontSize: 33,
            padding: "22px 30px",
            borderLeft: `4px solid ${C.stop}`,
            background: "rgba(255,255,255,.05)",
            borderRadius: "0 14px 14px 0",
          }}
        >
          {line}
        </Rise>
      ))}
    </div>
  </Shell>
);

/** Treatment is a sequence; one slipped link moves everything after it. */
export const Sequence: React.FC = () => {
  const frame = useCurrentFrame();
  const steps = ["Scan", "Report", "Review", "Dose"];
  const slipAt = 38;
  const slip = interpolate(frame, [slipAt, slipAt + 18], [0, 150], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <Shell>
      <Kicker>Why cancer makes it worse</Kicker>
      <Head>Treatment is a sequence. Move one link and everything after it moves.</Head>
      <div style={{ marginTop: 70, display: "flex", alignItems: "center", gap: 20 }}>
        {steps.map((step, i) => (
          <React.Fragment key={step}>
            <div
              style={{
                padding: "26px 40px",
                borderRadius: 16,
                fontSize: 32,
                fontWeight: 600,
                whiteSpace: "nowrap",
                background: i === 0 ? C.warnSoft : "#fff",
                border: `1px solid ${i === 0 ? C.warn : C.line}`,
                color: i === 0 ? C.warn : C.ink,
                transform: `translateX(${i === 0 ? 0 : slip}px)`,
              }}
            >
              {step}
            </div>
            {i < steps.length - 1 && (
              <div style={{ color: C.inkSoft, fontSize: 30, transform: `translateX(${i === 0 ? slip / 2 : slip}px)` }}>
                →
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
      <div style={{ fontSize: 29, color: C.inkSoft, marginTop: 66, maxWidth: 1200 }}>
        And every move is another journey somebody has to pay for.
      </div>
    </Shell>
  );
};

/* ───────────────────────────── the solution ────────────────────────────── */

export const Network: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const nodes = [
    "Hospitals", "Clinics", "Railways", "State buses", "Cabs",
    "Pharmacies", "Equipment", "Dharamshalas", "Labs",
  ];
  return (
    <Shell dark>
      <Kicker dark>What we built</Kicker>
      <Head>The logistics layer nobody owns.</Head>
      <div style={{ marginTop: 56, display: "flex", flexWrap: "wrap", gap: 16, maxWidth: 1500 }}>
        {nodes.map((n, i) => {
          const s = spring({ frame: frame - 10 - i * 4, fps, config: { damping: 200 }, durationInFrames: 18 });
          return (
            <div
              key={n}
              style={{
                padding: "20px 32px",
                borderRadius: 999,
                fontSize: 28,
                border: `1px solid rgba(255,255,255,.22)`,
                background: "rgba(255,255,255,.06)",
                opacity: s,
                transform: `scale(${interpolate(s, [0, 1], [0.92, 1])})`,
              }}
            >
              {n}
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 29, color: "rgba(247,248,251,.66)", marginTop: 54, maxWidth: 1300 }}>
        Registered into one network, so a change in any of them can be planned around.
      </div>
    </Shell>
  );
};

export const Agents: React.FC = () => (
  <Shell>
    <Kicker>Agents, and the people over them</Kicker>
    <Head>Every agent stops at a person.</Head>
    <div style={{ display: "flex", gap: 22, marginTop: 56 }}>
      <Rise delay={12} style={{ flex: 1.3 }}>
        <div style={{ fontSize: 22, letterSpacing: 2, color: C.inkSoft, marginBottom: 16 }}>THE AGENTS DO</div>
        {["Read what the hospital published", "Read what the family wrote back", "Search dates that fit both", "Work out what it would cost"].map((t) => (
          <div key={t} style={{ fontSize: 27, padding: "16px 0", borderBottom: `1px solid ${C.line}` }}>{t}</div>
        ))}
      </Rise>
      <Rise delay={22} style={{ flex: 1 }}>
        <div style={{ fontSize: 22, letterSpacing: 2, color: C.blue, marginBottom: 16 }}>A PERSON DECIDES</div>
        {["Agrees the reading is right", "Approves the date", "A doctor, if it touches treatment"].map((t) => (
          <div
            key={t}
            style={{
              fontSize: 27, padding: "16px 20px", marginBottom: 10,
              background: C.blueSoft, borderRadius: 12, color: C.ink,
            }}
          >
            {t}
          </div>
        ))}
      </Rise>
    </div>
  </Shell>
);

export const MoneyRules: React.FC = () => (
  <Shell>
    <Kicker>How we handle money</Kicker>
    <Head>Every figure says where it came from.</Head>
    <div style={{ marginTop: 50, display: "flex", flexDirection: "column", gap: 14, maxWidth: 1420 }}>
      {[
        ["Rail", "the railway's own distance slabs"],
        ["Bus", "state transport per-kilometre rates"],
        ["Auto, taxi", "the city's gazetted meter tariff"],
        ["A bed", "a band for the kind of place, never a named hotel's price"],
        ["Her fare", "what she told us, kept with the sentence she said it in"],
      ].map(([what, from], i) => (
        <Rise
          key={what}
          delay={10 + i * 6}
          style={{
            display: "flex", gap: 26, alignItems: "baseline",
            padding: "18px 26px", background: i === 4 ? C.goSoft : "#fff",
            border: `1px solid ${i === 4 ? C.go : C.line}`, borderRadius: 14,
          }}
        >
          <div style={{ fontSize: 28, fontWeight: 650, width: 230 }}>{what}</div>
          <div style={{ fontSize: 26, color: i === 4 ? C.go : C.inkSoft }}>{from}</div>
        </Rise>
      ))}
    </div>
  </Shell>
);

export const Closing: React.FC = () => (
  <Shell dark>
    <Head delay={2}>
      A doctor marked themselves away.
      <br />
      Nobody told the family — nobody ever does.
    </Head>
    <Rise delay={20} style={{ fontSize: 33, color: "rgba(247,248,251,.72)", marginTop: 40, maxWidth: 1400, lineHeight: 1.5 }}>
      Minutes later every affected household had been asked, in their own language, and a
      person had agreed a plan around what they answered.
    </Rise>
    <Rise delay={34} style={{ marginTop: 70, fontSize: 30, fontWeight: 650 }}>
      EKYATRA <span style={{ color: C.blue }}>Saathi</span>
    </Rise>
  </Shell>
);

/* ───────────────────── the five that explain the rest ──────────────────── */

/** An interval with a guarantee, not a point prediction somebody can be wrong by. */
export const Readiness: React.FC = () => {
  const frame = useCurrentFrame();
  const grow = interpolate(frame, [14, 46], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <Shell>
      <Kicker>Before it offers a date</Kicker>
      <Head>Will the report actually be back?</Head>
      <div style={{ marginTop: 64 }}>
        <svg width={1420} height={200}>
          <line x1={60} y1={120} x2={1360} y2={120} stroke={C.line} strokeWidth={2} />
          {[0, 2, 4, 6, 8, 10].map((d, i) => (
            <text key={d} x={60 + i * 260} y={166} fontSize={23} fontFamily={FONT} fill={C.inkSoft}>
              day {d}
            </text>
          ))}
          {/* The interval, not a point. Width is the honesty. */}
          <rect
            x={320}
            y={88}
            width={620 * grow}
            height={64}
            rx={10}
            fill={C.blueSoft}
            stroke={C.blue}
            strokeWidth={2}
          />
          <text x={340} y={76} fontSize={25} fontFamily={FONT} fill={C.blue} fontWeight={600} opacity={grow}>
            back between day 3 and day 7, nine times in ten
          </text>
        </svg>
      </div>
      <Rise delay={46} style={{ fontSize: 29, color: C.inkSoft, maxWidth: 1340, marginTop: 24 }}>
        Being wrong by two days costs a 500 km round trip. So the planner will not plan behind a
        result it cannot promise.
      </Rise>
    </Shell>
  );
};

/** What is checked before anything reaches a family. */
export const Guard: React.FC = () => (
  <Shell dark>
    <Kicker dark>Before anything is sent</Kicker>
    <Head>A message that cannot be checked is not sent.</Head>
    <div style={{ marginTop: 50, display: "flex", flexDirection: "column", gap: 14, maxWidth: 1420 }}>
      {[
        "No clinical language",
        "No reassurance it has no business giving",
        "No date it was not handed",
        "A date it can read, in any of five scripts",
      ].map((rule, i) => (
        <Rise
          key={rule}
          delay={10 + i * 7}
          style={{
            fontSize: 31,
            padding: "20px 28px",
            background: "rgba(255,255,255,.06)",
            border: "1px solid rgba(255,255,255,.18)",
            borderRadius: 14,
          }}
        >
          {rule}
        </Rise>
      ))}
    </div>
    <Rise delay={44} style={{ fontSize: 28, color: "rgba(247,248,251,.7)", marginTop: 40 }}>
      And if it cannot read the date it is about to send — it gives the message to a person.
    </Rise>
  </Shell>
);

/** Who may decide what, enforced rather than displayed. */
export const Roles: React.FC = () => (
  <Shell>
    <Kicker>Who may decide what</Kicker>
    <Head>Enforced on the server, not shown in the interface.</Head>
    <div style={{ display: "flex", gap: 20, marginTop: 56 }}>
      {[
        { who: "A desk", can: "Report an outage. Confirm a record.", tone: C.line },
        { who: "A navigator", can: "Approve a re-plan.", tone: C.blue },
        { who: "A doctor", can: "Approve one that touches treatment or a dose date.", tone: C.go },
      ].map((r, i) => (
        <Rise
          key={r.who}
          delay={12 + i * 8}
          style={{
            flex: 1,
            padding: "30px 28px",
            background: "#fff",
            border: `2px solid ${r.tone}`,
            borderRadius: 18,
          }}
        >
          <div style={{ fontSize: 34, fontWeight: 650, marginBottom: 14 }}>{r.who}</div>
          <div style={{ fontSize: 25, color: C.inkSoft, lineHeight: 1.45 }}>{r.can}</div>
        </Rise>
      ))}
    </div>
    <Rise delay={40} style={{ fontSize: 28, color: C.inkSoft, marginTop: 46 }}>
      Typing the word “doctor” into a form changes nothing.
    </Rise>
  </Shell>
);

/** The limits, written down rather than hidden. */
export const Limits: React.FC = () => (
  <Shell dark>
    <Kicker dark>What it will not do</Kicker>
    <Head>Four things, said out loud.</Head>
    <div style={{ marginTop: 48, display: "flex", flexDirection: "column", gap: 13, maxWidth: 1480 }}>
      {[
        ["No train timetable", "it names the stations and hands you to IRCTC"],
        ["No arrival clock, hosted", "it says a family arrived and claims no delay"],
        ["A deleted appointment", "it sees one cancelled, but not one deleted"],
        ["Two families, one slot", "it has no answer for that yet"],
      ].map(([what, instead], i) => (
        <Rise
          key={what}
          delay={10 + i * 7}
          style={{
            display: "flex",
            gap: 24,
            alignItems: "baseline",
            padding: "18px 26px",
            background: "rgba(255,255,255,.05)",
            borderLeft: `4px solid ${C.warn}`,
            borderRadius: "0 12px 12px 0",
          }}
        >
          <div style={{ fontSize: 28, fontWeight: 650, width: 400 }}>{what}</div>
          <div style={{ fontSize: 26, color: "rgba(247,248,251,.72)" }}>{instead}</div>
        </Rise>
      ))}
    </div>
  </Shell>
);

/** The ledger: nothing deleted, refusals included. */
export const Ledger: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const blocks = ["read", "refused", "asked", "agreed", "approved", "wrote"];
  return (
    <Shell>
      <Kicker>And all of it is written down</Kicker>
      <Head>A hash-chained record, refusals included.</Head>
      <div style={{ marginTop: 62, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        {blocks.map((b, i) => {
          const s = spring({ frame: frame - 12 - i * 6, fps, config: { damping: 200 }, durationInFrames: 16 });
          return (
            <React.Fragment key={b}>
              <div
                style={{
                  padding: "20px 26px",
                  borderRadius: 12,
                  fontSize: 26,
                  fontFamily: "ui-monospace, monospace",
                  background: b === "refused" ? C.warnSoft : "#fff",
                  border: `1px solid ${b === "refused" ? C.warn : C.line}`,
                  color: b === "refused" ? C.warn : C.ink,
                  opacity: s,
                }}
              >
                {b}
              </div>
              {i < blocks.length - 1 && (
                <div style={{ color: C.inkSoft, fontSize: 24, opacity: s }}>⛓</div>
              )}
            </React.Fragment>
          );
        })}
      </div>
      <Rise delay={54} style={{ fontSize: 29, color: C.inkSoft, marginTop: 56, maxWidth: 1360 }}>
        A record that only holds the times a system was right is not a record anybody should trust.
      </Rise>
    </Shell>
  );
};

/* ───────────────────── what is not built yet, said so ─────────────────── */

/**
 * The badge every roadmap scene wears.
 *
 * Thirty-two clips of working software come before these, and the only thing
 * separating them is that somebody says so. A sentence of narration is not
 * enough: a frame screenshotted out of context, or a viewer who joined late,
 * must still be able to tell intention from evidence. So it is on the screen
 * the whole time, in a colour nothing else in the film uses.
 */
const NotBuilt: React.FC = () => (
  <div
    style={{
      position: "absolute",
      top: 44,
      right: 56,
      padding: "11px 22px",
      borderRadius: 999,
      background: C.warn,
      color: "#fff",
      fontFamily: FONT,
      fontSize: 20,
      fontWeight: 650,
      letterSpacing: 2,
    }}
  >
    NEXT · NOT BUILT
  </div>
);

/** The line between what works and what is only intended. */
export const NextDivider: React.FC = () => (
  <Shell dark>
    <Rise style={{ fontSize: 24, letterSpacing: 3, color: C.warn, marginBottom: 26 }}>
      EVERYTHING BEFORE THIS IS RUNNING SOFTWARE
    </Rise>
    <Head>Two things we have not built yet.</Head>
    <Rise
      delay={18}
      style={{ fontSize: 32, color: "rgba(247,248,251,.72)", marginTop: 36, maxWidth: 1400, lineHeight: 1.5 }}
    >
      They are where this goes next, and nothing in the next ninety seconds exists today.
    </Rise>
  </Shell>
);

/** Slide 7: the molecular profile. */
export const MolecularNext: React.FC = () => (
  <Shell>
    <NotBuilt />
    <Kicker>Next</Kicker>
    <Head delay={4}>A longitudinal molecular profile</Head>
    <Rise delay={12} style={{ fontSize: 27, color: C.inkSoft, marginTop: 16, maxWidth: 1500 }}>
      Built only from tests the doctor has already ordered.{" "}
      <strong style={{ color: C.go }}>
        Saathi never suggests a test and never interprets one.
      </strong>
    </Rise>

    <div style={{ display: "flex", gap: 20, marginTop: 40 }}>
      {[
        {
          step: "1 · CAPTURE",
          head: "Every molecular report, in one place",
          bullets: [
            "Karyotyping, genome or exome sequencing, transcriptomic and proteomic panels",
            "Pulled from the lab over FHIR Genomics, with consent",
            "Linked to the patient's ABHA ID",
          ],
          tone: C.blue,
          ground: "#fff",
        },
        {
          step: "2 · KEEP",
          head: "A molecular timeline across the disease",
          bullets: [
            "Germline predispositions and tumour alterations over time",
            "Helps treating doctors with biomarker interpretation and molecular monitoring",
            "Moves with the patient between centres",
          ],
          tone: C.blue,
          ground: "#fff",
        },
        {
          step: "3 · SHARE · OPT-IN ONLY",
          head: "Contribute to cancer research",
          bullets: [
            "A separate consent from the patient and family, managed in Saathi",
            "De-identified data to research repositories such as NCI's GDC, home of TCGA",
            "Withdraw at any time",
          ],
          tone: C.go,
          ground: C.goSoft,
        },
      ].map((col, i) => (
        <Rise
          key={col.step}
          delay={18 + i * 8}
          style={{
            flex: 1,
            background: col.ground,
            borderLeft: `4px solid ${col.tone}`,
            borderRadius: "0 14px 14px 0",
            padding: "26px 26px 30px",
          }}
        >
          <div style={{ fontSize: 18, letterSpacing: 1.6, color: C.inkSoft, marginBottom: 12 }}>
            {col.step}
          </div>
          <div style={{ fontSize: 30, fontWeight: 650, color: col.tone, lineHeight: 1.2, marginBottom: 18 }}>
            {col.head}
          </div>
          {col.bullets.map((b) => (
            <div key={b} style={{ fontSize: 21, color: C.ink, lineHeight: 1.45, marginBottom: 11 }}>
              • {b}
            </div>
          ))}
        </Rise>
      ))}
    </div>

    <div style={{ display: "flex", gap: 12, marginTop: 34, flexWrap: "wrap" }}>
      {[
        ["Separate consent per purpose", C.blue],
        ["Encrypted store, doctor-only access", C.blue],
        ["DPDP Act 2023 · ICMR ethics guidelines", C.blue],
        ["Outside the treatment pipeline", C.go],
      ].map(([chip, tone], i) => (
        <Rise
          key={chip as string}
          delay={44 + i * 5}
          style={{
            padding: "12px 20px",
            borderRadius: 999,
            fontSize: 20,
            fontWeight: 600,
            color: tone as string,
            background: tone === C.go ? C.goSoft : C.blueSoft,
          }}
        >
          {chip}
        </Rise>
      ))}
    </div>
  </Shell>
);

/** Slide 8: the vendor login and the partner network. */
export const PartnerNext: React.FC = () => (
  <Shell>
    <NotBuilt />
    <Kicker>Next</Kicker>
    <Head delay={4}>A vendor login and partner network</Head>
    <Rise delay={12} style={{ fontSize: 27, color: C.inkSoft, marginTop: 16, maxWidth: 1500 }}>
      Today a cab firm or a hotel sees only its own jobs.{" "}
      <strong style={{ color: C.go }}>
        Next, any service a journey needs joins one verified network.
      </strong>
    </Rise>

    <div style={{ display: "flex", gap: 30, marginTop: 38 }}>
      <Rise
        delay={18}
        style={{
          flex: 1.05,
          background: "#fff",
          borderLeft: `4px solid ${C.blue}`,
          borderRadius: "0 14px 14px 0",
          padding: "26px 28px 30px",
        }}
      >
        <div style={{ fontSize: 18, letterSpacing: 1.6, color: C.inkSoft, marginBottom: 12 }}>
          VENDOR LOGIN
        </div>
        <div style={{ fontSize: 31, fontWeight: 650, color: C.blue, marginBottom: 18 }}>
          One screen per partner
        </div>
        {[
          "Self-onboarding with GST and licence checks",
          "Accept, decline and update jobs in real time",
          "Set prices and patient-family rates",
          "Payouts, invoices and an SLA dashboard",
          "Sees a first name, district and day; a phone number only if the family agrees",
        ].map((b) => (
          <div key={b} style={{ fontSize: 21, color: C.ink, lineHeight: 1.45, marginBottom: 11 }}>
            • {b}
          </div>
        ))}
      </Rise>

      <div style={{ flex: 1 }}>
        <Rise delay={24} style={{ fontSize: 18, letterSpacing: 1.6, color: C.inkSoft, marginBottom: 14 }}>
          PARTNER NETWORK · SERVICE CATEGORIES
        </Rise>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 11 }}>
          {[
            "Labs and sample pickup", "Pharmacies and distributors",
            "Stays and dharamshalas", "Cabs and ambulances",
            "Home care and nursing", "NGO and scheme help desks",
            "Insurers and TPAs",
          ].map((cat, i) => (
            <Rise
              key={cat}
              delay={28 + i * 4}
              style={{
                padding: "14px 20px",
                borderRadius: 10,
                fontSize: 21,
                fontWeight: 600,
                color: C.blue,
                background: C.blueSoft,
              }}
            >
              {cat}
            </Rise>
          ))}
        </div>
        <Rise delay={58} style={{ fontSize: 20, color: C.inkSoft, marginTop: 18, lineHeight: 1.5 }}>
          Partners plug in through the vendor app or their own MCP server. Agents route each job
          by price band, distance, accessibility and SLA history.
        </Rise>
      </div>
    </div>

    <div style={{ display: "flex", gap: 40, marginTop: 34, borderTop: `1px solid ${C.line}`, paddingTop: 26 }}>
      {[
        ["More options", "the budget agent finds cheaper, closer services"],
        ["Quality loop", "ratings and missed SLAs feed the ranking"],
        ["Revenue", "capped commission, never added to the family's price"],
      ].map(([head, sub], i) => (
        <Rise key={head} delay={62 + i * 6} style={{ flex: 1 }}>
          <div style={{ fontSize: 27, fontWeight: 650, color: C.go, marginBottom: 7 }}>{head}</div>
          <div style={{ fontSize: 21, color: C.inkSoft, lineHeight: 1.4 }}>{sub}</div>
        </Rise>
      ))}
    </div>
  </Shell>
);

/* ─────────────────── and then they were built, said so ────────────────── */

/**
 * The counterpart to `NotBuilt`.
 *
 * The roadmap slides are deliberately unmistakable, and that cuts both ways:
 * having spent seventy seconds insisting two things do not exist, a later
 * reel claiming they do has to be at least as clear, or it reads as the same
 * pitch with the caveat quietly dropped. Green rather than amber, and the
 * word that matters is "running".
 */
const NowBuilt: React.FC = () => (
  <div
    style={{
      position: "absolute",
      top: 44,
      right: 56,
      padding: "11px 22px",
      borderRadius: 999,
      background: C.go,
      color: "#fff",
      fontFamily: FONT,
      fontSize: 20,
      fontWeight: 650,
      letterSpacing: 2,
    }}
  >
    BUILT · RUNNING
  </div>
);

/** Opens the addendum: the two slides, revisited. */
export const BuiltDivider: React.FC = () => (
  <Shell dark>
    <Rise style={{ fontSize: 24, letterSpacing: 3, color: C.go, marginBottom: 26 }}>
      AN ADDENDUM TO THE TWO SLIDES AT THE END
    </Rise>
    <Head>Both of them now exist.</Head>
    <Rise
      delay={18}
      style={{ fontSize: 32, color: "rgba(247,248,251,.72)", marginTop: 36, maxWidth: 1460, lineHeight: 1.5 }}
    >
      Narrower than the slides promised, and every frame after this one is the
      deployed system doing it.
    </Rise>
  </Shell>
);

/**
 * What is still missing.
 *
 * Placed before the closing card rather than after it, because a limitation
 * read out over the credits is a limitation nobody hears. The slide it
 * answers made five claims; three of them are still only claims, and saying
 * which is the only thing that makes the other two believable.
 */
export const BuiltLimits: React.FC = () => (
  <Shell>
    <NowBuilt />
    <Kicker>Still not built</Kicker>
    <Head delay={4}>What the slides promised that this does not do</Head>
    <div style={{ display: "flex", gap: 20, marginTop: 44 }}>
      {[
        {
          head: "No genomics feed",
          body:
            "OpenEMR exposes no genomics resource — MolecularSequence is a 404, " +
            "measured, not assumed. The register records that a test happened, " +
            "never a variant, and there is no timeline of alterations.",
        },
        {
          head: "No research contribution",
          body:
            "Nothing is contributed to a genomic data commons. The separate " +
            "consent purpose exists and is revocable; what it governs is a list " +
            "of tests, not findings.",
        },
        {
          head: "Licences read, not verified",
          body:
            "A reviewer reads what an applicant typed and decides. Nothing is " +
            "checked against a licensing register, and the screen says so rather " +
            "than implying a check happened.",
        },
      ].map((card, i) => (
        <Rise
          key={card.head}
          delay={14 + i * 7}
          style={{
            flex: 1,
            background: "#fff",
            borderLeft: `4px solid ${C.warn}`,
            borderRadius: 14,
            padding: "26px 28px",
          }}
        >
          <div style={{ fontSize: 27, fontWeight: 650, color: C.ink, marginBottom: 14 }}>
            {card.head}
          </div>
          <div style={{ fontSize: 22, color: C.inkSoft, lineHeight: 1.5 }}>{card.body}</div>
        </Rise>
      ))}
    </div>
    <Rise delay={40} style={{ fontSize: 24, color: C.inkSoft, marginTop: 40, maxWidth: 1560, lineHeight: 1.5 }}>
      Two more, for completeness. The vendor's own signed-in screens — its
      rates, its standing, its earnings — are built and tested but are not in
      this reel: the hosted demo runs with login off, and a vendor is
      identified by the account it signs in with. And the register is held in
      memory, so every deployment empties it.
    </Rise>
  </Shell>
);

/** The close. */
export const BuiltClose: React.FC = () => (
  <Shell dark>
    <NowBuilt />
    <Rise style={{ fontSize: 24, letterSpacing: 3, color: C.go, marginBottom: 26 }}>
      RECORDED ON THE DEPLOYED STACK
    </Rise>
    <Head>Three bugs found by pointing a camera at it.</Head>
    <Rise
      delay={18}
      style={{ fontSize: 28, color: "rgba(247,248,251,.72)", marginTop: 36, maxWidth: 1500, lineHeight: 1.55 }}
    >
      A directory that showed an approval as though it had failed. A status
      chip that called an approved vendor an applicant. And a refusal that
      said “422” instead of naming the word it objected to — on the one screen
      whose whole purpose is to name it. All three fixed before this was cut.
    </Rise>
  </Shell>
);
