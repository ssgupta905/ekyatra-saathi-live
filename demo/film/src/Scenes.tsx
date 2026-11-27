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
