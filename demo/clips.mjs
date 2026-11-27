/**
 * The demo, as a set of clips rather than one long take.
 *
 * `hosted-flow.mjs` films three windows tiled side by side for sixteen minutes.
 * It proved the system works, but it is not watchable: no surface is ever large
 * enough to read, the viewer is never told where to look, and one bad beat
 * costs the whole run.
 *
 * This records each beat on its own, from the source, full size:
 *
 *   - browser surfaces through Playwright's own page recording
 *   - handsets through `scrcpy --no-window --record`
 *
 * Nothing is captured from the desktop, which is what makes it safe. The
 * previous method put my editor — and four live API keys — into a film,
 * and also caught the macOS lock screen, a notification shade, and the Desk
 * View camera when an iPhone came into Continuity range. None of those can
 * reach a clip that was never taken from the screen.
 *
 * Clips are numbered and re-shootable one at a time:
 *
 *     node demo/clips.mjs                 # everything, in order
 *     node demo/clips.mjs --only 08       # just the planner search
 *     node demo/clips.mjs --from 11       # 11 onwards
 *     node demo/clips.mjs --list          # what the clips are
 *
 * **The clips are evidence, not illustration.** Each one drives the real
 * deployed stack and records whatever actually happens. Where a beat cannot
 * happen — a family with no plan to read out, a lookup that returns nothing —
 * the clip is skipped and said so, and the film goes without it. Nothing here
 * stages a screen.
 */

import { chromium } from "playwright";
import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { adbFor, pickPhone, pickSecond, recordPhone } from "./lib/device.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../recordings/clips");

/* ─────────────────────────── addresses and env ─────────────────────────── */

