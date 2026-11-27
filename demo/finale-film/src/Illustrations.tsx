import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, FONT } from "./theme";

const ease = (f: number, a: number, b: number) =>
  interpolate(f, [a, b], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) });

const Title: React.FC<{ kicker: string; line: string; at?: number }> = ({ kicker, line, at = 0 }) => {
  const f = useCurrentFrame();
  const p = ease(f, at, at + 20);
  return (
    <div style={{ position: "absolute", left: 140, top: 110, opacity: p, transform: `translateY(${(1 - p) * 20}px)` }}>
      <div style={{ fontFamily: FONT, fontSize: 26, letterSpacing: 4, textTransform: "uppercase", color: C.sky, fontWeight: 700 }}>{kicker}</div>
      <div style={{ fontFamily: FONT, fontSize: 64, color: C.white, fontWeight: 800, marginTop: 14, maxWidth: 1200, lineHeight: 1.1 }}>{line}</div>
    </div>
  );
};

export const Mark: React.FC<{ size: number; draw?: number }> = ({ size, draw = 1 }) => (
  <svg width={size} height={size} viewBox="0 0 100 100">
    <rect x="4" y="4" width="92" height="92" rx="24" fill={C.blue} opacity={Math.min(1, draw * 1.5)} />
    {/* two paths meeting: the hospital and the home, joined */}
    <path
      d="M24 66 C 34 30, 50 30, 50 50 S 66 70, 76 34"
      fill="none" stroke={C.white} strokeWidth="9" strokeLinecap="round"
      strokeDasharray="140" strokeDashoffset={140 * (1 - draw)}
    />
    <circle cx="24" cy="66" r={7 * draw} fill={C.white} />
    <circle cx="76" cy="34" r={7 * draw} fill={C.white} />
  </svg>
);

export const Logo: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const draw = ease(f, 5, 45);
  const word = spring({ frame: f - 35, fps, config: { damping: 200 } });
  const line = ease(f, 70, 95);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
      <div style={{ transform: `scale(${0.7 + draw * 0.3})` }}><Mark size={220} draw={draw} /></div>
      <div style={{ fontFamily: FONT, fontSize: 92, fontWeight: 800, color: C.white, marginTop: 40, opacity: word, letterSpacing: -1 }}>
        EKYATRA <span style={{ color: C.sky }}>Saathi</span>
      </div>
      <div style={{ fontFamily: FONT, fontSize: 34, color: C.muted, marginTop: 18, opacity: line }}>
        The patient's journey, between hospitals.
      </div>
    </AbsoluteFill>
  );
};

// Approximate positions on a 1920x1080 stage, roughly where these cities sit on India.
const CITY: Record<string, [number, number]> = {
  Mumbai: [760, 700], Delhi: [880, 360], Kolkata: [1290, 600], Chennai: [990, 900],
  Gaya: [1180, 520], Darbhanga: [1230, 450], Ranchi: [1170, 600], Mirzapur: [1060, 500],
  Bhubaneswar: [1210, 720], Madurai: [930, 990], Samastipur: [1215, 475],
};

