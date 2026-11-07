# Video-agent prompt — EKYATRA Saathi presentation demo

**How to use this file.** Upload `EKYATRA-Saathi-end-to-end.mp4` (12:07, 1920×1080, in this
same folder) as the source video, then paste everything below the line into the prompt box
of HeyGen (or Synthesia, Argil, Creatify — the brief is written to be tool-agnostic).

Two notes before you do.

- **Nothing else goes in the video.** The two-page solution brief is a separate document for
  the organisers. It is not a slide, not an end card, and not something the agent should
  read from. This prompt is only about the demo film.
- **The accuracy block near the end is the important part.** Every number and claim in it was
  measured, and a video agent asked to make something exciting will otherwise round "zero
  wasted trips on fifty synthetic families" into "zero wasted trips", which is a different
  and untrue sentence.

---

## ROLE

You are producing a **presentation demo video** for EKYATRA Saathi, an entry in Health-a-thon
2026 by team **Bits2026**. You are given a 12-minute narrated screen-recording of the working
product. Your job is to turn it into a **tighter, presenter-led film** that a judging panel
will watch end to end.

You are re-cutting and re-presenting real footage. You are not generating product footage,
and you must not invent screens, numbers, logos or testimonials.

## AUDIENCE AND GOAL

Clinicians, health-system people and technical judges watching many submissions in one
sitting. They will decide in the first forty seconds whether to keep watching.

The one idea they must leave with: **a family travelling 600 km for cancer care is told
whether the trip is worth making today — and the system that decides is not a chatbot.**

## OUTPUT SPEC

- **Length:** 4:00–5:00. The source is 12:07; you are selecting, not replaying.
- **Aspect:** 16:9, 1920×1080. (Also export a 9:16 cut of 0:60 for social, if supported.)
- **Presenter:** one avatar, Indian-English, warm and plain-spoken — a colleague explaining
  their work, not a product launch. Picture-in-picture lower-left over the screen recording;
  full-frame only for the opening and closing.
- **Captions:** burned-in English subtitles throughout. Many judges will watch muted.
- **Pace:** let the screen recording breathe. When a verdict changes on screen, stop talking
  and let it change.

## SOURCE MAP

Use these timecodes to pull footage. Chapter cards in the source are dark title cards; you
may keep them as transitions or replace them with your own lower-thirds.

| Source | What is on screen |
|---|---|
| 00:00–00:25 | Title and the problem framing |
| 00:28–01:14 | Onboarding: a family taken on in seven stages; the medical-background stage |
| 01:17–02:44 | The hospital control centre, section by section |
| 02:47–05:55 | **The core demo.** Three families on one morning: the network board, Meena's cab answering by itself (Wait→Go), Ravi's cab firm failing, a navigator pressing *Book another*, the lab releasing Anita's report, the chain filling in |
| 05:58–06:19 | The cab firm's own screen — a vendor signed in, seeing only its own jobs |
| 06:22–07:22 | The family's Android app: email sign-in, then the Wait state in Hindi |
| 07:25–08:29 | **Affordability.** The family is asked what they can manage; three real options; a navigator confirms; the ride moves from a taxi to the railway patient-quota desk |
| 08:32–09:17 | Read-aloud in Hindi (Sarvam voice) |
| 09:20–10:14 | What a vendor failure looks like on the family's phone |
| 10:17–11:33 | **The money shot.** The lab releases the report and the family's phone changes by itself: रुकिए (Wait) → आइए (Come), with a date |
| 11:33–12:07 | What never enters the system; close |

## STRUCTURE TO BUILD

**1 — The problem (0:00–0:40).** Presenter full-frame, then under footage.
> "Sixty per cent of the patients at India's biggest cancer hospital come from outside the
> state. Most travel over five hundred kilometres. They arrive, and the report isn't back —
> so they go home and come again. Eighty-three per cent of those families hit catastrophic
> non-medical costs. Half borrow or sell something to cope. Saathi asks one question, every
> day, for every family: is this trip worth making?"

**2 — The decision (0:40–1:40).** Use 02:47–03:30 and 04:30–05:30.
> "This is a hospital navigator's board: every family against every party holding them up —
> the lab, the insurer, the pharmacy, the cab, the hotel. Watch Meena. Her cab firm answers
> for itself, and the moment the last party is ready, Wait becomes Come and a date appears.
> The date is a consequence of readiness. It is never a guess."
>
> Then the failure, from 03:30–04:30:
> "Ravi's cab firm says it cannot. The journey stops. No date is promised, because there is
> nothing to promise — and a person, not the system, picks who to ask next."

