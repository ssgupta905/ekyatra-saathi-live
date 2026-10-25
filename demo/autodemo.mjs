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

/* ── the camera layer: a cursor and a caption, injected, app untouched ──── */

const OVERLAY = `
  (() => {
    // The stage is three documents. Only the outer one gets a cursor, or each
    // iframe draws its own and the recording shows three pointers.
    if (window.top !== window) return;
    const cursor = document.createElement('div');
    cursor.id = '__demo_cursor';
    Object.assign(cursor.style, {
      position: 'fixed', zIndex: 2147483647, width: '22px', height: '22px',
      marginLeft: '-5px', marginTop: '-3px', pointerEvents: 'none',
      transition: 'transform 60ms linear', left: '0', top: '0',
    });
    cursor.innerHTML =
      '<svg viewBox="0 0 22 22" width="22" height="22">' +
      '<path d="M4 2 L4 17 L8.2 13.2 L11 19.4 L13.6 18.2 L10.9 12.2 L16.4 12.1 Z"' +
      ' fill="#1d1d1f" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>';

    const title = document.createElement('div');
    title.id = '__demo_title';
    Object.assign(title.style, {
      position: 'fixed', zIndex: 2147483646, left: '0', right: '0', top: '0',
      bottom: '0', display: 'flex', flexDirection: 'column', gap: '10px',
      alignItems: 'center', justifyContent: 'center', textAlign: 'center',
      background: 'rgba(16,16,18,0.9)', color: '#fff', opacity: '0',
      transition: 'opacity 320ms ease', pointerEvents: 'none',
      backdropFilter: 'saturate(140%) blur(6px)',
      font: '600 44px/1.15 -apple-system, BlinkMacSystemFont, "SF Pro Display", system-ui, sans-serif',
      letterSpacing: '-0.03em',
    });

    const caption = document.createElement('div');
    caption.id = '__demo_caption';
    Object.assign(caption.style, {
      position: 'fixed', zIndex: 2147483646, left: '50%', bottom: '28px',
      transform: 'translateX(-50%)', maxWidth: 'min(900px, 86vw)',
      padding: '12px 20px', borderRadius: '14px',
      background: 'rgba(29,29,31,0.92)', color: '#fff',
      font: '500 16px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif',
      letterSpacing: '-0.01em', textAlign: 'center', opacity: '0',
      transition: 'opacity 220ms ease', boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
      pointerEvents: 'none', backdropFilter: 'saturate(180%) blur(12px)',
    });

    const attach = () => {
      if (!document.body) return;
      if (!document.getElementById('__demo_cursor')) document.body.appendChild(cursor);
      if (!document.getElementById('__demo_caption')) document.body.appendChild(caption);
      if (!document.getElementById('__demo_title')) document.body.appendChild(title);
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', attach);
    } else {
      attach();
    }

    window.__demoMove = (x, y) => {
      attach();
      cursor.style.transform = 'translate(' + x + 'px,' + y + 'px)';
    };
    window.__demoTitle = (heading, sub) => {
      attach();
      title.innerHTML = '';
      if (!heading) { title.style.opacity = '0'; return; }
      const h = document.createElement('div');
      h.textContent = heading;
      title.appendChild(h);
      if (sub) {
        const s2 = document.createElement('div');
        s2.textContent = sub;
        Object.assign(s2.style, {
          font: '400 19px/1.4 -apple-system, BlinkMacSystemFont, system-ui, sans-serif',
          letterSpacing: '-0.01em', color: '#a1a1a6',
        });
        title.appendChild(s2);
      }
      title.style.opacity = '1';
    };
    window.__demoSay = (text) => {
      attach();
      caption.textContent = text || '';
      caption.style.opacity = text ? '1' : '0';
    };
    // Mirror real mouse movement too, so a human can take over mid-recording.
    window.addEventListener('mousemove', (e) => window.__demoMove(e.clientX, e.clientY));
  })();
`;

/* ── driving ─────────────────────────────────────────────────────────────── */

class Demo {
  constructor(page) {
    this.page = page;
    this.at = { x: VIEWPORT.width / 2, y: 140 };
  }

  /** Press Advance until the story says it is finished.
   *
   *  Never a counted number of presses: a story that gains a beat silently
   *  ends one short, and a disabled button cannot tell "busy" from "done".
   *  The progress counter is the only unambiguous signal, and it is the one a
   *  presenter is reading anyway. */
  async runOut(frame, advance, lines = []) {
    for (let i = 0; i < 12; i += 1) {
      const progress = await frame.locator(".story-progress").first().textContent();
      const [done, total] = (progress ?? "0/0").split("/").map(Number);
      if (!Number.isFinite(total) || done >= total) return;
      if (lines[i]) await this.say(lines[i], 2300);
      await this.click(advance);
      await this.page.waitForTimeout(2900);
    }
  }