export const MapIllo: React.FC = () => {
  const f = useCurrentFrame();
  const homes = ["Gaya", "Darbhanga", "Ranchi", "Mirzapur", "Bhubaneswar", "Samastipur"];
  const centres = ["Mumbai", "Delhi", "Kolkata", "Chennai"];
  const km = Math.round(interpolate(f, [60, 200], [0, 1020], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <AbsoluteFill>
      <Title kicker="The problem" line="Care sits in a few cities. Patients don't." />
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        {Array.from({ length: 22 }).map((_, r) =>
          Array.from({ length: 30 }).map((__, c) => (
            <circle key={`${r}-${c}`} cx={560 + c * 34} cy={300 + r * 34} r={2} fill="#1E2C5E" />
          )),
        )}
        {homes.map((h, i) => {
          const [x1, y1] = CITY[h];
          const [x2, y2] = CITY.Mumbai;
          const p = ease(f, 30 + i * 12, 110 + i * 12);
          const mx = (x1 + x2) / 2, my = Math.min(y1, y2) - 160;
          return (
            <g key={h}>
              <path d={`M${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`} fill="none" stroke={C.sky} strokeWidth={3}
                strokeDasharray="1200" strokeDashoffset={1200 * (1 - p)} opacity={0.85} />
              <circle cx={x1} cy={y1} r={9} fill={C.wait} opacity={ease(f, 20 + i * 8, 40 + i * 8)} />
              <text x={x1 + 16} y={y1 + 6} fill={C.white} fontFamily={FONT} fontSize={24} opacity={ease(f, 20 + i * 8, 40 + i * 8)}>{h}</text>
            </g>
          );
        })}
        {centres.map((c, i) => {
          const [x, y] = CITY[c];
          const s = ease(f, 10 + i * 6, 30 + i * 6);
          return (
            <g key={c}>
              <circle cx={x} cy={y} r={22 * s} fill={C.blue} opacity={0.35} />
              <circle cx={x} cy={y} r={12 * s} fill={C.blue} />
              <text x={x - 20} y={y + 50} fill={C.sky} fontFamily={FONT} fontSize={26} fontWeight={700} opacity={s} textAnchor="end">{c}</text>
            </g>
          );
        })}
      </svg>
      <div style={{ position: "absolute", right: 150, bottom: 170, textAlign: "right", fontFamily: FONT, opacity: ease(f, 60, 80) }}>
        <div style={{ fontSize: 120, fontWeight: 800, color: C.white }}>{km.toLocaleString("en-IN")} km</div>
        <div style={{ fontSize: 34, color: C.sky }}>Gaya → Mumbai · nearly two days, each way</div>
      </div>
    </AbsoluteFill>
  );
};

const Box: React.FC<{ x: number; y: number; w: number; h: number; title: string; children?: React.ReactNode; tint: string; o: number }> = ({ x, y, w, h, title, children, tint, o }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, borderRadius: 28, background: "rgba(255,255,255,0.06)", border: `2px solid ${tint}`, padding: 34, opacity: o, transform: `translateY(${(1 - o) * 30}px)`, fontFamily: FONT }}>
    <div style={{ fontSize: 40, fontWeight: 800, color: C.white }}>{title}</div>
    <div style={{ marginTop: 22 }}>{children}</div>
  </div>
);

const Row: React.FC<{ text: string; o: number; color?: string }> = ({ text, o, color = C.white }) => (
  <div style={{ fontSize: 30, color, opacity: o, marginTop: 14, transform: `translateX(${(1 - o) * -20}px)` }}>{text}</div>
);

export const GapIllo: React.FC = () => {
  const f = useCurrentFrame();
  const gap = ease(f, 150, 190);
  return (
    <AbsoluteFill>
      <Title kicker="The problem" line="The hospital knows. The family doesn't." />
      <Box x={150} y={330} w={680} h={520} title="The hospital system" tint={C.blue} o={ease(f, 10, 35)}>
        <Row text="⛔  Doctor on leave — Sunday" o={ease(f, 40, 55)} color="#FCA5A5" />
        <Row text="⚙️  MRI-2 out of service" o={ease(f, 60, 75)} color="#FCA5A5" />
        <Row text="🧪  Report not back yet" o={ease(f, 80, 95)} color="#FCD34D" />
        <Row text="📅  Slot moved to Tuesday" o={ease(f, 100, 115)} color="#FCD34D" />
      </Box>
      <Box x={1090} y={330} w={680} h={520} title="The family, on the train" tint={C.wait} o={ease(f, 20, 45)}>
        <Row text="🚆  Gaya → Mumbai, Thursday" o={ease(f, 50, 65)} />
        <Row text="🏨  Two nights, borrowed money" o={ease(f, 70, 85)} />
        <Row text="📱  No message. No change." o={ease(f, 90, 105)} color={C.muted} />
      </Box>
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        <line x1={840} y1={590} x2={1080} y2={590} stroke={C.stop} strokeWidth={5} strokeDasharray="14 12" opacity={gap} />
        <text x={960} y={560} textAnchor="middle" fill="#FCA5A5" fontFamily={FONT} fontSize={30} fontWeight={700} opacity={gap}>nobody's job</text>
      </svg>
    </AbsoluteFill>
  );
};

const Counter: React.FC<{ x: number; label: string; value: string; sub: string; at: number }> = ({ x, label, value, sub, at }) => {
  const f = useCurrentFrame();
  const o = ease(f, at, at + 20);
  return (
    <div style={{ position: "absolute", left: x, top: 380, width: 500, fontFamily: FONT, opacity: o, transform: `translateY(${(1 - o) * 30}px)` }}>
      <div style={{ fontSize: 28, color: C.sky, textTransform: "uppercase", letterSpacing: 3, fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 96, fontWeight: 800, color: C.white, marginTop: 12 }}>{value}</div>
      <div style={{ fontSize: 30, color: C.muted, marginTop: 8, lineHeight: 1.35 }}>{sub}</div>
    </div>
  );
};