**3 — The family's side (1:40–2:30).** Use 06:22–07:22 and 10:17–11:00.
> "The family has none of that complexity. One word, one date, what to bring, in their own
> language. And when the lab four hundred kilometres away releases the report — nobody
> touches the phone. Wait becomes Come, and the list of papers to carry appears with it."
>
> Hold on the Hindi screen flipping रुकिए → आइए. **Do not cut away during the flip.**

**4 — Affordability (2:30–3:20).** Use 07:25–08:29. This section is the differentiator.
> "Not every family can absorb an app cab and a hotel. So Saathi asks — and the options are
> real organisations from the hospital's own directory: a railway patient-quota berth, a
> shared jeep, a taxi. This family's ration card is AAY, so the concession is offered first.
> There is no price on the screen, because the system has none to give. And last on every
> list, deliberately not one of the things to buy: *I cannot manage any of these* — which
> doesn't book a cheaper cab. It raises a social worker."

**5 — Why it is trustworthy (3:20–4:10).** Use 11:33–11:53, plus the Hindi read-aloud at
08:32–09:00 for one beat.
> "Three things make this safe to put in front of a family. The model never decides whether
> they travel — a deterministic planner decides, and the model only puts that decision into
> their language. No report content ever enters the system; there is no field that could
> hold a diagnosis. And every decision is in a hash-chained log that cannot be quietly
> edited. It speaks Hindi, Bengali and Odia — Odia because no browser and almost no phone
> ships that voice, so read-aloud used to do nothing at all for those families."

**6 — The result and the ask (4:10–4:40).** Presenter full-frame.
> "Scored against planted ground truth on fifty synthetic families: the hospital's default
> would have sent thirty of them on a wasted journey. With Saathi, none. We have not touched
> real patient data, and that is the next step — a hospital partner and an ethics approval,
> so this can be measured on real families instead of simulated ones."

## STYLE

- **Verbs over adjectives.** "The cab firm answers for itself" beats "a powerful AI-driven
  orchestration layer".
- **No stock footage of hospitals, doctors or families.** The product footage is the proof;
  stock imagery makes it look like there is nothing to show.
- **Keep the Hindi on screen untranslated**, with the presenter saying what it means. Seeing
  the family's own language is the point; subtitling it away removes it.
- **Music:** sparse and low, out entirely under the verdict changes.
- **No countdown timers, no swooshes, no neon.** The product is a calm light interface;
  match it.

## ACCURACY — DO NOT DEVIATE

Everything below was measured or cited. Do not round, dramatise or extend it.

**Say exactly:**
- "60% of patients at Tata Memorial Hospital come from outside Maharashtra"
- "83% faced catastrophic non-medical costs" (mean ₹88,433)
- "53% of those travelling over 500 km borrowed or sold assets"
- "On **fifty synthetic families with planted ground truth**, the hospital's default policy
  would have produced thirty wasted trips. Saathi produced none."
- "No real patient data has been used."

**Never say:**
- Any claim of clinical validation, hospital deployment, patient outcomes, or lives saved.
- "Diagnoses", "detects", "predicts cancer", or anything implying the system reads results.
  It reads *status* — ready or not ready — and never content.
- A number not in this prompt. If a figure is needed and is not here, omit the sentence.
- That the AI makes the travel decision. It renders a decision the planner made.

**Also:**
- Do not add a company name, funding claim, user count, or partner logo. There are none.
- Do not add an avatar of a doctor or a patient. The team has no clinician member, and an
  implied one is the single most damaging thing this video could do.
- One section of the source (07:25–08:29, affordability) was recorded on a local build rather
  than the deployed service. If you state that the demo runs on a live deployment, add
  "apart from the affordability feature, which is new and not yet deployed."

## DELIVERABLES

1. Master cut, 16:9, 1920×1080, H.264, burned-in English captions.
2. Clean version with no captions.
3. 0:60 vertical cut (9:16) built from sections 1, 4 and the Wait→Come flip.
4. The narration script as text, so it can be checked line by line against this prompt.