  /** Scroll something, visibly. A screen that never moves reads as a mockup,
   *  and the content below the fold is half of what each app has to show. */
  async scroll(locator, by) {
    const box = await locator.boundingBox().catch(() => null);
    if (!box) return;
    await this.moveTo(box.x + box.width / 2, box.y + box.height / 2);
    // In steps, so the motion is visible rather than a jump cut.
    for (let i = 0; i < 6; i += 1) {
      await this.page.mouse.wheel(0, by / 6);
      await this.page.waitForTimeout(90);
    }
    await this.page.waitForTimeout(500);
  }

  /** Give one screen the whole stage, or put them all back.
   *
   *  Side by side is right for the moment an event crosses between them, and
   *  wrong for reading a thread or a worklist — at a third of the width each
   *  screen is legible on a monitor and not on a projector. Modes: All, Phone,
   *  Desk, Navigator. */
  async focus(mode) {
    await this.click(this.page.locator(".st-focus button", { hasText: mode }), {
      label: `focus ${mode}`,
    });
    await this.page.waitForTimeout(700);
  }

  /** A full-screen act card. Structure the audience can hold on to — without
   *  it, four minutes of two screens reacting reads as one undifferentiated
   *  thing and nobody can tell which part was the point. */
  async title(heading, sub = "", hold = 2600) {
    await this.raiseTitle(heading, sub);
    await this.page.waitForTimeout(hold);
    await this.dropTitle();
  }

  async raiseTitle(heading, sub = "") {
    await this.page.evaluate(([h, s2]) => window.__demoTitle?.(h, s2), [heading, sub]);
    await this.page.evaluate(() => window.__demoSay?.(""));
  }

  async dropTitle() {
    await this.page.evaluate(() => window.__demoTitle?.(""));
    await this.page.waitForTimeout(420);
  }

  async say(text, hold = BEAT) {
    await this.page.evaluate((t) => window.__demoSay?.(t), text);
    await this.page.waitForTimeout(hold);
  }

  async clear() {
    await this.page.evaluate(() => window.__demoSay?.(""));
  }

  /** Move in a slight arc, the way a hand does, rather than a straight jump. */
  async moveTo(x, y) {
    const steps = 22;
    const { x: fromX, y: fromY } = this.at;
    for (let i = 1; i <= steps; i += 1) {
      const t = i / steps;
      const ease = t < 0.5 ? 2 * t * t : 1 - (2 - 2 * t) ** 2 / 2;
      const cx = fromX + (x - fromX) * ease;
      const cy = fromY + (y - fromY) * ease - Math.sin(ease * Math.PI) * 18;
      await this.page.mouse.move(cx, cy);
      await this.page.evaluate(([px, py]) => window.__demoMove?.(px, py), [cx, cy]);
      await this.page.waitForTimeout(9);
    }
    this.at = { x, y };
  }

  /** Point at something without clicking it. The caption says "watch the
   *  phone"; without this the cursor stays wherever it last clicked and the
   *  audience is looking at the wrong half of the screen. */
  async lookAt(locator) {
    const box = await locator.boundingBox().catch(() => null);
    if (!box) return;
    await this.moveTo(box.x + box.width / 2, box.y + Math.min(box.height / 2, 90));
  }

  /** Keep a frame. Named, numbered, and written beside the recording. */
  async shot(name) {
    this.frame = (this.frame ?? 0) + 1;
    const file = resolve(STILLS, `${String(this.frame).padStart(2, "0")}-${name}.png`);
    await this.page.screenshot({ path: file }).catch(() => {});
  }

  async click(locator, { label } = {}) {
    // Wait for the control to be ready. The Advance button disables itself
    // while a beat is running, and a click landing in that window is silently
    // swallowed — which is exactly how the first recording stopped at beat 3
    // of 4 while appearing to have pressed it four times.
    await locator.waitFor({ state: "visible", timeout: 15000 });
    for (let i = 0; i < 60 && !(await locator.isEnabled().catch(() => true)); i += 1) {
      await this.page.waitForTimeout(250);
    }
    await locator.scrollIntoViewIfNeeded().catch(() => {});
    const box = await locator.boundingBox();
    if (!box) throw new Error(`nothing to click${label ? ` for ${label}` : ""}`);
    await this.moveTo(box.x + box.width / 2, box.y + box.height / 2);
    await this.page.waitForTimeout(140);
    await locator.click();
    await this.page.waitForTimeout(260);
  }

  async type(locator, text) {
    await this.click(locator);
    await locator.fill("");
    await this.page.keyboard.type(text, { delay: 55 });
    await this.page.waitForTimeout(300);
  }
}

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
  const demo = new Demo(page);

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
    await nav.locator(".hx-worklist").waitFor({ timeout: 25000 });
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
    await demo.click(nav.locator(".hx-lens button", { hasText: "Why this answer" }), {
      label: "why",
    });
    await page.waitForTimeout(2800);
    await demo.say("Every claim behind the decision, and the source each one came from.", 3200);
    await demo.scroll(nav.locator(".hx-work"), 420);
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
    await demo.click(nav.locator(".hx-lens button", { hasText: "Pathway" }));
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
    await demo.click(nav.locator(".hx-row", { hasText: "P-ANITA" }), {
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
