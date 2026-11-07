/**
 * The submission walkthrough.
 *
 * The brief asks for something the end-to-end film is not: an introduction to
 * the team, how the problem was approached, the collaboration with the
 * technology and doctor partners — and explicitly "not merely a screen
 * recording".
 *
 * So this is not a re-cut of the raw clips. The product sections are lifted
 * straight out of `EKYATRA-Saathi-end-to-end.mp4`, which already carries
 * composited footage, its own narration and the phone's Hindi read-aloud, and
 * the new material is built around it. A `film` segment keeps the source
 * audio; a `card` segment is narrated here.
 *
 * Timecodes below are positions in that film, read off its own plan rather
 * than guessed.
 */

export const CANVAS = { w: 1920, h: 1080, fps: 30 };
export const INK = "#0b1220";

/** The finished end-to-end film, which this one quotes from. */
export const FILM =
  process.env.SAATHI_SOURCE_FILM ??
  `${process.env.HOME}/Documents/EKYATRA-Saathi-end-to-end.mp4`;

export const PLAN = [
  {
    id: "w01-title", kind: "card", seconds: 6,
    card: { heading: "EKYATRA Saathi", sub: "An orchestration layer for any care pathway that makes a patient travel", kicker: "Team Bits2026 · 86W1QA · Health-a-thon 2026" },
    vo: "EKYATRA Saathi. From team Bits2026.",
  },

  // ── what it actually is, before anything else ─────────────────────────────
  {
    id: "w02-whatitis", kind: "turn", seconds: 30,
    card: {
      heading: "What this is",
      before: "A hospital system.\nFor cancer.",
      after: "An orchestration\nlayer. For any\ncare pathway.",
      note: "Saathi stores no clinical record and replaces nothing. A care pathway is declared as a graph of steps and the dependencies between them — three ship today: oncology, maintenance dialysis, and recovery after discharge. The decision core never knows which one it is working on.",
    },
    vo: "First, two things this is not. It is not a hospital management system. It stores no clinical record and replaces nothing. And it is not only for cancer. Saathi is an orchestration layer. A care pathway is declared as a graph — the steps, and what each one waits on. Three ship today. Oncology. Maintenance dialysis. And recovery after discharge. The decision core never knows which one it is working on. Adding a condition is a declaration, not a rewrite.",
  },
  {
    id: "w03-problem", kind: "card", seconds: 39,
    card: {
      heading: "Why that layer is missing",
      sub: "Every department optimises its own queue. Nobody counts the patient's trips.",
      kicker: "The evidence is strongest in oncology, so the numbers here are oncology's: 60% of Tata Memorial's patients come from outside Maharashtra · 75%+ travel over 500 km · 83% face catastrophic non-medical costs, mean ₹88,433 · 53% borrow or sell assets. A dialysis patient makes the same journey three times a week.",
    },
    vo: "Here is the gap it fills. Every department optimises its own queue. The lab, the scheme desk, the pharmacy, the cab firm. Nobody counts the patient's trips. So a family travels six hundred kilometres, and the report is not back. The published evidence is strongest in cancer care, so these numbers are cancer's. Eighty-three per cent of those households hit catastrophic non-medical costs. More than half borrow or sell something. But a dialysis patient makes that journey three times a week, and somebody recovering from surgery makes it not knowing whether the wound clinic can see them.",
  },

  // ── the architecture, before any screen ───────────────────────────────────
  {
    id: "w04-arch", kind: "arch", seconds: 49,
    card: {
      heading: "Where it sits",
      sub: "Read status · decide · tell everyone who needs to know. No clinical write, anywhere.",
      above: [
        ["HMS / LIS", "appointments and report status — read only"],
        ["ABDM", "linked status under India's own consent model"],
        ["Pathways & directory", "the care pathway as a declared graph — oncology, dialysis, post-discharge — and the vendors already in use"],
      ],
      core: {
        title: "EKYATRA Saathi · the orchestration layer",
        detail: "Pathway-agnostic and stateless per family. No diagnosis, no result, no report content — there is no field that could hold one.",
        steps: ["dependency graph", "conformal readiness forecast", "ask every party", "verdict", "render into the family's language", "hash-chained ledger"],
      },
      below: [
        ["Navigator's console", "every journey against every party holding it up"],
        ["The family's phone", "one word, one date, in their language"],
        ["Vendor screens", "one job each, and nothing about anybody's care"],
      ],
    },
    vo: "This is where it sits. Above the line, what the hospital already runs — its own system for appointments and report status, A B D M for linked status under India's consent model, the care pathways themselves, and the directory of labs, cabs, hotels and scheme desks it already uses. Saathi reads from those. It never writes anything clinical. In the middle it resolves the care pathway as a dependency graph, forecasts when each pending step will be ready, asks every party the journey leans on, and reaches a verdict. Below the line, three audiences. The navigator sees every journey against whatever is holding it up. The family sees one word and one date, in their own language. And each vendor sees one job, and nothing about anybody's care.",
  },
  {
    id: "w05-tech", kind: "stack", seconds: 38,
    card: {
      heading: "What it is built from",
      rows: [
        ["The decision — no model", "Dependency-graph resolution · split conformal prediction for readiness, with a stated coverage level · PELT change-point detection for drop-off · a hash-chained ledger"],
        ["Agentic AI", "A language model puts a decided plan into the family's language — and simulated counterparties stand in for vendors in the demo. Neither ever makes the decision."],
        ["Sarvam AI", "bulbul:v3 and saarika:v2.5 — Hindi, Bengali, Odia, English. Chosen because almost no phone ships an Odia voice."],
        ["Platform", "FastAPI · PostgreSQL · React · Kotlin/Compose · server-sent events · 631 credential-free tests"],
      ],
    },
    vo: "What it is built from. The decision itself uses no model at all — a dependency graph, split conformal prediction for the readiness forecast with a stated coverage level, change-point detection for drop-off, and a hash-chained ledger. The A I layer puts a decided plan into the family's words, and only that. Sarvam gives us speech in four languages, chosen because almost no phone ships an Odia voice. Underneath: FastAPI, Postgres, React, Kotlin, and six hundred and thirty-one tests that run with no credentials at all.",
  },

  // ── who built it, and with whom ───────────────────────────────────────────
  {
    id: "w06-team", kind: "people", seconds: 19,
    card: {
      heading: "Who built it",
      sub: "Bits2026",
      people: [
        ["Siddhartha Sengupta", "Technical Architect", "The decision core and its invariants"],
        ["Ankshuk Ray", "Full-stack & AI engineer", "Web, Android, language and speech"],
        ["Abhik Sengupta", "PhD scholar, biological sciences", "Evidence review"],
        ["Srinivas Pavan", "Delivery Manager", "Four-week sprint and scope"],
      ],
    },
    vo: "Four of us built it. Siddhartha Sengupta, technical architect, on the decision core. Ankshuk Ray on the two web products, the Android app and the speech layer. Abhik Sengupta, a PhD scholar in the biological sciences, on the evidence. And Srinivas Pavan on delivery and scope.",
  },
  {
    id: "w07-doctor", kind: "card", seconds: 29,
    card: {
      heading: "Dr Arani Chakraborty",
      sub: "MBBS · Reg. 93698 · our doctor partner",
      kicker: "Neurology, Manipal Hospital EM Bypass · formerly Neurosurgery, AIIMS Kalyani — he mapped where a patient's evaluation and follow-up actually breaks, which is why a journey is modelled as a chain with a blocking step rather than a calendar",
    },
    vo: "Our doctor partner is Doctor Arani Chakraborty. Neurology at Manipal Hospital, formerly neurosurgery at A I I M S Kalyani. He mapped the sequence a patient really moves through, and told us where it breaks — the points at which someone is sent away and does not come back. That is why a journey here is a chain with one thing blocking it, and not a calendar. To be precise: this is clinical process review, not a clinical trial.",
  },

  // ── the working solution, quoted from the film ────────────────────────────
  { id: "w07-chapter", kind: "card", seconds: 5,
    card: { chapter: "The product, running", heading: "Five things it does" },
    vo: "So here it is, running. Five things to watch for." },

  //: 02:49–03:56 — three families loaded, the network board, Meena Wait→Go.
  //: 170–236 · starts as the narration starts, ends inside the 226–237 gap
  { id: "w08-board", kind: "film", in: 167.5, seconds: 68.5, vo: "" },
  //: 03:56–04:45 — Ravi's vendor fails and a navigator picks the next one.
  //: 237–285.5 · inside the 274–286 gap, rather than clipping its first syllable
  { id: "w09-fails", kind: "film", in: 237, seconds: 48.5, vo: "" },
  //: 05:00–05:39 — the lab releases the report and the chain fills in.
  //: 301–339 · inside the 331–340 gap
  { id: "w10-release", kind: "film", in: 301, seconds: 38, vo: "" },
  //: 06:01–06:22 — the cab firm's own screen.
  //: 362–383 · inside the 380–386 gap
  { id: "w11-partner", kind: "film", in: 359.5, seconds: 23.5, vo: "" },
  //: 07:28–08:35 — affordability: the budget conversation, end to end.
  //: 450.5–516 · trims a dead lead-in, ends inside the 508–519 gap
  { id: "w12-afford", kind: "film", in: 450.5, seconds: 65.5, vo: "" },
  //: 08:35–09:10 — the Hindi read-aloud, in the family's own voice.
  //: 517.5–558.5 · was cut mid-sentence at 551; the Sarvam passage runs to 558.2
  { id: "w13-voice", kind: "film", in: 517.5, seconds: 42, vo: "" },
  //: 10:15–10:50 — Wait becomes Come while nobody touches the phone.
  //: 617.5–649 · was cut mid-Hindi at 652; the gap is 641.4–649.4
  { id: "w14-flip", kind: "film", in: 617.5, seconds: 31.5, vo: "" },

  // ── what it does about the problem ────────────────────────────────────────
  {
    id: "w15-result", kind: "stack", seconds: 36,
    card: {
      heading: "Does it address the problem?",
      rows: [
        ["30 of 50", "wasted journeys under the hospital's default policy, scored against planted ground truth on synthetic families"],
        ["0 of 50", "with Saathi"],
        ["₹2,55,000", "non-medical cost avoided, at the published ₹8,500 per journey"],
        ["No patient data", "has been used anywhere. This is the measurement a pilot replaces."],
      ],
    },
    vo: "Does it work? We scored it against planted ground truth. Fifty synthetic families. We generate the true date each report actually lands. Then we ask a simple question. Would the family have travelled for nothing? The hospital's default policy produces thirty wasted journeys out of fifty. Saathi produces none. At the published figure — eight and a half thousand rupees a journey — that is two and a half lakh avoided. These are synthetic families. No real patient data has been used anywhere. Replacing this number with a real one is exactly what the pilot is for.",
  },
  {
    id: "w16-close", kind: "card", seconds: 15,
    card: {
      heading: "Thank you",
      sub: "Bits2026 · 86W1QA",
      kicker: "The model never decides whether a family travels · report content never enters the system · every decision is in a hash-chained log",
    },
    vo: "Three rules hold all of this up. The model never decides whether a family travels. No report content ever enters the system. And every decision sits in a log that cannot be quietly edited. Thank you for watching.",
  },
];

export const TOTAL = PLAN.reduce((n, s) => n + s.seconds, 0);
