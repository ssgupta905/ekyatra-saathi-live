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
    id: "w01-title", kind: "card", seconds: 11,
    card: { heading: "EKYATRA Saathi", sub: "Demo walkthrough", kicker: "Team Bits2026 · 86W1QA · Health-a-thon 2026" },
    vo: "EKYATRA Saathi, from team Bits2026. This is a walkthrough of what we built, who built it, and how it works.",
  },

  // ── the problem ───────────────────────────────────────────────────────────
  {
    id: "w02-problem", kind: "card", seconds: 27,
    card: {
      heading: "The problem",
      sub: "A journey that costs more than the care",
      kicker: "60% of Tata Memorial's patients come from outside Maharashtra · 75%+ travel over 500 km · 83% face catastrophic non-medical costs, mean ₹88,433 · 53% borrow or sell assets to cope",
    },
    vo: "Sixty per cent of the patients at India's largest cancer hospital come from outside the state. Most travel over five hundred kilometres. They arrive, and the report is not back — so they go home, and they come again. Eighty-three per cent of those families hit catastrophic non-medical costs, and more than half borrow or sell something to cope. The care is often free. The journey is what ruins them.",
  },

  // ── the team ──────────────────────────────────────────────────────────────
  {
    id: "w03-team", kind: "people", seconds: 36,
    card: {
      heading: "The team",
      sub: "Bits2026",
      people: [
        ["Siddhartha Sengupta", "Technical Architect", "The decision core, and the rules the system is not allowed to break"],
        ["Ankshuk Ray", "Full-stack & AI engineer", "Two web products, the Android app, the language and speech layer"],
        ["Abhik Sengupta", "PhD scholar, biological sciences", "Evidence review and the published cost-of-care data"],
        ["Srinivas Pavan", "Delivery Manager", "Four weeks of sprint planning, and the scope calls that kept it shippable"],
      ],
    },
    vo: "Four of us built it. Siddhartha Sengupta, our technical architect, designed the decision core and the rules the system is not allowed to break. Ankshuk Ray, a full stack and AI engineer, built the two web products, the Android app, and the language and speech layer. Abhik Sengupta, a PhD scholar in the biological sciences, did the evidence review this is built against. And Srinivas Pavan managed delivery across the four weeks, and made the scope calls that kept it shippable.",
  },
  {
    id: "w04-doctor", kind: "card", seconds: 38,
    card: {
      heading: "Dr Arani Chakraborty",
      sub: "MBBS · Reg. 93698 · our doctor partner",
      kicker: "Formerly Resident, Department of Neurosurgery, AIIMS Kalyani. Presently attached to the Department of Neurology, Manipal Hospital, EM Bypass.",
    },
    vo: "Our doctor partner is Doctor Arani Chakraborty — M B B S, formerly a resident in neurosurgery at A I I M S Kalyani, now with the department of neurology at Manipal Hospital, E M Bypass. He mapped the sequence a patient actually moves through: presentation, evaluation, the wait for a result, and follow-up. And he told us where that sequence breaks — the points at which a patient is sent away and does not come back. We should be precise about the limits of that. It is clinical process review, not a clinical trial.",
  },

  // ── how we approached it ──────────────────────────────────────────────────
  {
    id: "w05-approach", kind: "turn", seconds: 31,
    card: {
      heading: "How we approached it",
      before: "Remind the family\ntheir appointment\nis coming",
      after: "Tell them whether\nto come at all",
      note: "Dr Chakraborty's review turned a reminder into a readiness decision — and a journey into a dependency chain with a blocking step, rather than a calendar of appointments.",
    },
    vo: "We did not start here. The idea we submitted was a reminder app: tell the family their appointment is coming. Within the first week it was clear the useful question is the opposite one — should they come at all — and we rebuilt the system around a readiness verdict. The second change came from the clinical review. A journey is not a calendar of appointments. It is a chain, with one thing blocking it, and the honest answer is to withhold the date until that chain clears.",
  },
  {
    id: "w06-partners", kind: "stack", seconds: 35,
    card: {
      heading: "Technology partners",
      rows: [
        ["Groq", "gpt-oss-20b renders a decided plan into the family's language. It never makes the decision."],
        ["Sarvam AI", "bulbul:v3 and saarika:v2.5 — speech in Hindi, Bengali, Odia and English. Chosen because almost no phone ships an Odia voice."],
        ["ABDM", "Appointment and report status under India's own consent model. Status only — never report content."],
      ],
    },
    vo: "Three technology partners. Groq runs the language model that puts a decision into the family's own words — and only that; it never decides anything. Sarvam gives us speech in Hindi, Bengali, Odia and English, and we chose it for a concrete reason: almost no phone ships an Odia voice, so read-aloud used to do nothing at all, silently, for an Odia family. And A B D M is how status reaches us, under India's own consent model — status only, never the contents of a report.",
  },

  // ── the working solution, quoted from the film ────────────────────────────
  { id: "w07-chapter", kind: "card", seconds: 4,
    card: { chapter: "Now", heading: "The working solution" }, vo: "" },

  //: 02:49–03:56 — three families loaded, the network board, Meena Wait→Go.
  { id: "w08-board", kind: "film", in: 170, seconds: 66, vo: "" },
  //: 03:56–04:45 — Ravi's vendor fails and a navigator picks the next one.
  { id: "w09-fails", kind: "film", in: 237, seconds: 49, vo: "" },
  //: 05:00–05:39 — the lab releases the report and the chain fills in.
  { id: "w10-release", kind: "film", in: 301, seconds: 38, vo: "" },
  //: 06:01–06:22 — the cab firm's own screen.
  { id: "w11-partner", kind: "film", in: 362, seconds: 21, vo: "" },
  //: 07:28–08:35 — affordability: the budget conversation, end to end.
  { id: "w12-afford", kind: "film", in: 449, seconds: 67, vo: "" },
  //: 08:35–09:10 — the Hindi read-aloud, in the family's own voice.
  { id: "w13-voice", kind: "film", in: 516, seconds: 35, vo: "" },
  //: 10:15–10:50 — Wait becomes Come while nobody touches the phone.
  { id: "w14-flip", kind: "film", in: 616, seconds: 36, vo: "" },

  // ── what it does about the problem ────────────────────────────────────────
  {
    id: "w15-result", kind: "stack", seconds: 38,
    card: {
      heading: "Does it address the problem?",
      rows: [
        ["30 of 50", "wasted journeys under the hospital's default policy, scored against planted ground truth on synthetic families"],
        ["0 of 50", "with Saathi"],
        ["₹2,55,000", "non-medical cost avoided, at the published ₹8,500 per journey"],
        ["No patient data", "has been used anywhere. This is the measurement a pilot replaces."],
      ],
    },
    vo: "Does it work? We scored it against planted ground truth on fifty synthetic families — we generate the true date each report actually lands, then ask whether the family would have travelled for nothing. The hospital's default policy produces thirty wasted journeys out of fifty. Saathi produces none. At the published figure of eight and a half thousand rupees a journey, that is two and a half lakh avoided. These are synthetic families. No real patient data has been used anywhere, and replacing this measurement with a real one is exactly what the pilot is for.",
  },
  {
    id: "w16-close", kind: "card", seconds: 17,
    card: {
      heading: "Thank you",
      sub: "Bits2026 · 86W1QA",
      kicker: "The model never decides whether a family travels · report content never enters the system · every decision is in a hash-chained log",
    },
    vo: "Three rules hold all of this up. The model never decides whether a family travels. No report content ever enters the system. And every decision sits in a log that cannot be quietly edited. Thank you for watching.",
  },
];

export const TOTAL = PLAN.reduce((n, s) => n + s.seconds, 0);
