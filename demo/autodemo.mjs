/**
 * The automatic demo: the real apps, driven, recorded as one flow.
 *
 *     make demo-video
 *
 * The family's phone, the desk and the navigator are separate applications. The
 * thing worth watching is one event crossing between them — a machine goes
 * down in Mumbai, and a phone in Gaya changes while someone is holding it — so
 * this drives the demo stage (`frontend/apps/demo-stage`), which mounts all
 * three in device frames, and the cursor moves between them the way attention
 * does. The story bar and the clock controls live on the stage page itself:
 * they are the presenter's, and no role's app has them.
 *
 * **What is real and what is staged.** Everything the system does is real:
 * every press runs the `LiveRunner` method a person's click would, the planner
 * re-runs, Groq writes the family's message, Whisper transcribes the audio, and
 * the guard reads the result. Two runs differ because the model output differs,
 * which is the point — identical frames every time would mean a video, not a
 * run.
 *
 * What is staged is only the *input* a human would otherwise supply: which
 * button gets pressed, and what the family asks. The spoken question is a
 * recorded clip (`audio/hi-dose-question.wav`, synthesised with macOS `say` —
 * see `make demo-audio`) fed to Chrome as a fake capture device. From
 * `getUserMedia` onward nothing knows the difference: a real `MediaRecorder`
 * captures it, the real endpoint receives it, and real Whisper transcribes it.
 *
 * Two things are added for the camera and neither touches the app. A cursor is
 * drawn, because an OS pointer does not appear in a screen recording. And a
 * caption bar narrates, because an audience watching silent automation cannot
 * tell which part was the clever bit.
 */

import { chromium } from "playwright";
import { Demo, OVERLAY } from "./stagecraft.mjs";
import { existsSync, mkdirSync, readdirSync, renameSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../recordings");

//: The demo stage, which frames the others. It finds them by the addresses in its
//: own config.json; override these only if you moved an app off its usual port.
const STAGE_URL = process.env.SAATHI_STAGE_URL ?? "http://localhost:5190";
const APP_URLS = {
  family: process.env.SAATHI_FAMILY_URL ?? "http://localhost:5180",
  desk: process.env.SAATHI_DESK_URL ?? "http://localhost:5174",
  navigator: process.env.SAATHI_NAVIGATOR_URL ?? "http://localhost:5173",
};
const API_URL = process.env.SAATHI_API_URL ?? "http://localhost:8001";
//: 1080p, so the recording plays full-screen on any projector or monitor
//: without the browser scaling it down. At 1600×1000 the two screens were
//: legible on a laptop and not in a room.
const VIEWPORT = { width: 1920, height: 1080 };

//: Whose phone is on the stage. Story one is his, and he reads Hindi, which is
//: the language of the recorded question below.
const PHONE = process.env.SAATHI_DEMO_PHONE ?? "P-SHAMBHU";

//: The spoken question, as a fake capture device. Chrome loops this file
//: through `getUserMedia`, so the page's own `MediaRecorder` records it and the
//: transcription that follows is a real Whisper call on real audio.
const AUDIO = resolve(HERE, "audio/hi-dose-question.wav");

//: Stills, beside the recording. Overwritten each run so the newest set is
//: always the one on disk and nobody pastes last week's frame into a deck.
const STILLS = resolve(OUT, "stills");

/** Slow enough to follow on a projector, quick enough to hold a room. */
const BEAT = Number(process.env.SAATHI_DEMO_BEAT ?? 900);


/* ── driving ─────────────────────────────────────────────────────────────── */

/* ── the run ─────────────────────────────────────────────────────────────── */

async function preflight() {
  const checks = [
    ["demo stage", STAGE_URL],
    ["family app", APP_URLS.family],
    ["desk app", APP_URLS.desk],
    ["navigator app", APP_URLS.navigator],
    ["API", `${API_URL}/api/health`],
  ];
  const missing = [];
  for (const [name, url] of checks) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(4000) });
      if (!response.ok) missing.push([name, url, `HTTP ${response.status}`]);
    } catch (error) {
      missing.push([name, url, error.cause?.code ?? error.name]);
    }
  }
  if (!existsSync(AUDIO)) {
    console.error(`\nThe spoken question is missing: ${AUDIO}`);
    console.error("Build it with:  make demo-audio\n");
    process.exit(1);
  }
  if (missing.length === 0) return;

  console.error("\nThe demo drives the running app; it does not start it.\n");
  for (const [name, url, why] of missing) {
    console.error(`  ${name} not reachable at ${url}  (${why})`);
  }
  console.error("\nStart everything in one terminal, then run this again:\n");
  console.error("  SAATHI_API_PORT=8001 make dev PORT=8001\n");
  process.exit(1);
}