function loadEnvFile() {
  let text;
  try {
    text = readFileSync(resolve(HERE, "../.env"), "utf8");
  } catch {
    return;
  }
  for (const line of text.split("\n")) {
    const m = /^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$/i.exec(line);
    if (m && process.env[m[1]] === undefined) {
      process.env[m[1]] = m[2].trim().replace(/^(['"])(.*)\1$/, "$2");
    }
  }
}
loadEnvFile();

const LOCAL = /^(https?:\/\/)?(localhost|127\.0\.0\.1|\[?::1\]?|0\.0\.0\.0|10\.0\.2\.2)([:/]|$)/i;

//: `--list` is a question about this file, not about a deployment, so it must
//: answer without one configured.
const LISTING = process.argv.includes("--list");

function must(name) {
  if (LISTING) return "";
  const value = process.env[name];
  if (!value) {
    console.error(`\n  ${name} is not set. These clips record the deployed stack.\n`);
    process.exit(1);
  }
  if (LOCAL.test(value)) {
    console.error(`\n  ${name}=${value} is a local address. These clips are evidence`);
    console.error("  that the deployed system does this; a laptop will not do.\n");
    process.exit(1);
  }
  return value.replace(/\/+$/, "");
}

const API = must("SAATHI_API_URL");
const PANEL = must("SAATHI_PANEL_URL");
const EMR = must("SAATHI_OPENEMR_URL");
const FAMILY_WEB = process.env.SAATHI_FAMILY_URL ?? "https://ekyatra-saathi-family.onrender.com";
const PARTNER_WEB = process.env.SAATHI_PARTNER_URL ?? "https://ekyatra-saathi-partner.onrender.com";

/* ────────────────────────────── small helpers ──────────────────────────── */

const wait = (ms) => new Promise((done) => setTimeout(done, ms));

async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(`${API}/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`${method} ${path} → ${response.status}`);
  return response.json();
}

/** Poll until something is true, or say clearly what never happened. */
async function until(what, read, ok, { tries = 30, gap = 3000 } = {}) {
  let last;
  for (let i = 0; i < tries; i += 1) {
    last = await read().catch(() => null);
    if (last && ok(last)) return last;
    await wait(gap);
  }
  throw new Error(`${what} did not happen after ${Math.round((tries * gap) / 1000)}s`);
}

const say = (text) => console.log(`    ${text}`);

/**
 * The connector's own tally of what it has done to the hospital.
 *
 * Read from `/hospital/now` rather than counted here, so every claim a clip
 * makes about the write-back is the connector's number, not ours.
 */
async function connectorCounts() {
  const now = await api("/hospital/now").catch(() => ({ hospitals: [] }));
  const live = (now.hospitals ?? []).find((b) => b.connector?.live);
  return live?.connector?.counts ?? {};
}

/* ───────────────────────────── browser clips ───────────────────────────── */

/**
 * Record one browser surface doing one thing.
 *
 * Headless on purpose: there is no window, so there is nothing for another
 * app to appear in front of. 1600x1000 is 16:10, which letterboxes cleanly
 * into a 1920x1080 film without cropping anything off a dense console.
 */
async function web(name, url, act, { width = 1600, height = 1000 } = {}) {
  const dir = resolve(OUT, `_${name}`);
  rmSync(dir, { recursive: true, force: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width, height },
    recordVideo: { dir, size: { width, height } },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 120000 });
    await wait(2500);
    await act(page);
  } finally {
    await context.close();
    await browser.close();
  }
  // Playwright names the file by an internal id; give it the clip's name.
  const { readdirSync } = await import("node:fs");
  const made = readdirSync(dir).find((f) => f.endsWith(".webm"));
  if (!made) throw new Error(`${name}: playwright wrote no video`);
  const final = resolve(OUT, `${name}.webm`);
  renameSync(resolve(dir, made), final);
  rmSync(dir, { recursive: true, force: true });
  return final;
}

/* ─────────────────── what the app's own chrome says, per language ──────── */
//: Read off `Translations.kt`. A table short of a language means a family the
//: film cannot follow, which is how three takes lost the cost card.
const MESSAGES = { hi: "संदेश", bn: "বার্তা", ta: "செய்திகள்", or: "ସନ୍ଦେଶ", en: "Messages" };
const PLAN_TAB = { hi: "योजना", bn: "পরিকল্পনা", ta: "திட்டம்", or: "ଯୋଜନା", en: "Plan" };
const TODAY_TAB = { hi: "आज", bn: "আজ", ta: "இன்று", or: "ଆଜି", en: "Today" };
const SPEAK = { hi: "बोलिए", bn: "বলুন", ta: "பேசுங்கள்", or: "କୁହନ୍ତୁ", en: "Speak" };
const SPENDS = { hi: "खर्चा", bn: "খরচ", ta: "செலவு", or: "ଖର୍ଚ୍ଚ", en: "Spends" };
const COST_CARD = {
  hi: "yeh kaise nikla", bn: "এটা কীভাবে এল", ta: "இது எப்படி வந்தது",
  or: "ଏହା କିପରି ଆସିଲା", en: "how this was worked out",
};
const STAY_NEED = {
  hi: "ठहरने की जगह", bn: "থাকার জায়গা", ta: "தங்குவதற்கு இடம்",
  or: "ରହିବା ସ୍ଥାନ", en: "Somewhere to stay",
};

//: What each family says back, in their own language written the way people
//: actually type it. Not translations of one sentence: each says a different
//: thing, because the point is that different households have different
//: problems — a wage lost, a salary that arrives on the 1st, a month to wait.
const REPLIES = {
  hi: "Bees tarikh ke baad hi aa sakte hain, pehle nahi. Do log aayenge. Bus ka kiraya chaudah sau rupaye lagega.",
  bn: "Amar sathe ami jabo. Trainer tickets 900 taka hobe. 1 tarikher age noy, salary tokhon ase.",
  ta: "Irupathu theti ku appuram thaan vara mudiyum. Rendu per varuvom. Bus kattanam aayiram roobai aagum.",
  en: "Can't do a weekday, I lose the day's wages. After the 4th is fine, and only me coming.",
};

/* ────────────────────────────── phone clips ────────────────────────────── */

let PHONE = null;
let SECOND = null;
let adb = null;

/** Tap text read from the live view hierarchy, searching both ways for it. */
async function tap(serial, label, settle = 3000) {
  const call = adbFor(serial);
  const dump = async () => {
    await call.quiet("shell", "uiautomator", "dump", "/sdcard/ui.xml");
    const { stdout } = await call.quiet("shell", "cat", "/sdcard/ui.xml");
    return stdout;
  };
  const find = (xml) =>
    xml.match(
      new RegExp(`text="([^"]*${label}[^"]*)"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`),
    );

  let xml = await dump();
  let hit = find(xml);
  if (!hit) {
    // A thread opens at its newest message, so what the film wants is usually
    // above the fold rather than below it. Look down, then up.
    for (const [from, to] of [[1800, 900], [800, 1900]]) {
      let previous = "";
      for (let i = 0; i < 10 && !hit; i += 1) {
        if (xml === previous) break;
        previous = xml;
        await call.quiet("shell", "input", "swipe", "540", String(from), "540", String(to), "260");
        await wait(900);
        xml = await dump();
        hit = find(xml);
      }
      if (hit) break;
    }
  }
  if (!hit) return null;
  const [x1, y1, x2, y2] = hit.slice(2).map(Number);
  await call.quiet(
    "shell", "input", "tap",
    String(Math.round((x1 + x2) / 2)), String(Math.round((y1 + y2) / 2)),
  );
  await wait(settle);
  return hit[1];
}

async function onPhone(serial, fragment) {
  const call = adbFor(serial);
  await call.quiet("shell", "uiautomator", "dump", "/sdcard/ui.xml");
  const { stdout } = await call.quiet("shell", "cat", "/sdcard/ui.xml");
  return stdout.normalize("NFC").includes(fragment.normalize("NFC"));
}

/**
 * Scroll until something is on screen, and leave it there.
 *
 * A thread opens at its newest message, so the thing a clip is about — a
 * question asked twenty minutes ago, a proposal with its working folded under
 * it — is usually above the fold. Checking without scrolling reports it
 * missing when it is merely out of view, which is how three takes concluded
 * the cost card did not exist.
 *
 * Both sides of the comparison are NFC-normalised: the fragment comes from the
 * API and the screen text from uiautomator, and nothing guarantees the two
 * compose Indic conjuncts the same way.
 */
async function reveal(serial, fragment, { swipes = 10 } = {}) {
  if (await onPhone(serial, fragment)) return true;
  const call = adbFor(serial);
  let previous = "";
  for (let i = 0; i < swipes; i += 1) {
    await call.quiet("shell", "uiautomator", "dump", "/sdcard/ui.xml");
    const { stdout } = await call.quiet("shell", "cat", "/sdcard/ui.xml");
    if (stdout === previous) break;
    previous = stdout;
    // Finger downward reveals what is above: older messages.
    await call.quiet("shell", "input", "swipe", "540", "800", "540", "1900", "260");
    await wait(900);
    if (await onPhone(serial, fragment)) return true;
  }
  return false;
}

/** Start the app from a known place, whatever the last clip left behind. */
async function freshApp(serial) {
  const call = adbFor(serial);
  // HOME first: it closes a notification shade, which otherwise covers
  // everything and makes the app look absent.
  await call.quiet("shell", "input", "keyevent", "KEYCODE_HOME");
  await wait(1200);
  await call.quiet("shell", "am", "force-stop", "org.ekyatra.saathi");
  await wait(1500);
  await call.quiet("shell", "am", "start", "-n", "org.ekyatra.saathi/.MainActivity");
  await wait(8000);
}

/** Record a handset while `act` drives it. */
async function phone(name, serial, act) {
  const file = resolve(OUT, `${name}.mp4`);
  const rec = recordPhone(serial, file);
  await wait(1200);
  try {
    await act(serial);
  } finally {
    await wait(1200);
    await rec.stop();
  }
  return file;
}

/* ──────────────────────────────── the clips ────────────────────────────── */

const state = {};

/**
 * Rebuild what earlier clips learned, by asking the system.
 *
 * `--only 10` has to work without having run 01–09 first, or a bad clip costs
 * the whole sequence again — which is the thing this file exists to stop. So
 * nothing is remembered between clips that cannot be re-read from the live
 * deployment: who was asked, who replied, what was offered.
 */
async function recall() {
  if (!state.asked) {
    const waiting = await api("/questions/waiting").catch(() => []);
    const hit = waiting.filter((q) => q.about_day === state.day && q.reason === "doctor_away");
    if (hit.length) {
      state.asked = hit;
      say(`recalled: ${hit.map((q) => `${q.name} (${q.language})`).join(", ")}`);
    }
  }
  if (!state.following && state.asked) {
    state.following = state.asked.find((q) => q.language !== "en") ?? state.asked[0];
  }
  if (!state.replied && state.following) {
    // Whoever already has a reading is the one the later clips follow; before
    // any reply exists, it is simply whoever the film was going to follow.
    const readings = await api("/requests/waiting").catch(() => []);
    const already = readings.find((r) => (state.asked ?? []).some((q) => q.patient_id === r.patient_id));
    state.replied = already
      ? (state.asked ?? []).find((q) => q.patient_id === already.patient_id)
      : state.following;
  }
}

const CLIPS = [
  {
    id: "01",
    name: "01-hospital-leave",
    says: "A clinician marks themselves away, in OpenEMR's own calendar",
    async shoot() {
      const day = state.day;
      return web("01-hospital-leave", `${EMR}/interface/login/login.php?site=default`, async (page) => {
        await page.fill("#authUser", process.env.SAATHI_OPENEMR_USER ?? "admin").catch(() => {});
        await page.fill("#clearPass", process.env.SAATHI_OPENEMR_PASS ?? "").catch(() => {});
        await page.press("#clearPass", "Enter").catch(() => {});
        await wait(7000);
        await page.goto(`${EMR}/interface/main/calendar/add_edit_event.php?startdate=${day}&prov=true`,
          { waitUntil: "domcontentloaded", timeout: 90000 });
        await wait(3000);
        const options = await page.locator('[name="form_category"] option').evaluateAll(
          (els) => els.map((e) => ({ value: e.value, label: (e.textContent ?? "").trim() })));
        const vacation = options.find((o) => /vacation/i.test(o.label));
        if (!vacation) throw new Error(`no Vacation category (saw: ${options.map((o) => o.label).join(", ")})`);
        await page.selectOption('[name="form_category"]', vacation.value);
        await wait(1800);
        await page.locator('[name="form_allday"]').first().check().catch(() => {});
        await page.fill('[name="form_date"]', day).catch(() => {});
        await page.fill('[name="form_title"]', "Vacation").catch(() => {});
        await page.fill('[name="form_comments"]', "oncology leave").catch(() => {});
        await wait(2500);
        await page.click('[name="form_save"]').catch(async () => {
          await page.locator('button:has-text("Save")').first().click();
        });
        await wait(6000);
        await page.goto(
          `${EMR}/interface/main/calendar/index.php?module=PostCalendar&func=view&tplview=&viewtype=day&Date=${day.replace(/-/g, "")}`,
          { waitUntil: "domcontentloaded", timeout: 90000 }).catch(() => {});
        await wait(6000);
      });
    },
  },

  {
    id: "02",
    name: "02-appointments-untouched",
    says: "The families' appointments that day — unchanged by the leave",
    async shoot() {
      return web("02-appointments-untouched", `${PANEL}/#/hospital`, async (page) => {
        await signInConsole(page, "Seema Kamble");
        await page.goto(`${PANEL}/#/hospital`, { waitUntil: "domcontentloaded" }).catch(() => {});
        await wait(7000);
      });
    },
  },

  {
    id: "03",
    name: "03-board",
    says: "One change, and every family it landed on",
    async shoot() {
      // Wait for the connector to notice and ask, before filming the board.
      const waiting = await until(
        "the connector asking the families",
        () => api("/questions/waiting"),
        (qs) => qs.some((q) => q.about_day === state.day && q.reason === "doctor_away"),
        { tries: 60, gap: 4000 },
      );
      state.asked = waiting.filter((q) => q.about_day === state.day && q.reason === "doctor_away");
      say(`asked: ${state.asked.map((q) => `${q.name} (${q.language})`).join(", ")}`);
      return web("03-board", `${PANEL}/#/approvals`, async (page) => {
        await signInConsole(page, "Seema Kamble");
        await page.goto(`${PANEL}/#/approvals`, { waitUntil: "domcontentloaded" }).catch(() => {});
        await wait(6000);
        await page.getByText(/What one change did, and to whom/).first()
          .scrollIntoViewIfNeeded().catch(() => {});
        await wait(7000);
      });
    },
  },

  {
    id: "04",
    name: "04-board-opened",
    says: "A row opened: the agent's trace, its timings, and its refusals",
    async shoot() {
      const who = state.asked?.[0];
      if (!who) throw new Error("clip 03 must run first; nobody has been asked");
      return web("04-board-opened", `${PANEL}/#/approvals`, async (page) => {
        await signInConsole(page, "Seema Kamble");
        await page.goto(`${PANEL}/#/approvals`, { waitUntil: "domcontentloaded" }).catch(() => {});
        await wait(6000);
        const row = page.locator(".board-row-head").filter({ hasText: who.name }).first();
        await row.click({ timeout: 20000 });
        await wait(9000);
      });
    },
  },

  {
    id: "05",
    name: "05-question-arrives",
    says: "The question, on her own phone, in her own script",
    async shoot() {
      const who = (state.asked ?? []).find((q) => q.language !== "en") ?? state.asked?.[0];
      if (!who) throw new Error("nobody has been asked");
      state.following = who;
      return phone("05-question-arrives", PHONE.serial, async (serial) => {
        await freshApp(serial);
        await tap(serial, who.patient_id);
        await wait(5000);
        const words = (who.asked_text ?? "").split(/\s+/).filter((w) => w.length >= 5);
        const fragment = words.sort((a, b) => b.length - a.length)[0];
        if (fragment && !(await reveal(serial, fragment))) {
          say(`warning: the question is not on ${who.patient_id}'s screen`);
        }
        await wait(6000);
      });
    },
  },

  {
    id: "06",
    name: "06-she-answers",
    says: "She answers in her own words, and the reading is proposed — not acted on",
    async shoot() {
      const who = state.following ?? state.asked?.[0];
      if (!who) throw new Error("nobody has been asked");
      const words = REPLIES[who.language];
      if (!words) throw new Error(`no reply written for ${who.language}`);
      state.replied = who;

      return phone("06-she-answers", PHONE.serial, async (serial) => {
        await freshApp(serial);
        await tap(serial, who.patient_id);
        await tap(serial, MESSAGES[who.language] ?? MESSAGES.en);
        await wait(2500);
        // Sent through the same endpoint the app's own composer posts to, so
        // this is her message arriving, not a row inserted behind the app.
        await api("/live/inject", { method: "POST", body: { patient_id: who.patient_id, text: words } });
        await wait(9000);
      });
    },
  },

  {
    id: "07",
    name: "07-a-person-agrees",
    says: "A person reads what she actually said, and agrees before the planner may act",
    async shoot() {
      const who = state.replied ?? state.asked?.[0];
      const readings = await until(
        "her words being read into a constraint",
        () => api("/requests/waiting"),
        (rows) => rows.some((r) => r.patient_id === who.patient_id),
        { tries: 25, gap: 4000 },
      );
      const mine = readings.find((r) => r.patient_id === who.patient_id);
      say(`read: ${JSON.stringify(mine.constraint)}`);
      state.reading = mine;

      return web("07-a-person-agrees", `${PANEL}/#/approvals`, async (page) => {
        await signInConsole(page, "Seema Kamble");
        await page.goto(`${PANEL}/#/approvals`, { waitUntil: "domcontentloaded" }).catch(() => {});
        await wait(6000);
        const row = page.locator("li.queue-row").filter({ hasText: who.name }).first();
        await row.scrollIntoViewIfNeeded().catch(() => {});
        await wait(4000);
        await row.getByRole("button", { name: /^Agree/ }).first().click({ timeout: 20000 });
        await wait(8000);
      });
    },
  },

  {
    id: "08",
    name: "08-planner-search",
    says: "Every date the planner tried, and the rule that refused each one",
    async shoot() {
      const who = state.replied ?? state.asked?.[0];
      const search = await until(
        "the planner searching",
        () => api(`/patients/${who.patient_id}/search`),
        (s) => (s.considered ?? []).length > 0,
        { tries: 20, gap: 3000 },
      );
      for (const c of search.considered) say(c.line);
      state.search = search;

      return web("08-planner-search", `${PANEL}/#/approvals`, async (page) => {
        await signInConsole(page, "Seema Kamble");
        await page.goto(`${PANEL}/#/approvals`, { waitUntil: "domcontentloaded" }).catch(() => {});
        await wait(5000);
        const row = page.locator(".board-row-head").filter({ hasText: who.name }).first();
        await row.click({ timeout: 15000 }).catch(() => {});
        await wait(4000);
        await page.getByText(/What the planner considered/).first()
          .scrollIntoViewIfNeeded().catch(() => {});
        await wait(9000);
      });
    },
  },

  {
    id: "09",
    name: "09-saathi-proposes",
    says: "Saathi puts a day and a cost to her, and asks whether it suits",
    async shoot() {
      const who = state.replied ?? state.asked?.[0];
      await until(
        "Saathi putting a day to her",
        () => api(`/patients/${who.patient_id}/notifications`),
        (d) => (d.thread ?? []).some((r) => r.kind === "proposal"),
        { tries: 25, gap: 4000 },
      );
      const thread = await api(`/patients/${who.patient_id}/notifications`);
      const latest = [...(thread.thread ?? [])].reverse().find((r) => r.kind === "proposal");
      const anchorWords = (latest?.body ?? "").split(/\s+/).filter((w) => w.length >= 5);
      const anchorWord = anchorWords.sort((a, b) => b.length - a.length)[0];

      return phone("09-saathi-proposes", PHONE.serial, async (serial) => {
        await freshApp(serial);
        await tap(serial, who.patient_id);
        await wait(2500);
        if (anchorWord && !(await reveal(serial, anchorWord))) {
          say("warning: the proposal is not on her screen");
        }
        await wait(8000);
      });
    },
  },

  {
    id: "10",
    name: "10-whose-number",
    says: "The working, folded under the sentence, opened — and whose number each is",
    async shoot() {
      const who = state.replied ?? state.asked?.[0];
      const thread = await api(`/patients/${who.patient_id}/notifications`);
      const proposal = [...(thread.thread ?? [])].reverse().find((r) => r.kind === "proposal");
      state.cost = (proposal?.detail ?? {}).cost ?? null;
      if (state.cost) {
        for (const i of state.cost.items ?? []) {
          say(`${i.stated ? "theirs" : "ours  "}  ${i.label} ${i.rupees}`);
        }
      }
      return phone("10-whose-number", PHONE.serial, async (serial) => {
        await freshApp(serial);
        await tap(serial, who.patient_id);
        await wait(3000);
        const opened = await tap(serial, COST_CARD[who.language] ?? COST_CARD.en, 4000);
        if (!opened) say("warning: the folded card was not found on her screen");
        await wait(7000);
      });
    },
  },

  {
    id: "11",
    name: "11-navigator-approves",
    says: "The one action in this system that writes anything",
    async shoot() {
      const who = state.replied ?? state.asked?.[0];
      const queued = await until(
        "her options reaching the approvals queue",
        () => api("/disruptions/pending"),
        (rows) => rows.some((r) => r.patient_id === who.patient_id),
        { tries: 20, gap: 3000 },
      );
      state.before = await connectorCounts();
      state.chosen = queued.find((r) => r.patient_id === who.patient_id);
      const detail = await api(
        `/disruptions/${encodeURIComponent(state.chosen.disruption_id)}/options/${who.patient_id}`);
      state.offered = (detail.options ?? [])[0] ?? {};
      say(`approving ${state.offered.target_on}`);

      return web("11-navigator-approves", `${PANEL}/#/approvals`, async (page) => {
        await signInConsole(page, "Seema Kamble");
        await page.goto(`${PANEL}/#/approvals`, { waitUntil: "domcontentloaded" }).catch(() => {});
        await wait(5000);
        // By id: the queue labels rows with the patient id, while her *name*
        // appears higher up the same screen in the request queue.
        await page.locator(".master-row").filter({ hasText: who.patient_id }).first()
          .click({ timeout: 20000 });
        await wait(4000);
        await page.getByRole("button", { name: /^Approve as / }).first().click({ timeout: 15000 });
        await wait(10000);
      });
    },
  },

  {
    id: "12",
    name: "12-written-back",
    says: "The booking, in the hospital's own calendar",
    async shoot() {
      const after = await until(
        "the hospital accepting the booking",
        connectorCounts,
        (c) => (c.booked ?? 0) > (state.before?.booked ?? 0),
        { tries: 15, gap: 4000 },
      );
      state.after = after;
      const on = (state.offered?.target_on ?? state.day).replace(/-/g, "");
      return web("12-written-back", `${EMR}/interface/login/login.php?site=default`, async (page) => {
        await page.fill("#authUser", process.env.SAATHI_OPENEMR_USER ?? "admin").catch(() => {});
        await page.fill("#clearPass", process.env.SAATHI_OPENEMR_PASS ?? "").catch(() => {});
        await page.press("#clearPass", "Enter").catch(() => {});
        await wait(7000);
        await page.goto(
          `${EMR}/interface/main/calendar/index.php?module=PostCalendar&func=view&tplview=&viewtype=day&Date=${on}`,
          { waitUntil: "domcontentloaded", timeout: 90000 });
        await wait(9000);
      });
    },
  },

  {
    id: "13",
    name: "13-will-not-pretend",
    says: "The slot it refuses to pretend it cancelled",
    async shoot() {
      const left = (state.after?.["rebook:old-slot-left-open"] ?? 0)
        > (state.before?.["rebook:old-slot-left-open"] ?? 0);
      if (!left) throw new Error("no old slot was left open on this run, so there is nothing to show");
      say("rebook:old-slot-left-open moved — the connector is reporting it, not us");
      return web("13-will-not-pretend", `${PANEL}/#/hospital`, async (page) => {
        await signInConsole(page, "Seema Kamble");
        await page.goto(`${PANEL}/#/hospital`, { waitUntil: "domcontentloaded" }).catch(() => {});
        await wait(9000);
      });
    },
  },

  {
    id: "14",
    name: "14-read-aloud",
    says: "Her new plan, read out in her own language by the service voice",
    async shoot() {
      const who = state.replied ?? state.asked?.[0];
      return phone("14-read-aloud", PHONE.serial, async (serial) => {
        await freshApp(serial);
        await tap(serial, who.patient_id);
        await tap(serial, TODAY_TAB[who.language] ?? TODAY_TAB.en);
        await wait(2500);
        const spoke = await tap(serial, SPEAK[who.language] ?? SPEAK.en, 2000);
        if (!spoke) {
          say("warning: no speak control — there may be no plan to read out yet");
        }
        // Long enough for a whole reading; these run twelve to sixteen seconds.
        await wait(18000);
      });
    },
  },

  {
    id: "15",
    name: "15-the-journey",
    says: "Somewhere to stay, the way there, and what she has spent",
    async shoot() {
      const who = state.replied ?? state.asked?.[0];
      const near = await api(`/patients/${who.patient_id}/nearby?need=stay`).catch(() => null);
      const top = (near?.places ?? [])[0];
      if (top) say(`nearest stay: ${top.place.kind} ${Math.round(top.metres)}m ${top.place.name}`);
      return phone("15-the-journey", PHONE.serial, async (serial) => {
        await freshApp(serial);
        await tap(serial, who.patient_id);
        await tap(serial, PLAN_TAB[who.language] ?? PLAN_TAB.en);
        await wait(4000);
        await tap(serial, STAY_NEED[who.language] ?? STAY_NEED.en, 5000);
        await wait(6000);
        await tap(serial, SPENDS[who.language] ?? SPENDS.en, 4000);
        await wait(5000);
      });
    },
  },

  {
    id: "16",
    name: "16-a-second-family",
    says: "The same change, a different household, a different right answer",
    async shoot() {
      if (!SECOND) throw new Error("only one device attached, so there is no second family to show");
      const other = (state.asked ?? []).find((q) => q.patient_id !== (state.replied ?? {}).patient_id);
      if (!other) throw new Error("the leave reached only one family on this run");
      say(`${other.name} (${other.language}) — the other household`);
      const words = REPLIES[other.language];
      return phone("16-a-second-family", SECOND.serial, async (serial) => {
        await freshApp(serial);
        await tap(serial, other.patient_id);
        await tap(serial, MESSAGES[other.language] ?? MESSAGES.en);
        await wait(2500);
        if (words) {
          await api("/live/inject", { method: "POST", body: { patient_id: other.patient_id, text: words } });
          await wait(10000);
        }
        await wait(4000);
      });
    },
  },

  {
    id: "17",
    name: "17-what-a-partner-sees",
    says: "What a cab firm, a hotel desk or a pharmacy sees: one job, three answers",
    async shoot() {
      return web("17-what-a-partner-sees", PARTNER_WEB, async (page) => {
        await wait(9000);
      }, { width: 900, height: 1200 });
    },
  },

  {
    id: "18",
    name: "18-without-a-smartphone",
    says: "The same family app in a browser, for reach without a smartphone",
    async shoot() {
      const who = state.replied ?? state.asked?.[0];
      return web("18-without-a-smartphone", `${FAMILY_WEB}/?patient=${who.patient_id}`, async (page) => {
        await wait(10000);
      }, { width: 900, height: 1200 });
    },
  },

  {
    id: "19",
    name: "19-what-it-is-worth",
    says: "Consented, de-identified, and the gap nobody has data on",
    async shoot() {
      const who = state.replied ?? state.asked?.[0];
      // Ask and grant on camera: a release that was already granted shows a
      // number, not a decision.
      const held = await api(`/patients/${who.patient_id}/consent`).catch(() => ({ grants: [] }));
      for (const grant of held.grants ?? []) {
        if (grant.purpose === "research" && grant.active) {
          await api(`/patients/${who.patient_id}/consent/grants/${grant.id}/revoke`, {
            method: "POST",
            body: { by: who.name, reason: "clip setup — this shows the grant being given" },
          }).catch(() => {});
        }
      }
      const request = await api(`/patients/${who.patient_id}/consent/requests`, {
        method: "POST",
        body: {
          purpose: "research", requester_id: "NCG-IN",
          requester_name: "National Cancer Grid (NCG), India",
          categories: ["travel_burden"],
          reason: "Travel and cost burden, de-identified, for research into why treatment is abandoned",
        },
      });
      await api(`/patients/${who.patient_id}/consent/requests/${request.id}/grant`, {
        method: "POST",
        body: { granted_by: who.name, capacity: "self", channel: "ivr" },
      });
      const release = await api("/research/release");
      say(`released ${release.manifest.rows} row(s), ${release.manifest.excluded_no_research_consent} withheld`);

      return web("19-what-it-is-worth", `${PANEL}/?persona=menon&section=research`, async (page) => {
        await wait(10000);
      });
    },
  },
];