export const CostIllo: React.FC = () => (
  <AbsoluteFill>
    <Title kicker="What it costs a cancer patient" line="A wasted journey is not an inconvenience." />
    <Counter x={150} label="Money" value="₹ borrowed" sub="Fares, nights in a strange city, food — often on loan." at={30} />
    <Counter x={710} label="Time" value="Wages lost" sub="A caregiver off work for days, again and again." at={110} />
    <Counter x={1270} label="Treatment" value="Doses slip" sub="Long treatment is where families drop out." at={200} />
  </AbsoluteFill>
);

const NODES: Array<[string, string]> = [
  ["🏥", "Hospitals"], ["🧪", "Labs & clinics"], ["💊", "Pharmacies"], ["🚆", "Rail & bus"], ["🚕", "Cabs"],
  ["🛏️", "Stays & dharamshalas"], ["🫁", "Home equipment"], ["🚑", "Ambulances"], ["🛡️", "Insurers & schemes"],
];

export const NetworkIllo: React.FC<{ title?: string; kicker?: string }> = ({ title = "One network, the family at the centre.", kicker = "The solution" }) => {
  const f = useCurrentFrame();
  const cx = 960, cy = 610, R = 330;
  return (
    <AbsoluteFill>
      <Title kicker={kicker} line={title} />
      <svg width={1920} height={1080} style={{ position: "absolute" }}>
        {NODES.map((_, i) => {
          const a = (i / NODES.length) * Math.PI * 2 - Math.PI / 2;
          const p = ease(f, 25 + i * 14, 45 + i * 14);
          return <line key={i} x1={cx} y1={cy} x2={cx + Math.cos(a) * R * p} y2={cy + Math.sin(a) * R * 0.78 * p} stroke={C.sky} strokeWidth={2.5} opacity={0.6} />;
        })}
      </svg>
      {NODES.map(([icon, label], i) => {
        const a = (i / NODES.length) * Math.PI * 2 - Math.PI / 2;
        const p = ease(f, 25 + i * 14, 45 + i * 14);
        return (
          <div key={label} style={{ position: "absolute", left: cx + Math.cos(a) * R - 110, top: cy + Math.sin(a) * R * 0.78 - 46, width: 220, textAlign: "center", opacity: p, transform: `scale(${0.7 + 0.3 * p})`, fontFamily: FONT }}>
            <div style={{ fontSize: 46 }}>{icon}</div>
            <div style={{ fontSize: 24, color: C.white, fontWeight: 600, marginTop: 4 }}>{label}</div>
          </div>
        );
      })}
      <div style={{ position: "absolute", left: cx - 120, top: cy - 120, width: 240, height: 240, borderRadius: 120, background: C.blue, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", boxShadow: "0 0 0 18px rgba(37,99,235,0.18)", opacity: ease(f, 0, 20), fontFamily: FONT }}>
        <Mark size={90} />
        <div style={{ color: C.white, fontSize: 30, fontWeight: 800, marginTop: 8 }}>Saathi</div>
        <div style={{ color: C.sky, fontSize: 22, opacity: ease(f, 160, 180) }}>👪 the family</div>
      </div>
    </AbsoluteFill>
  );
};

const Pill: React.FC<{ text: string; o: number; color: string }> = ({ text, o, color }) => (
  <div style={{ display: "inline-block", padding: "16px 28px", borderRadius: 40, background: color, color: C.white, fontFamily: FONT, fontSize: 30, fontWeight: 700, opacity: o, transform: `scale(${0.8 + 0.2 * o})`, margin: 10 }}>{text}</div>
);

export const StandardsIllo: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Title kicker="Plug in the same way" line="Open standards in. Only the trip goes out." />
      <div style={{ position: "absolute", left: 150, top: 380, width: 760 }}>
        <div style={{ fontFamily: FONT, color: C.muted, fontSize: 28, marginBottom: 12 }}>How partners connect</div>
        <Pill text="HL7 FHIR R4 · hospitals" o={ease(f, 20, 35)} color={C.blue} />
        <Pill text="Beckn / ONDC · travel" o={ease(f, 35, 50)} color={C.blue} />
        <Pill text="Partner app · stays, cabs" o={ease(f, 50, 65)} color={C.blue} />
        <Pill text="Payment links · vendors" o={ease(f, 65, 80)} color={C.blue} />
      </div>
      <div style={{ position: "absolute", left: 1010, top: 380, width: 760 }}>
        <div style={{ fontFamily: FONT, color: C.muted, fontSize: 28, marginBottom: 12 }}>What a partner sees</div>
        <Pill text="✓ dates" o={ease(f, 110, 125)} color={C.go} />
        <Pill text="✓ party size" o={ease(f, 120, 135)} color={C.go} />
        <Pill text="✓ first name" o={ease(f, 130, 145)} color={C.go} />
        <Pill text="✗ diagnosis" o={ease(f, 160, 175)} color={C.stop} />
        <Pill text="✗ budget" o={ease(f, 170, 185)} color={C.stop} />
        <Pill text="✗ health record" o={ease(f, 180, 195)} color={C.stop} />
      </div>
    </AbsoluteFill>
  );
};