async function reset() {
  const response = await fetch(`${API_URL}/api/live/control`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ action: "reset" }),
  });
  if (!response.ok) throw new Error(`reset failed: ${response.status}`);
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  mkdirSync(STILLS, { recursive: true });
  await preflight();
  // A rehearsable demo starts from the same world every time. Only the model's
  // words differ between runs.
  await reset();

  // Headed by default: the usual reason to run this is to watch it. Set
  // SAATHI_DEMO_HEADLESS=true in CI or over SSH, where there is no display.
  const headless = process.env.SAATHI_DEMO_HEADLESS === "true";
  const browser = await chromium.launch({
    headless,
    args: [
      "--force-device-scale-factor=1",
      // The staged input: a recorded question, presented to Chrome as a
      // capture device. Everything downstream of `getUserMedia` — the page's
      // MediaRecorder, the upload, Whisper — is real and unaware.
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
      `--use-file-for-fake-audio-capture=${AUDIO}`,
      "--autoplay-policy=no-user-gesture-required",
    ],
    slowMo: headless ? 0 : Number(process.env.SAATHI_DEMO_SLOWMO ?? 0),
  });
  console.log(headless ? "running headless" : "opening a browser window…");
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    recordVideo: { dir: OUT, size: VIEWPORT },
    // Granted up front so no permission prompt interrupts the recording. The
    // fake device means nothing on this machine is actually listening.
    permissions: ["microphone"],
  });
  await context.addInitScript(OVERLAY);
  const page = await context.newPage();
  const demo = new Demo(page, { viewport: VIEWPORT, beat: BEAT, stills: STILLS });

  try {
    await page.goto(`${STAGE_URL}/?phones=${encodeURIComponent(PHONE)}`, {
      waitUntil: "domcontentloaded",
    });

    // The three apps, each in its own frame. Everything below addresses them by
    // name, so a click is unambiguously on the phone, the desk or the navigator.
    // The story bar is the stage's own, so it is addressed on the page.
    const phone = page.frameLocator('iframe[title^="Family app"]');
    const desk = page.frameLocator('iframe[title="Desk app"]');
    const nav = page.frameLocator('iframe[title="Navigator app"]');

    // The title card goes up first, over the loading apps. Otherwise the first
    // seconds of the recording — and the poster frame every player shows as
    // the thumbnail — are two half-built screens with nothing happening.
    await demo.raiseTitle("EKYATRA Saathi", "Two screens. One system.");

    await phone.locator(".fx-app").waitFor({ timeout: 25000 });
    await desk.locator(".iss-text").waitFor({ timeout: 25000 });
    await nav.locator(".fam-list").waitFor({ timeout: 25000 });
    await page.locator(".story-bar").waitFor({ timeout: 25000 });
    await page.waitForTimeout(1600);
    await demo.dropTitle();
    await demo.shot("both-screens");
    await demo.say(
      "On the left, a family's phone in Gaya, Bihar. In the middle, the desk in " +
        "Mumbai. On the right, the navigator — 1,771 km from the family.",
      3600,
    );
    await demo.say(
      "Three separate applications sharing one backend. The question they answer " +
        "together: is this trip worth making?",
      3400,
    );

    /* ---------- Act 1: the hospital has a bad day ---------- */

    await demo.title("1 · The hospital has a bad day", "Shambhu Prasad · Gaya");

    // The desk takes the stage: this beat happens entirely in Mumbai, and at
    // half width a thirty-family worklist is unreadable in a room.
    await demo.focus("Desk");
    const advance = page.locator(".story-bar button.btn.primary");

    await demo.say(
      "Shambhu is booked for an MRI tomorrow. His family is about to start a " +
        "twenty-hour journey by road.",
      3400,
    );
    await demo.say(
      "7:40 am. MRI-2 fails. The desk does not fill in a form — it types the " +
        "line it would write in its own work log.",
      3800,
    );
    await demo.type(
      desk.locator(".iss-text"),
      "MRI-2 down till Saturday, nothing can run on it",
    );
    await demo.click(desk.locator(".iss-entry button"), { label: "read it" });
    await desk.locator(".iss-reading").waitFor({ timeout: 45000 });
    await demo.say(
      "An agent reads it and proposes a record: which machine, what kind of " +
        "outage, and it resolved \u201ctill Saturday\u201d to a date.",
      4000,
    );
    await demo.shot("work-log-read");
    await demo.say(
      "It proposes. It does not report. The desk confirms what was understood — " +
        "the model supplies the reading, a person supplies the decision.",
      4200,
    );
    // Cancelled on purpose: the scripted story raises this same outage a
    // moment later, so letting both through would report it twice. The
    // narration says so rather than hiding the seam.
    await demo.click(desk.locator(".iss-actions button", { hasText: "Cancel" }));
    await demo.say(
      "Here the scripted story raises that same report, so the clock matches " +
        "the brief. One tap — the desk states a fact, it decides nothing.",
      4000,
    );
    await demo.click(advance, { label: "advance" });
    await page.waitForTimeout(2800);

    // Both, for the one moment that is actually about the crossing.
    await demo.focus("All");
    await demo.say(
      "Watch the phone. Every affected family is told not to travel BEFORE " +
        "anything has worked out a new date.",
      3600,
    );
    await demo.shot("holding-message");

    await demo.focus("Phone");
    await demo.say(
      "That order is the whole design. Silence while a system thinks is the " +
        "gap a family fills by getting on a bus.",
      3600,
    );
    await demo.scroll(phone.locator(".fx-scroll"), 300);
    await demo.say("Why, in the only form that helps: what is being waited for, and when.", 3200);

    await demo.focus("Navigator");
    await demo.say(
      "Meanwhile the planner re-runs. It fetched the journey from Gaya live — " +
        "1,739 km, twenty hours by road, from OpenStreetMap. Nobody typed that.",
      4000,
    );
    await demo.say("The family writes back. Groq composes it; the real guard reads it.", 3200);
    await demo.click(advance);
    await page.waitForTimeout(2800);

    await demo.say(
      "Options come back ranked by nights away and trips taken. A navigator " +
        "chooses — never the model.",
      3600,
    );
    await demo.click(advance);
    await page.waitForTimeout(2800);

    await demo.focus("All");
    await demo.say("And the phone changes, in Hindi, while someone is holding it.", 3200);
    await demo.shot("plan-approved");

    await demo.focus("Phone");
    await demo.say(
      "And it reads itself out. For a caregiver who cannot read this script, " +
        "that is not a convenience — it is the only way the message lands.",
      3400,
    );
    const speak = phone.locator(".fx-speak");
    if (await speak.count()) {
      await demo.click(speak, { label: "read aloud" });
      await demo.shot("reading-aloud");
      await page.waitForTimeout(3400);
    }

    await demo.focus("Navigator");
    await demo.say("The family confirms on the voice line. Press one.", 2400);
    await demo.runOut(page, advance);

    /* ---------- Act 2: the family speaks ---------- */

    await demo.title("2 · The family speaks", "Voice, because reading is not assumed");
    await demo.focus("Phone");
    await demo.say(
      "Many caregivers cannot read their own script. So the microphone is a " +
        "primary control here, the same size as Send.",
      3600,
    );

    const mic = phone.locator(".fx-mic");
    await demo.click(mic, { label: "microphone" });
    await demo.say("Recording. A real microphone capture, in Hindi.", 2400);
    await demo.shot("listening");
    await page.waitForTimeout(2200);
    await demo.click(mic, { label: "stop recording" });

    await demo.say(
      "Groq Whisper transcribes it — real speech-to-text on real audio. " +
        "The question: \u201cwhat happens to the medicine if we cannot come?\u201d",
      4000,
    );
    await page.waitForTimeout(2600);

    await demo.say(
      "It is not sent yet. The words go back to the family to check first — a " +
        "misheard date is not a mistake anyone downstream would catch.",
      4000,
    );
    await demo.shot("transcribed");

    await demo.click(phone.locator(".fx-send"), { label: "send" });
    await page.waitForTimeout(3400);
    await demo.say(
      "The guard screened it. A question about logistics gets an answer; a " +
        "question about a result goes to a person. Saathi never discusses a result.",
      4200,
    );
    await demo.shot("answered");

    /* ---------- Act 3: their language, their record ---------- */

    await demo.title("3 · Their language", "A change to the record, not the view");
    await demo.say("The family asks to be written to in Bengali.", 2400);
    await demo.click(phone.locator('.fx-langs button[title="Bengali"]'), { label: "Bengali" });
    await page.waitForTimeout(3400);
    await demo.say(
      "Groq re-wrote the message in Bengali and the guard checked it again. " +
        "Every message from here on is Bengali.",
      3800,
    );
    await demo.shot("bengali");

    await demo.say(
      "But the older messages are still Hindi, and labelled as such. They were " +
        "sent in Hindi, so that is what the record says.",
      4000,
    );
    await demo.scroll(phone.locator(".fx-scroll"), 240);
    await demo.say(
      "Nothing is rewritten after the fact. This thread is the receipt for what " +
        "this family was actually told.",
      3800,
    );
    await demo.shot("thread-languages");

    /* ---------- Act 4: why, on the hospital's side ---------- */

    await demo.title("4 · Why", "A navigator has to be able to defend this");
    await demo.focus("Navigator");
    await demo.say(
      "The pathway and the trace sit folded away. At 7:40 in the morning a " +
        "navigator needs what happened, not a diagram — but when a family " +
        "argues with the answer, it is one click.",
      4400,
    );
    await demo.click(nav.locator('[data-layer="why"] .ui-layer-head'), {
      label: "why",
    });
    await page.waitForTimeout(2800);
    await demo.say("Every claim behind the decision, and the source each one came from.", 3200);
    await demo.scroll(nav.locator(".fam-layers"), 420);
    await demo.say(
      "Underneath it, the evidence ledger: append-only and hash-chained, so a " +
        "claim cannot be changed after a family acted on it.",
      4000,
    );
    await demo.shot("why-this-answer");
    // Clear first: a caption stays up until the next one replaces it, so
    // switching the view under it leaves the narration describing a pane that
    // is no longer on screen.
    await demo.clear();
    await demo.click(nav.locator('[data-layer="pathway"] .ui-layer-head'));
    await page.waitForTimeout(1400);

    /* ---------- Act 5: story two ---------- */

    await demo.title("5 · A second family", "Anita Devi · in maintenance");
    await demo.clear();
    const anita = page.locator(".story-bar .segmented button", { hasText: "Anita" });
    await demo.click(anita, { label: "Anita's story" });
    await page.waitForTimeout(1400);

    // Picking the story does not pick the family — the worklist is the
    // navigator's own, and a story bar reaching into it would be the console
    // causing something rather than reflecting it. So click her, the way a
    // navigator would, or the whole act narrates Anita over Shambhu's board.
    await demo.click(nav.locator(".fam-row", { hasText: "P-ANITA" }), {
      label: "Anita's board",
    });
    await page.waitForTimeout(1600);

    await demo.say(
      "Anita Devi, 90 km away, on maintenance treatment — 17 doses, with an " +
        "echo before every fourth.",
      3400,
    );
    await demo.say("Her story is the harder one: two things go wrong, a week apart.", 3000);

    const lines = [
      "The hub's only echo cardiologist goes on emergency leave.",
      "Her daughter asks what happens to dose 13. A process answer only — never a clinical one.",
      "Dr Sinha chooses. One option was removed by a care rule before she ever saw it.",
      "Then the drug delivery is late. A second disruption, on top of the first.",
      "And here is the interesting part: the second disruption makes the plan BETTER than the original. One trip instead of two.",
      "The family confirms — her husband on the voice line, her daughter on WhatsApp.",
    ];
    await demo.runOut(page, advance, lines);
    await demo.focus("All");
    await demo.shot("story-two-done");

    await demo.title("What was real", "", 3000);
    await demo.say(
      "The families are synthetic. Everything else was real: the planner, the " +
        "routing tools, Groq writing every message, Whisper hearing the question.",
      4400,
    );
    await demo.say(
      "The guard read every outbound message. The ledger recorded every claim. " +
        "And a person decided anything that touched treatment.",
      4400,
    );
    await demo.clear();
    await page.waitForTimeout(900);
  } finally {
    await context.close();
    await browser.close();
  }

  // Playwright names videos by an internal hash. Rename to something findable.
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const named = resolve(OUT, `saathi-autodemo-${stamp}.webm`);
  const latest = readdirSync(OUT)
    .filter((f) => f.endsWith(".webm") && f.startsWith("page@"))
    .map((f) => ({ f, t: statSync(resolve(OUT, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t)[0];
  if (latest) renameSync(resolve(OUT, latest.f), named);

  console.log(`\nrecording: ${named}`);
  console.log("open it with:  open " + JSON.stringify(named));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