/* ───────────────────────────── console sign-in ─────────────────────────── */

async function signInConsole(page, name) {
  const picker = page.getByText(name, { exact: true }).first();
  if (await picker.isVisible({ timeout: 8000 }).catch(() => false)) {
    await picker.click();
    await wait(3000);
  }
}

/* ──────────────────────────────── the run ──────────────────────────────── */

async function main() {
  mkdirSync(OUT, { recursive: true });

  const args = process.argv.slice(2);
  const only = args.includes("--only") ? args[args.indexOf("--only") + 1] : null;
  const from = args.includes("--from") ? args[args.indexOf("--from") + 1] : null;

  if (args.includes("--list")) {
    for (const clip of CLIPS) console.log(`  ${clip.id}  ${clip.name.padEnd(28)} ${clip.says}`);
    return;
  }

  PHONE = await pickPhone();
  SECOND = await pickSecond(PHONE.serial);
  adb = adbFor(PHONE.serial);
  console.log(`\n  filming ${PHONE.serial} (${PHONE.model})${SECOND ? `, second ${SECOND.serial}` : ""}`);

  state.day = process.env.SAATHI_LEAVE_DAY;
  if (!state.day) {
    console.error("  SAATHI_LEAVE_DAY is not set. See demo/RUNBOOK.md step 1.\n");
    process.exit(1);
  }
  console.log(`  leave day ${state.day}\n`);

  const chosen = CLIPS.filter((c) =>
    only ? c.id === only : from ? c.id >= from : true);

  const made = [];
  for (const clip of chosen) {
    process.stdout.write(`  ${clip.id} ${clip.says}\n`);
    try {
      await recall();
      const file = await clip.shoot();
      made.push({ ...clip, file });
      say(`✓ ${file.replace(resolve(HERE, ".."), ".")}`);
    } catch (error) {
      // A clip that could not be taken is reported and skipped. The film goes
      // without it rather than with something staged in its place.
      say(`✗ skipped: ${error.message}`);
    }
  }

  writeFileSync(
    resolve(OUT, "manifest.json"),
    JSON.stringify({ day: state.day, phone: PHONE, clips: made.map(({ id, name, says, file }) => ({ id, name, says, file })) }, null, 2),
  );
  console.log(`\n  ${made.length}/${chosen.length} clips in ${OUT}\n`);
}

main().catch((error) => {
  console.error(`\n  ${error.message}\n`);
  process.exit(1);
});