const AGENTS: Array<[string, string]> = [
  ["Hospital watcher", "reads the hospital's own calendar"], ["Reader", "turns a family's words into dates"],
  ["Planner", "tries every date, keeps the refusals"], ["Readiness", "go, wait, or hold"],
  ["Travel & stay", "finds a room, bargains on a yes"], ["Message guard", "checks every sentence before it goes"],
];

export const AgentsIllo: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Title kicker="Agents, governed by people" line="Agents do the routine. People make the calls." />
      {AGENTS.map(([name, job], i) => {
        const o = ease(f, 20 + i * 22, 40 + i * 22);
        return (
          <div key={name} style={{ position: "absolute", left: 150 + (i % 3) * 540, top: 360 + Math.floor(i / 3) * 190, width: 500, height: 160, borderRadius: 24, background: "rgba(37,99,235,0.18)", border: `2px solid ${C.blue}`, padding: "26px 30px", opacity: o, transform: `translateY(${(1 - o) * 24}px)`, fontFamily: FONT }}>
            <div style={{ fontSize: 34, fontWeight: 800, color: C.white }}>🤖 {name}</div>
            <div style={{ fontSize: 26, color: C.sky, marginTop: 10 }}>{job}</div>
          </div>
        );
      })}
      {[["👤 A navigator agrees with what the family meant", 320], ["👤 A person approves every change to a booking", 400]].map(([t, at], i) => {
        const o = ease(f, at as number, (at as number) + 20);
        return (
          <div key={i} style={{ position: "absolute", left: 150 + i * 820, top: 790, width: 780, padding: "26px 32px", borderRadius: 24, background: "rgba(22,163,74,0.18)", border: `2px solid ${C.go}`, fontFamily: FONT, fontSize: 32, fontWeight: 700, color: C.white, opacity: o, transform: `scale(${0.9 + 0.1 * o})` }}>
            {t}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

export const CloseIllo: React.FC = () => {
  const f = useCurrentFrame();
  const a = ease(f, 10, 35), b = ease(f, 70, 95), c = ease(f, 200, 230);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", fontFamily: FONT, textAlign: "center" }}>
      <div style={{ fontSize: 60, color: C.white, fontWeight: 800, opacity: a }}>The hospital system runs the hospital.</div>
      <div style={{ fontSize: 60, color: C.sky, fontWeight: 800, opacity: b, marginTop: 20 }}>Saathi runs the journey between.</div>
      <div style={{ marginTop: 80, opacity: c, display: "flex", alignItems: "center", gap: 28 }}>
        <Mark size={110} />
        <div style={{ fontSize: 64, fontWeight: 800, color: C.white }}>EKYATRA <span style={{ color: C.sky }}>Saathi</span></div>
      </div>
    </AbsoluteFill>
  );
};

export const ChapterCard: React.FC<{ number: string; title: string }> = ({ number, title }) => {
  const f = useCurrentFrame();
  const a = ease(f, 4, 22), b = ease(f, 12, 32);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", fontFamily: FONT }}>
      <div style={{ fontSize: 34, color: C.sky, fontWeight: 700, letterSpacing: 6, opacity: a, transform: `translateY(${(1 - a) * 16}px)` }}>
        {number.padStart(2, "0")}
      </div>
      <div style={{ width: 120 * b, height: 4, background: C.blue, borderRadius: 2, margin: "26px 0" }} />
      <div style={{ fontSize: 78, color: C.white, fontWeight: 800, opacity: b, transform: `translateY(${(1 - b) * 20}px)` }}>{title}</div>
    </AbsoluteFill>
  );
};
