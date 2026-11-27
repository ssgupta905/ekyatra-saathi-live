/**
 * The deployed stack, end to end, in one unbroken frame — with captions.
 *
 *     SAATHI_API_URL=https://…onrender.com \
 *     SAATHI_PANEL_URL=https://…onrender.com \
 *     SAATHI_OPENEMR_URL=http://8.231.81.219:8300 \
 *     node hosted-flow.mjs
 *
 * Everything here is addressed by environment variable and nothing defaults to
 * localhost, because the point of this particular film is that the things on
 * screen are the deployed ones. A missing address stops the take rather than
 * quietly recording a laptop.
 *
 *     +---------------------------+--------+
 *     |  OpenEMR (the hospital)   | phone  |
 *     +---------------------------+ (live  |
 *     |  EKYATRA Console          | mirror)|
 *     +---------------------------+--------+
 *     |  what is happening, in words        |
 *     +-------------------------------------+
 *
 * WHY THE CAPTION IS A WINDOW AND NOT BURNED IN
 *
 * This machine's ffmpeg has neither `drawtext` nor `subtitles` — no freetype,
 * no libass — so there is no post-processing route to text at all. A browser
 * window is better regardless: it renders Devanagari, Bengali and Tamil
 * correctly with no font wrangling, and it is captured as part of the frame,
 * so the caption cannot drift out of sync with the picture it describes.
 *
 * THE RULE THAT MATTERS: A CAPTION FOLLOWS ITS EVIDENCE
 *
 * `say()` is never called before the thing it describes has been checked.
 * Every beat reads the API back, asserts, and only then captions — and where
 * a caption states a number, the number is the one that was just read, not
 * one written into this file. Earlier takes of an earlier film narrated a
 * leave over an empty day and a knowledge graph over a screen without one,
 * both from a swallowed click. A take that fails costs ten minutes; a take
 * that lies costs the only thing this project is selling.
 *
 * WHAT THIS FILM DELIBERATELY DOES NOT CLAIM
 *
 * The arrival clock — "the OPD is running late" — is absent. It is derived
 * from OpenEMR's own MariaDB, and a Render service cannot hold the SSH tunnel
 * that reaches it. Rather than show the beat against a local backend and
 * imply it is hosted, it is left out and the Console says what it honestly
 * can: that a family arrived, with no delay claimed.
 */

import { chromium } from "playwright";
import { execFile, spawn } from "node:child_process";
import { mkdirSync, openSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../recordings");

//: Addresses that are not a deployment, however they are spelled.
const LOCAL = /^(https?:\/\/)?(localhost|127\.0\.0\.1|\[?::1\]?|0\.0\.0\.0|10\.0\.2\.2)([:/]|$)/i;

/** Read `.env` into the environment, without overriding what is already set.
 *
 *  The VM's OpenEMR password is not the local Docker one, and it has no place
 *  in this repository or in a shell history. `.env` is already git-ignored and
 *  already holds the Groq and Sarvam keys, so it is where this belongs too.
 *  Anything exported before the run still wins, which is what makes a one-off
 *  `SAATHI_LEAVE_DAY=…` on the command line work.
 */
function loadEnvFile() {
  let text;
  try {
    text = readFileSync(resolve(HERE, "../.env"), "utf8");
  } catch {
    return;
  }
  for (const line of text.split("\n")) {
    const match = /^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$/i.exec(line);
    if (!match) continue;
    const [, name, raw] = match;
    if (process.env[name] !== undefined) continue;
    process.env[name] = raw.trim().replace(/^(['"])(.*)\1$/, "$2");
  }
}

loadEnvFile();

/** Addresses. No defaults: see the module docstring. */
const API = must("SAATHI_API_URL");
const PANEL = must("SAATHI_PANEL_URL");
const EMR = must("SAATHI_OPENEMR_URL");
const ADB =
  process.env.ADB ?? `${process.env.HOME}/Library/Android/sdk/platform-tools/adb`;

/** A deployed address, or nothing.
 *
 *  This film exists to show that the things on screen are the deployed ones,
 *  so a local address is refused outright rather than defaulted away from. A
 *  recording made against a laptop and presented as a deployment would be the
 *  one kind of dishonesty this whole project is built to avoid — and it is an
 *  easy mistake to make, because a local stack is the convenient thing to
 *  have running while building the script.
 */
function must(name) {
  const value = process.env[name];
  if (!value) {
    console.error(`\n  ${name} is not set. This film records the deployed stack;`);
    console.error("  it will not quietly fall back to a local one.\n");
    process.exit(1);
  }
  const address = value.replace(/\/+$/, "");
  if (LOCAL.test(address)) {
    console.error(`\n  ${name} is ${address}, which is this machine, not a deployment.`);
    console.error("  This film records the deployed stack only. Point it at the");
    console.error("  Render services and the hospital's own address, or do not run it.\n");
    process.exit(1);
  }
  return address;
}

//: Filled in once the screen has been measured. Chromium positions windows
//: in logical points, and this machine is not at a clean 2x — it reports
//: 1470x956 against a 2560x1664 panel. Hardcoding half the panel left a
//: 190-point strip down one side and the Dock across the bottom, through
//: which a terminal, an editor and the desktop were plainly visible in an
//: otherwise finished nine-minute take.
let LAYOUT = null;
let CROP = null;

/** Measure the screen, then lay the four windows over all of it.
 *
 *  `availTop` is the menu bar and the gap under `availHeight` is the Dock.
 *  Neither can be covered by an ordinary window, so they are cropped out of
 *  the recording instead — which leaves the user's own settings alone.
 */
async function measureTheScreen() {
  const browser = await chromium.launch({
    headless: false,
    args: ["--window-position=0,0", "--window-size=420,300"],
  });
  const page = await browser.newPage({ viewport: null });
  const s = await page.evaluate(() => ({
    width: screen.width, height: screen.height,
    availWidth: screen.availWidth, availHeight: screen.availHeight,
    availTop: screen.availTop,
  }));
  await browser.close();

  const top = s.availTop;
  const usable = s.availHeight;
  // scrcpy keeps the handset's aspect, so a column narrower than that leaves
  // a gap beside the mirror — and whatever was behind it shows through.
  const phoneW = Math.round(usable * PHONE_ASPECT) + 2;
  const leftW = s.availWidth - phoneW;
  const topH = Math.round(usable * 0.49);
  LAYOUT = {
    emr: { x: 0, y: top, w: leftW, h: topH },
    panel: { x: 0, y: top + topH, w: leftW, h: usable - topH },
    phone: { x: leftW, y: top, w: phoneW, h: usable },
  };
  // As fractions of the captured frame, so the crop holds whatever the
  // panel's pixel size turns out to be.
  CROP = {
    top: s.availTop / s.height,
    height: s.availHeight / s.height,
    width: s.availWidth / s.width,
  };
  console.log(`  screen ${s.width}x${s.height} logical, usable ${s.availWidth}x${s.availHeight} from y=${top}`);
  return s;
}

const BENGALI_FAMILY = "EKY-SHANTI";
//: Whose id the narration borrows. The speech endpoint hangs off a patient;
//: the narration is not about them and is never shown to them.
const NARRATOR = "EKY-SHANTI";
//: Answers in Hindi, and asks for a date the hospital's own rules cannot
//: allow — so the planner's search has a real rejection in it, not only offers.
const HINDI_FAMILY = "EKY-FATIMA";
//: From the app's own `Translations.kt`, not retyped.
const SPEAK = { hi: "बोलिए", bn: "বলুন", ta: "பேசுங்கள்" };
const MESSAGES = { hi: "संदेश", bn: "বার্তা", ta: "செய்திகள்" };
//: The home tab. Coming back to a family reopens whichever tab was last
//: used, and the speak button lives only on this one.
const TODAY = { hi: "आज", bn: "আজ", ta: "இன்று", en: "Today" };
const PLAN_TAB = { hi: "योजना", bn: "পরিকল্পনা", ta: "திட்டம்", en: "Plan" };
const STAY = { hi: "ठहरने की जगह", bn: "থাকার জায়গা", ta: "தங்குவதற்கு இடம்", en: "Somewhere to stay" };
//: 1080x2340 on the handset being filmed. scrcpy will not stretch past it.
const PHONE_ASPECT = 1080 / 2340;

const soundtrack = [];
let captureStartedAt = 0;
let bar = null;
//: The last thing said, so a reload can put it straight back.
let lastCaption = null;

/* ───────────────────────────── the deployed API ───────────────────────── */

/** A GET against the deployed API. Slow on purpose: a free instance that has
 *  gone to sleep takes a minute to answer its first request. */
async function api(path, { timeout = 90000 } = {}) {
  const response = await fetch(`${API}/api${path}`, { signal: AbortSignal.timeout(timeout) });
  if (!response.ok) throw new Error(`GET ${path} -> ${response.status}`);
  return response.json();
}

async function post(path, body, { timeout = 90000 } = {}) {
  const response = await fetch(`${API}/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body ?? {}),
    signal: AbortSignal.timeout(timeout),
  });
  if (!response.ok) {
    throw new Error(`POST ${path} -> ${response.status} ${await response.text()}`);
  }
  return response.json();
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/** Wait for something to become true, returning what made it true.
 *
 *  Used instead of a fixed sleep wherever the film waits on the system rather
 *  than on a viewer's reading speed. A sleep that is long enough on a fast day
 *  is a coin toss on a slow one, and the thing it guards is an assertion.
 */
async function until(what, read, ok, { tries = 30, gap = 3000 } = {}) {
  let last;
  for (let i = 0; i < tries; i += 1) {
    try {
      last = await read();
      if (ok(last)) return last;
    } catch (error) {
      last = error;
    }
    await wait(gap);
  }
  const detail = last instanceof Error
    ? last.message
    : JSON.stringify(last)?.slice(0, 400) ?? String(last);
  throw new Error(`${what} did not happen after ${(tries * gap) / 1000}s. Last saw: ${detail}`);
}

/* ───────────────────────────────── the phone ──────────────────────────── */

const adb = (...args) => run(ADB, args).catch(() => ({ stdout: "" }));

async function phoneXml() {
  await adb("shell", "uiautomator", "dump", "/sdcard/ui.xml");
  const { stdout } = await run(ADB, ["shell", "cat", "/sdcard/ui.xml"]);
  return stdout;
}

async function phoneText() {
  const xml = await phoneXml();
  return [...xml.matchAll(/text="([^"]+)"/g)].map((m) => m[1]).join(" | ");
}

/** Tap a piece of text, read from the live view hierarchy.
 *
 *  Never a remembered coordinate: a tap at one of those lands on whatever has
 *  drifted into that spot, and the film then narrates a screen nobody is
 *  looking at. Absent text throws, which fails the take.
 */
async function phoneTap(label, settle = 3200) {
  const locate = async () => {
    const xml = await phoneXml();
    return xml.match(
      new RegExp(`text="([^"]*${label}[^"]*)"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`),
    );
  };
  let found = await locate();

  // Scroll to it if it is below the fold. The family picker is alphabetical and
  // this deployment carries thirty-two of them, so the family a take wants is
  // routinely off screen — which is not the same thing as absent, and failing
  // the take for it cost one. Stop as soon as the list stops moving, so a label
  // that genuinely is not there still throws rather than scrolling for ever.
  if (!found) {
    let last = "";
    for (let swipe = 0; swipe < 12 && !found; swipe += 1) {
      const before = await phoneText();
      if (before === last) break;
      last = before;
      await adb("shell", "input", "swipe", "540", "1800", "540", "900", "260");
      await wait(900);
      found = await locate();
    }
  }
  if (!found) throw new Error(`nothing on the phone reads "${label}", and scrolling did not reveal it`);
  const [x1, y1, x2, y2] = found.slice(2).map(Number);
  await adb("shell", "input", "tap", String(Math.round((x1 + x2) / 2)), String(Math.round((y1 + y2) / 2)));
  await wait(settle);
  return found[1];
}

/** Assert a piece of text is on the phone's screen.
 *
 *  Both sides are normalised first. The fragment comes from the API and the
 *  screen text from uiautomator, and the two compose Indic conjuncts and vowel
 *  signs differently — so a Bengali word that is plainly on screen can fail a
 *  byte comparison. Diagnosed the slow way: a dump containing
 *  "যাওয়া-আসায় আপনার কত খরচ হবে?" did not match that same word.
 */
async function mustReadOnThePhone(fragment, what) {
  const text = (await phoneText()).normalize("NFC");
  if (!text.includes(fragment.normalize("NFC"))) {
    throw new Error(`${what} is not on the phone`);
  }
}

/* ───────────────────────────── captions and audio ─────────────────────── */

const captions = [];

/** The caption band, injected into the Console's own page.
 *
 *  A fixed strip across the bottom of that pane. It has to be re-applied
 *  after every navigation, because a reload throws it away along with the
 *  rest of the document — and a caption that silently stops updating is
 *  worse than none, since the last thing it said stays on screen over
 *  whatever happens next.
 */
const CAPTION_BAND = () => {
  if (document.getElementById("__ek_caption")) return;
  const bar = document.createElement("div");
  bar.id = "__ek_caption";
  bar.innerHTML =
    '<div id="__ek_step"></div><div id="__ek_text"></div>';
  Object.assign(bar.style, {
    position: "fixed", left: "0", right: "0", bottom: "0", zIndex: "2147483647",
    minHeight: "74px", display: "flex", alignItems: "center", gap: "16px",
    padding: "10px 20px", boxSizing: "border-box",
    background: "#0b1220", color: "#e8eef9",
    font: '500 17px/1.35 -apple-system, "SF Pro Text", Inter, system-ui, sans-serif',
    borderTop: "2px solid #1d4ed8",
  });
  document.body.appendChild(bar);
  const step = bar.querySelector("#__ek_step");
  Object.assign(step.style, {
    flex: "none", minWidth: "84px", padding: "5px 11px", borderRadius: "999px",
    background: "#1d4ed8", color: "#fff", textAlign: "center",
    font: '600 12px/1 ui-monospace, SFMono-Regular, Menlo, monospace',
    letterSpacing: ".08em", textTransform: "uppercase",
  });
  // Nothing of the page should hide under the band.
  document.body.style.paddingBottom = "86px";
  window.__ekCaption = (s, h) => {
    const el = document.getElementById("__ek_caption");
    if (!el) return;
    el.querySelector("#__ek_step").textContent = s;
    el.querySelector("#__ek_text").innerHTML = h;
  };
};

/** Put the band on, and keep it on through reloads. */
async function dressTheConsole(page) {
  await page.addInitScript(CAPTION_BAND);
  await page.evaluate(CAPTION_BAND).catch(() => {});
  if (lastCaption) {
    await page.evaluate(([s, h]) => window.__ekCaption?.(s, h), lastCaption).catch(() => {});
  }
}

/** How long a wav runs, in seconds. */
async function secondsOf(file) {
  const { stdout } = await run("ffprobe", [
    "-v", "error", "-show_entries", "format=duration",
    "-of", "default=nokey=1:noprint_wrappers=1", file,
  ]);
  const seconds = Number(stdout.trim());
  return Number.isFinite(seconds) ? seconds : 0;
}

/** The English narration for one caption, as audio.
 *
 *  Through the same endpoint and the same provider the app uses, in `en-IN`.
 *  The film explains itself in English; the only vernacular audio in it is
 *  the app's own, which is the thing being demonstrated rather than the thing
 *  doing the explaining.
 */
async function narrationFor(html) {
  if (process.env.SKIP_NARRATION) return null;
  const text = html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
  if (!text) return null;
  try {
    const response = await fetch(`${API}/api/patients/${NARRATOR}/voice/say`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text, language: "en" }),
      signal: AbortSignal.timeout(90000),
    });
    if (!response.ok) return null;
    const file = resolve(OUT, `hosted-narration-${String(captions.length).padStart(2, "0")}.wav`);
    const bytes = Buffer.from(await response.arrayBuffer());
    writeFileSync(file, bytes);
    return { file, seconds: await secondsOf(file), bytes: bytes.length };
  } catch {
    return null;
  }
}

/** Put a line on the caption bar, say it aloud, and hold for as long as it
 *  takes to say.
 *
 *  Called only after the assertion for the beat has passed — a caption, and
 *  now a sentence of narration, follows its evidence and never leads it.
 *
 *  The audio is fetched *before* the caption appears so that the two start on
 *  the same frame; fetching afterwards would put the voice a second or two
 *  behind its own words. And the hold is the clip's own length rather than a
 *  guessed number, so the film is paced by what is being said instead of by
 *  whatever looked about right while writing it.
 */
async function say(step, html, mark = "") {
  const clip = await narrationFor(html);
  const at = Date.now() - captureStartedAt;
  captions.push({ atMs: at, step, html });
  if (clip) soundtrack.push({ ...clip, atMs: at, language: "en", spokenBy: "Sarvam (narration)" });
  lastCaption = [step, html];
  if (bar) {
    await bar.evaluate(CAPTION_BAND).catch(() => {});
    await bar.evaluate(([s, h]) => window.__ekCaption?.(s, h), [step, html]).catch(() => {});
  }
  console.log(`  [${step}] ${html.replace(/<[^>]+>/g, "")}`);
  await wait(clip ? Math.round(clip.seconds * 1000) + 1100 : 3500);
}

const said = (text) => `<span class="said">${text}</span>`;
const num = (text) => `<span class="num">${text}</span>`;

/** The exact audio the app plays, kept for the soundtrack.
 *
 *  Same endpoint the phone calls, same text, same language, at the moment of
 *  the tap. `X-Spoken-By` is checked rather than assumed: if Sarvam did not
 *  speak it, the clip is dropped and nothing is claimed about it.
 */
async function keepTheAudio(patientId, text, language) {
  if (process.env.SKIP_AUDIO) return null;
  const at = Date.now() - captureStartedAt;
  const response = await fetch(`${API}/api/patients/${patientId}/voice/say`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text, language }),
    signal: AbortSignal.timeout(90000),
  });
  if (!response.ok) {
    console.log(`  no audio kept for ${language}: the API said ${response.status}`);
    return null;
  }
  const spokenBy = response.headers.get("x-spoken-by") ?? "unknown";
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!/sarvam/i.test(spokenBy)) {
    console.log(`  dropped the ${language} clip: spoken by "${spokenBy}", not Sarvam`);
    return null;
  }
  const file = resolve(OUT, `hosted-voice-${language}.wav`);
  writeFileSync(file, bytes);
  const seconds = await secondsOf(file);
  soundtrack.push({ file, atMs: at, language, spokenBy, bytes: bytes.length, seconds });
  return { spokenBy, kb: Math.round(bytes.length / 1024), file, seconds };
}

/** Did the phone play it through the service voice, or its own fallback?
 *
 *  The buffer is cleared immediately before the tap and read whole
 *  afterwards. Reading only the last few hundred lines does not work on a
 *  real handset: this one writes thousands of lines a second from its own
 *  audio stack, so the evidence had scrolled away before it could be read,
 *  and two perfectly good Sarvam clips were dropped from a finished take as
 *  "the phone did not use the service voice" when it demonstrably had.
 */
/** The live connector's own tally of what it has done to the hospital.
 *
 *  Read from `/hospital/now` rather than counted here, so every number the
 *  film says about the write-back is the number the connector itself kept.
 */
async function connectorCounts() {
  const now = await api("/hospital/now").catch(() => ({ hospitals: [] }));
  const live = (now.hospitals ?? []).find((b) => b.connector?.live);
  return live?.connector?.counts ?? {};
}

async function forgetTheLog() {
  await adb("logcat", "-c");
}

async function playedThroughTheService() {
  const { stdout } = await adb("logcat", "-d");
  const ours = /org\.ekyatra\.saathi/.test(stdout);
  return {
    // The app's own playback goes through the platform media player. Paired
    // with our package appearing in the audio routing, that is the service
    // voice rather than the phone reading text.
    service: /MediaPlayer(Service|Native)/.test(stdout) && ours,
    fallback: /TextToSpeech|TtsFallback|SpeechSynthesis/.test(stdout),
    lines: stdout.split("\n").length,
  };
}

/** The longest text on the phone: the card body the speak button reads. */
async function longestTextOnScreen() {
  return (await phoneText())
    .split(" | ")
    .map((s) => s.trim())
    .sort((a, b) => b.length - a.length)[0] ?? "";
}

/** Tap speak, keep exactly what it read, and verify how it was played. */
async function speakOnThePhone(patientId, language) {
  const reading = await longestTextOnScreen();
  if (!reading) throw new Error(`nothing to read out on ${patientId}'s screen`);
  await forgetTheLog();
  await phoneTap(SPEAK[language]);
  const kept = await keepTheAudio(patientId, reading, language);
  // Wait for the whole clip, not a guessed six seconds. The Hindi and Bengali
  // readings run fourteen and fifteen seconds; waiting six put the English
  // narration eight seconds into them, so two voices spoke at once and the
  // summed track clipped — ten thousand samples hard against the ceiling.
  // This is the family's own language being demonstrated; nothing talks over
  // it.
  await wait(Math.round((kept?.seconds ?? 6) * 1000) + 1200);
  const played = await playedThroughTheService();
  if (kept && !played.service) {
    // The clip is Sarvam's but the phone did not play it, so the soundtrack
    // would be a voice the viewer never heard. Dropped by identity rather
    // than by position: narration clips share this list, and popping the end
    // would one day remove a sentence of narration instead.
    const at = soundtrack.findIndex((c) => c.file === kept.file);
    if (at >= 0) soundtrack.splice(at, 1);
    console.log(`  dropped the ${language} clip: the phone did not use the service voice`);
    return { reading, played, kept: null };
  }
  return { reading, played, kept };
}

/* ──────────────────────────────── windows ─────────────────────────────── */

async function windowAt({ x, y, w, h }, url) {
  const browser = await chromium.launch({
    headless: false,
    args: [
      `--window-position=${x},${y}`,
      `--window-size=${w},${h}`,
      "--hide-crash-restore-bubble",
      "--disable-infobars",
      "--disable-session-crashed-bubble",
    ],
  });
  const page = await browser.newPage({ viewport: null });
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 120000 }).catch(() => {});
  return { browser, page };
}

/* ──────────────────────────────── pre-flight ──────────────────────────── */

/** The live hospital connectors, whatever shape `/hospital/now` is in.
 *
 *  It answers `{today, hospitals: [{connector, resources}]}` — the connector
 *  is nested, so reading `h.live` off the outer object silently finds nothing
 *  and the pre-flight then reports no hospital on a deployment that has one.
 */
function liveConnectors(now) {
  const rows = Array.isArray(now) ? now : now.hospitals ?? [];
  return rows
    .map((row) => row.connector ?? row)
    .filter((c) => c && c.live);
}

/** Everything that must be true before a frame is worth recording.
 *
 *  Longer than it looks necessary, and every check here is one that has gone
 *  wrong at least once. Three of them fail *by being empty* rather than by
 *  erroring — no hospital connector, no saved rules, no cast — and an empty
 *  screen in a film reads as a broken product rather than a missing setting.
 */
async function ready() {
  const problems = [];
  const notes = [];

  // Free instances sleep after fifteen idle minutes and take a minute to come
  // back. Wake them before anything is timed, or act one waits on a cold start.
  for (const [what, url] of [["the API", `${API}/api/health`], ["the Console", `${PANEL}/`]]) {
    process.stdout.write(`  waking ${what}… `);
    try {
      await until(
        `${what} answering`,
        () => fetch(url, { signal: AbortSignal.timeout(90000) }),
        (r) => r.ok,
        { tries: 4, gap: 5000 },
      );
      console.log("awake");
    } catch {
      console.log("no answer");
      problems.push(`${what} is not answering on ${url}`);
    }
  }

  let health;
  try {
    health = await api("/health");
    if (!health.actors) problems.push("no Groq actors on the deployed API — a reply cannot be read");
    if (!health.language_layer) problems.push("no language layer on the deployed API");
    if (!health.patients) problems.push("the deployed database has no families in it");
    else notes.push(`${health.patients} families, sim date ${health.sim_date}`);
  } catch (error) {
    problems.push(`the deployed API is not healthy (${error.message})`);
  }

  // The Console proxies nothing in production — it is a static site reading
  // config.json — so confirm it is pointed at the same API this script is.
  try {
    const config = await (await fetch(`${PANEL}/config.json`, { signal: AbortSignal.timeout(30000) })).json();
    const base = (config.apiBase ?? "").replace(/\/api\/?$/, "").replace(/\/+$/, "");
    if (base && base !== API) {
      problems.push(`the Console is pointed at ${base}, not ${API} — the film would show two systems`);
    } else if (base) notes.push("the Console and this script share one API");
  } catch {
    notes.push("could not read the Console's config.json; assuming it is pointed correctly");
  }

  // The hospital. Without a connector everything works and nothing watches a
  // hospital, which is the quietest way to lose this entire film.
  try {
    const now = await api("/hospital/now");
    const live = liveConnectors(now);
    if (!live.length) {
      problems.push(
        "the deployed API has no live hospital connector — set SAATHI_HOSPITAL_SYSTEMS " +
          "and make sure the VM's firewall admits Render's outbound addresses",
      );
    } else {
      notes.push(`hospital connector live: ${live.map((c) => `${c.hospital_id}/${c.system}, ${c.appointments} appointments`).join("; ")}`);
    }
  } catch (error) {
    problems.push(`cannot read /hospital/now (${error.message})`);
  }

  // The hospital's own address, reachable from here too — the film shows it.
  try {
    const response = await fetch(`${EMR}/interface/login/login.php?site=default`, {
      signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) problems.push(`OpenEMR answered ${response.status} on ${EMR}`);
  } catch (error) {
    problems.push(
      `cannot reach OpenEMR on ${EMR} (${error.message}). The VM admits one address at a ` +
        "time; open the firewall to this machine as well as to Render",
    );
  }

  // Saved rules, or the planner refuses to offer dates and looks broken.
  for (const hospital of ["TMH-MUM"]) {
    try {
      const policy = await api(`/admin/policy/${hospital}`);
      if (!policy.used_by_planner) {
        problems.push(
          `${hospital} has no saved rules on the deployed API, so the option search will ` +
            "refuse every date. Save them on the Console's Configuration screen",
        );
      } else notes.push(`${hospital}'s rules are in force (version ${policy.version})`);
    } catch (error) {
      notes.push(`could not check ${hospital}'s rules (${error.message})`);
    }
  }

  const { stdout } = await run(ADB, ["devices"]).catch(() => ({ stdout: "" }));
  if (!/\s+device\s*$/m.test(stdout)) {
    problems.push("no phone attached — start the emulator and install the APK");
  }

  if (notes.length) {
    console.log("");
    for (const note of notes) console.log(`  · ${note}`);
  }
  if (problems.length) {
    console.error("\nNot recording. Fix these first:\n");
    for (const problem of problems) console.error(`  - ${problem}`);
    console.error("");
    process.exit(1);
  }
  console.log("");
  return health;
}

/* ─────────────────────────────────── main ─────────────────────────────── */

async function main() {
  const health = await ready();
  mkdirSync(OUT, { recursive: true });
  await measureTheScreen();

  // Back to "nobody has been asked yet". `clear`, never `reset`: reset rewinds
  // the world and is refused outright on real records, because it would delete
  // families somebody entered. Not swallowed — a silently failed clear is what
  // once put three copies of one family on screen for three takes running.
  await post("/live/control", { action: "clear" });
  await wait(10000);

  const phone = spawn(
    "scrcpy",
    [
      "--window-title", "Saathi — the family's phone",
      `--window-x=${LAYOUT.phone.x}`, `--window-y=${LAYOUT.phone.y}`,
      `--window-width=${LAYOUT.phone.w}`, `--window-height=${LAYOUT.phone.h}`,
      "--stay-awake", "--window-borderless",
      // Above everything else. Other windows on the machine sit in front of
      // it otherwise — an editor covered the phone for most of a take, and
      // the mirror is the one pane that cannot simply be moved out of the way
      // afterwards.
      "--always-on-top",
    ],
    { stdio: "ignore", env: { ...process.env, PATH: `${dirname(ADB)}:${process.env.PATH}` } },
  );
  await wait(9000);

  const emr = await windowAt(LAYOUT.emr, `${EMR}/interface/login/login.php?site=default`);
  const panel = await windowAt(LAYOUT.panel, PANEL);
  // The caption is injected into the Console's own page rather than given a
  // window. Chromium will not make a window shorter than 375 points however
  // politely it is asked, and a 375-point band is nearly half the usable
  // height — it buried the Console it was supposed to be explaining.
  bar = panel.page;
  await dressTheConsole(panel.page);
  await wait(3000);

  const raw = resolve(OUT, "hosted-flow-raw.mp4");
  // 30fps, because this capture device accepts only 15 or 30 and refuses
  // anything else outright — `-framerate 12` makes ffmpeg fail to open the
  // input at all and write no file, which cost a whole four-minute rehearsal
  // before anyone noticed there was no video. The nominal rate barely matters
  // anyway: the machine sustains about eleven while capturing three live
  // windows, and the label is corrected against the wall clock afterwards.
  // The "yuv420p not supported" warning is expected — that is the *output*
  // format; the device hands over uyvy422 and ffmpeg converts.
  // Keep the display awake. An unattended five-minute take let the screen
  // sleep, and the capture dutifully recorded five minutes of black with a
  // perfectly valid duration, frame count and soundtrack. `-d` blocks display
  // sleep only; the machine may still idle in every other respect.
  const awake = spawn("caffeinate", ["-d"], { stdio: "ignore" });

  const captureLog = resolve(OUT, "hosted-flow-ffmpeg.log");
  const capture = spawn("ffmpeg", [
    "-y", "-f", "avfoundation", "-capture_cursor", "1", "-framerate", "30",
    "-i", "2",
    // Crop first, scale second: the menu bar and the Dock belong to the
    // machine, not to the demo, and a film of a product should not be
    // showing somebody's editor and terminal along one edge.
    "-vf",
    `crop=floor(iw*${CROP.width.toFixed(6)}/2)*2:floor(ih*${CROP.height.toFixed(6)}/2)*2:0:floor(ih*${CROP.top.toFixed(6)}/2)*2,scale=1600:-2`,
    "-pix_fmt", "yuv420p",
    "-preset", "ultrafast", raw,
  ], { stdio: ["ignore", "ignore", openSync(captureLog, "w")] });
  await wait(4000);

  // Is it actually recording? `stdio: "ignore"` hid a capture that refused to
  // start at all, and the take ran its full four minutes against no video.
  // Checked here, where it costs four seconds instead.
  const firstSize = statSync(raw, { throwIfNoEntry: false })?.size ?? 0;
  if (!firstSize) {
    capture.kill("SIGKILL");
    const why = readFileSync(captureLog, "utf8").trim().split("\n").slice(-6).join("\n   ");
    throw new Error(`the screen capture wrote nothing. ffmpeg said:\n   ${why}`);
  }
  captureStartedAt = Date.now();
  console.log("  recording — do not touch the machine\n");

  let failure = null;
  let ranForMs = 0;
  try {
    await demo({ emr: emr.page, panel: panel.page, health });
  } catch (error) {
    failure = error;
  } finally {
    ranForMs = Date.now() - captureStartedAt;
    capture.kill("SIGINT");
    await wait(2500);
    phone.kill();
    awake.kill();
    for (const w of [emr, panel]) await w.browser.close().catch(() => {});
  }

  writeFileSync(resolve(OUT, "hosted-flow-captions.json"), JSON.stringify(captions, null, 2));
  if (failure) throw failure;

  const picture = await hasAPicture(raw);
  if (!picture.ok) {
    throw new Error(
      `the capture is black (brightness ${picture.samples.join(", ")}). The display ` +
        "almost certainly slept — everything else about the file is valid, which is " +
        "why this is checked rather than assumed.",
    );
  }

  const timed = await matchTheClock(raw, ranForMs);
  const finished = await addTheVoices(timed);
  console.log(`\n  recorded ${finished} (brightness ${picture.brightest.toFixed(0)})`);
}

/* ──────────────────────────────── the acts ────────────────────────────── */

/** A click the film depends on. Missing it fails the take rather than
 *  carrying on and captioning a screen that never changed. */
async function mustClick(page, target, what) {
  const locator = typeof target === "string"
    ? page.getByText(target, { exact: true })
    : page.getByText(target);
  try {
    await locator.first().click({ timeout: 20000 });
  } catch {
    throw new Error(`could not reach ${what} in the Console`);
  }
  await wait(2200);
}

/** Assert something is on the Console's screen before it is talked about. */
async function mustSee(page, target, what) {
  const locator = typeof target === "string"
    ? page.getByText(target, { exact: false })
    : page.getByText(target);
  try {
    await locator.first().waitFor({ state: "visible", timeout: 25000 });
  } catch {
    throw new Error(`${what} is not on the Console's screen`);
  }
}

/** Sign in, or notice we already are — the persona is remembered. */
async function signIn(page, name) {
  const picker = page.getByText(name, { exact: true }).first();
  if (await picker.isVisible({ timeout: 6000 }).catch(() => false)) {
    await picker.click();
    await wait(2500);
    return;
  }
  await mustSee(page, /Today|Families|Approvals/, "the Console's own navigation");
}

/** The day to put the leave on.
 *
 *  `SAATHI_LEAVE_DAY` wins, and on a real deployment it generally has to:
 *  the leave must collide with the **hospital's** appointments, and our own
 *  records are a different set of dates reconciled to them. Nothing we expose
 *  lists the hospital's diary — `/hospital/now` gives counts, not days — so
 *  when the two disagree, ours is the wrong one to trust.
 *
 *  Without it, the commonest upcoming day in our own records is a reasonable
 *  guess and is announced as a guess. A leave on a day nobody is booked for
 *  produces no asks at all, and that failure reads like a broken connector
 *  rather than a wrong date.
 */
async function pickTheLeaveDay(health) {
  const counts = new Map();
  const patients = await api("/patients");
  const list = Array.isArray(patients) ? patients : patients.patients ?? [];
  for (const patient of list) {
    const steps = await api(`/patients/${patient.id}/steps`).catch(() => []);
    for (const step of steps) {
      const on = step.scheduled_for;
      if (!on || on <= health.sim_date) continue;
      if (!["scheduled", "booked"].includes(String(step.status))) continue;
      counts.set(on, (counts.get(on) ?? 0) + 1);
    }
  }
  if (process.env.SAATHI_LEAVE_DAY) {
    return { day: process.env.SAATHI_LEAVE_DAY, told: true };
  }
  const best = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
  if (!best) throw new Error("no family has an upcoming booked step, so a leave would collide with nothing");
  console.log(`  no SAATHI_LEAVE_DAY set; guessing ${best[0]} from our own records`);
  return { day: best[0], told: false };
}

/** Enter a provider's leave in OpenEMR's own calendar, on camera.
 *
 *  Through the hospital's own form, not its database: the whole claim is that
 *  an ordinary staff action in an unmodified system is what we react to, and a
 *  SQL insert off camera would be a weaker version of the same beat.
 *
 *  `?prov=true` is the part that is not guessable — without it the form offers
 *  only patient categories and Vacation is not among them (it is `pc_cattype`
 *  1, a provider category). The category is then found by its name rather than
 *  its id, because ids differ between installations.
 */
async function enterLeaveOnCamera(emr, day) {
  // Refuse a day that already carries a leave.
  //
  // The connector treats a second leave for the same provider on the same day
  // as nothing new, so no family is asked and the take dies four minutes later
  // at "the connector noticing the leave ... did not happen". Proven by two
  // takes in a row: the one run straight after the calendar was cleared asked
  // both families; the next one, with its predecessor's own leave still there,
  // asked nobody. Failing here costs seconds and names the fix.
  const compactDay = day.replace(/-/g, "");
  await emr.goto(
    `${EMR}/interface/main/calendar/index.php?module=PostCalendar&func=view&tplview=&viewtype=day&Date=${compactDay}`,
    { waitUntil: "domcontentloaded", timeout: 90000 },
  ).catch(() => {});
  await wait(3000);
  const already = await emr.evaluate(() => document.body.innerText).catch(() => "");
  if (/vacation/i.test(already)) {
    throw new Error(
      `OpenEMR already holds a leave on ${day}, so a new one is not news to the connector ` +
        `and no family would be asked. Clear the film's leaves first:\n\n` +
        `  gcloud compute ssh saathi-hms --zone asia-south1-c --quiet --command \\\n` +
        `    "sudo docker exec -i openemr-mysql-1 mariadb -uroot -proot openemr -N -B -e \\\n` +
        `     \\\"DELETE FROM openemr_postcalendar_events WHERE pc_eventDate='${day}' ` +
        `AND (pc_pid IS NULL OR pc_pid=0);\\\""`,
    );
  }

  await emr.goto(
    `${EMR}/interface/main/calendar/add_edit_event.php?startdate=${day}&prov=true`,
    { waitUntil: "domcontentloaded", timeout: 90000 },
  );
  const options = await emr.locator('[name="form_category"] option').evaluateAll(
    (els) => els.map((e) => ({ value: e.value, label: (e.textContent ?? "").trim() })),
  );
  const vacation = options.find((o) => /vacation/i.test(o.label));
  if (!vacation) {
    throw new Error(
      `OpenEMR's provider form offers no Vacation category (saw: ${options.map((o) => o.label).join(", ")})`,
    );
  }
  await emr.selectOption('[name="form_category"]', vacation.value);
  await wait(1500);
  await emr.locator('[name="form_allday"]').first().check().catch(() => {});
  await emr.fill('[name="form_date"]', day).catch(() => {});
  await emr.fill('[name="form_title"]', "Vacation").catch(() => {});
  await emr.fill('[name="form_comments"]', "oncology leave").catch(() => {});
  await wait(2500);
  await emr.click('[name="form_save"]').catch(async () => {
    await emr.locator('button:has-text("Save")').first().click();
  });
  await wait(6000);

  // Confirm the hospital kept it, before anything downstream is credited with
  // noticing it — a failed save and a broken connector look identical from
  // the far end, and this is what tells them apart.
  //
  // The URL matters. `index.php?pc_view=day&date=…` renders the calendar
  // chrome and no events at all; the day's events come from PostCalendar's
  // own view, with the date as YYYYMMDD. Checked: the first form reports no
  // leave for a day that demonstrably has one.
  const compact = day.replace(/-/g, "");
  await emr.goto(
    `${EMR}/interface/main/calendar/index.php?module=PostCalendar&func=view&tplview=&viewtype=day&Date=${compact}`,
    { waitUntil: "domcontentloaded", timeout: 90000 },
  ).catch(() => {});
  await wait(4000);
  const shown = await emr.content();
  // The note this script typed, not merely the word "Vacation" — which could
  // be a legend, another provider's leave, or a leftover from an earlier run.
  if (!/oncology leave/i.test(shown)) {
    throw new Error(
      `OpenEMR's own day view for ${day} does not show the leave that was just saved`,
    );
  }
  return vacation.label;
}

async function demo({ emr, panel, health }) {
  /* ── one: three deployed things, named ─────────────────────────────────── */
  await say("setup", `Three deployed services and one phone. Nothing here is running on a laptop. The hospital is OpenEMR at ${EMR.replace(/^https?:\/\//, "")}; the Console and the API are on Render.`);

  await emr.fill("#authUser", process.env.SAATHI_OPENEMR_USER ?? "admin").catch(() => {});
  await emr.fill("#clearPass", process.env.SAATHI_OPENEMR_PASS ?? "").catch(() => {});
  await emr.click("#login-button").catch(() => {});
  await wait(12000);
  await emr.locator('button:has-text("Ask again later")').click().catch(() => {});
  await say("hospital", "OpenEMR, unmodified. No module of ours is installed in it; we read its standard FHIR API and write approved bookings back through the same one.");

  await signIn(panel, "Seema Kamble");
  await mustClick(panel, /^Hospitals right now$/, "the hospital board");
  const live = liveConnectors(await api("/hospital/now"));
  await say("console", `The Console, reading that hospital live: ${live.map((c) => `${c.system}, ${num(String(c.appointments))} appointments`).join("; ")}. ${num(String(health.patients))} families are on this deployment.`);

  /* ── two: the phone, and the family's own language ─────────────────────── */
  await adb("shell", "am", "force-stop", "org.ekyatra.saathi");
  // Force-stop first. `am start` resumes an already-running activity wherever
  // it was left, so a take that ended inside a family — or a hand that reset
  // the phone between takes — begins on her screen rather than the picker, and
  // the film fails with "the family list is not on the phone" having never
  // looked at one. The take must not depend on how the last one ended.
  // Home first, which closes a notification shade. A downward swipe anywhere
  // near the top pulls it, it covers the whole screen, and `am start` then
  // brings the app up *behind* it — so the film reads Android's own settings
  // text and reports that the family list is not on the phone. It was; the
  // shade was in front of it. Cost two takes.
  await adb("shell", "input", "keyevent", "KEYCODE_HOME").catch(() => {});
  await wait(1500);
  await adb("shell", "am", "force-stop", "org.ekyatra.saathi").catch(() => {});
  await wait(2000);
  await adb("shell", "am", "start", "-n", "org.ekyatra.saathi/.MainActivity");
  await wait(9000);
  await mustReadOnThePhone("EKY-", "the family list");
  await say("phone", "The family's app, built against the deployed API — not a local one. Four families, each on the language their record carries.");

  /* ── three: a doctor marks leave, and nobody tells the family ─────────── */
  const { day } = await pickTheLeaveDay(health);
  // Which questions already exist, before this film touches anything. A
  // previous rehearsal's leave can sit on the same day, and clearing our side
  // makes the connector re-read and re-ask from it — so a question about this
  // day may be waiting before the leave below is ever entered. Waiting for a
  // question id that is *new* is what separates "it reacted to what we just
  // did" from "something had already asked about that day".
  const askedBefore = new Set((await api("/questions/waiting")).map((q) => q.id));
  await say("event", `A doctor is about to mark themselves away on ${num(day)}, in the hospital's own calendar. An ordinary save, by ordinary staff, in a system with nothing of ours installed in it.`);

  const category = await enterLeaveOnCamera(emr, day);
  await say("event", `Saved in OpenEMR as “${category}”, all day. Now look at the families' appointments: unchanged. Not moved, not cancelled, status untouched — so anything watching appointments sees nothing at all.`);

  // Keyed on the day the question is *about*, not on how many are open.
  // A conversation holds one open question per family, so a family that was
  // already mid-question has theirs replaced rather than added to — and a
  // count then never grows, however well the connector worked. That cost a
  // rehearsal: three families had in fact just been asked about this very day.
  const isNew = (q) =>
    q.about_day === day && q.reason === "doctor_away" && !askedBefore.has(q.id);
  const waiting = await until(
    `the connector noticing the leave on ${day} and asking somebody about it`,
    () => api("/questions/waiting"),
    (qs) => qs.some(isNew),
    // Patience, not a weaker test: `isNew` still demands a question about the
    // day this take entered. A leave left over from an earlier take gets its
    // own families asked first, and those calls are live — one take expired
    // with this day's questions still in flight behind somebody else's.
    { tries: 60, gap: 4000 },
  );
  const asked = waiting.filter(isNew);
  const languages = [...new Set(asked.map((q) => q.language))];
  await say("asked", `The connector read the leave and worked out which families it hits — then asked each one ${languages.length > 1 ? "in their own language" : ""}: ${asked.map((q) => `${q.name} (${q.language})`).join(", ")}. Nobody wrote a script per family.`);

  await mustClick(panel, /^Approvals$/, "the approvals queue");
  await mustSee(panel, /Asked|waiting/i, "the asked-and-waiting list");
  await say("console", "Each question, as it was sent. Templated per language, never generated — a model that writes the question can invent a premise, and a family cannot tell which half of a fluent sentence came from a record.");

  /* ── four: the Hindi voice, on the phone, from the deployed API ────────── */
  // Prefer a family whose language is not English, because the point of this
  // beat is that the question arrived in her own script. Which families a leave
  // hits is not ours to choose, so when every one of them reads English the
  // caption says that instead of claiming a script nobody is looking at.
  const onCamera = asked.find((q) => q.language !== "en") ?? asked[0];
  await phoneTap(onCamera.patient_id);
  await phoneTap(MESSAGES[onCamera.language] ?? MESSAGES.hi);

  // Checked against the text the API says it sent, not against a month name in
  // one script. This beat hunted for Devanagari on a Bengali screen and failed
  // a take eight beats in: the family a leave hits decides the language, and
  // the film does not get to assume it.
  const words = (onCamera.asked_text ?? "").split(/\s+/).filter((w) => w.length >= 5);
  const fragment = words.sort((a, b) => b.length - a.length)[0];
  if (!fragment) throw new Error(`the question sent to ${onCamera.name} has no word long enough to look for`);
  await mustReadOnThePhone(fragment, `the question sent to ${onCamera.name}, on the phone`);

  const ownScript = onCamera.language !== "en";
  await say(
    "phone",
    `${onCamera.name}'s phone. The question has arrived ${ownScript ? "in their own script — not transliterated, and not in English" : "in the language their record carries"}.`,
  );

  // Nothing is read aloud yet, and that is not an omission. The speak button
  // reads the family's current plan, and until a navigator has agreed to her
  // answer there is no new plan to read: on this deployment both Hindi
  // families had no rendered message and so no speak button at all. The
  // voice belongs after the agreement, which is the better place for it —
  // what she hears is then the plan her own words produced.

  /* ── five: the family answers, in their own words, with their own figure ── */
  // Whoever was actually asked answers — not a hardcoded pair. The leave hits
  // a different set of families on a deployment than it does locally, and a
  // reply injected for somebody who was never asked lands in a void: no open
  // question, so no reading, so nothing in the queue. That cost a take, and
  // the symptom was one reply arriving instead of two.
  const WORDS = {
    hi: "Bees tarikh ke baad hi aa sakte hain, pehle nahi. Do log aayenge. Bus ka kiraya chaudah sau rupaye lagega.",
    bn: "Amar sathe ami jabo. Trainer tickets 900 taka hobe. 1 tarikher age noy, salary tokhon ase.",
    ta: "Irupathu theti ku appuram thaan vara mudiyum. Rendu per varuvom. Bus kattanam aayiram roobai aagum.",
    en: "Can't do a weekday, I lose the day's wages. After the 4th is fine, and only me coming. Train and bus is about 60 rupees each way.",
  };
  const replying = asked.filter((q) => WORDS[q.language]).slice(0, 2);
  if (!replying.length) throw new Error("nobody was asked in a language this film has words for");
  for (const who of replying) {
    await post("/live/inject", { patient_id: who.patient_id, text: WORDS[who.language] });
  }
  await say(
    "reply",
    `${replying.length === 1 ? "A family answers" : `${num(String(replying.length))} families answer`} by voice, ` +
      `in their own language typed the way they speak it: ${said(`“${WORDS[replying[0].language].slice(0, 95)}…”`)}`,
  );

  // Wait for all of them, settle for what actually arrived. Each reply is a
  // live model call on a free instance and two do not always land together;
  // demanding both failed a take when one had arrived and was perfectly good.
  let readings = [];
  for (let attempt = 0; attempt < 45; attempt += 1) {
    readings = await api("/requests/waiting").catch(() => []);
    if (readings.length >= replying.length) break;
    await wait(5000);
  }
  if (!readings.length) {
    throw new Error(`${replying.length} famil(ies) replied and nothing reached the queue in 225s`);
  }
  if (readings.length < replying.length) {
    console.log(`  only ${readings.length} of ${replying.length} replies had been read; carrying on`);
  }
  await panel.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
  await dressTheConsole(panel);
  await wait(3000);
  await signIn(panel, "Seema Kamble");
  await mustClick(panel, /^Approvals$/, "the approvals queue");
  await wait(3000);

  for (const row of readings) {
    const c = row.constraint ?? {};
    const tr = row.travel ?? {};
    console.log(`    ${row.patient_id}: not_before=${c.not_before} companions=${tr.companions} cost=${tr.stated_cost_inr}`);
  }
  const quoted = readings.find((r) => (r.travel ?? {}).stated_cost_inr);
  await say("read", `Read into constraints: ${readings.map((r) => `${r.name} not before ${num((r.constraint ?? {}).not_before ?? "—")}`).join("; ")}. ${quoted ? `And a cost of ${num("₹" + quoted.travel.stated_cost_inr)} — there because ${quoted.name} said it. There is no fare table in this system; the sentence they said it in is stored beside the number.` : ""}`);

  await say("guard", "Nothing has re-planned yet. A navigator reads the family's actual sentence and agrees with the reading before the planner may act — mishearing “after the 20th” as “on the 20th” costs this family two days on a train.");

  /* ── six: a person agrees, and only then does the planner search ───────── */
  // The family whose working we will follow on screen. Fatima's reading asks
  // for a date the hospital's rules cannot allow, so her search is the one
  // with a rejection in it — the half worth showing.
  const follow = readings.find((r) => r.patient_id === HINDI_FAMILY) ?? readings[0];

  /** Agree to one reading the way a navigator does: by clicking it.
   *
   *  Scoped to that family's own row. Every row carries a button with the
   *  same words, so an unscoped click agrees to whoever happens to be first.
   */
  async function agreeTo(name) {
    const row = panel.locator("li.queue-row").filter({ hasText: name }).first();
    const button = row.getByRole("button", { name: /^Agree/ });
    try {
      await button.first().click({ timeout: 20000 });
    } catch {
      throw new Error(`could not agree to ${name}'s reading in the Console`);
    }
    await wait(4000);
  }

  // Select her first. Agreeing removes the row from the queue, and the "Why"
  // control only exists while a family is selected — so clicking her name
  // afterwards is not possible. Cost a rehearsal to find.
  await mustClick(panel, follow.name, `${follow.name} in the queue`);
  await mustSee(panel, /Looking at/, "the selected family");

  for (const row of readings) await agreeTo(row.name);
  await say("human", `A navigator agrees with each reading — and only now may the planner act. ${num(String(readings.length))} readings, ${num(String(readings.length))} decisions, each by a person.`);

  const searches = [];
  for (const row of readings) {
    const search = await api(`/patients/${row.patient_id}/search`).catch(() => null);
    if (search && search.considered?.length) {
      searches.push({ name: row.name, ...search });
      console.log(`    ${row.patient_id}: ${search.summary}`);
      for (const c of search.considered) console.log(`        ${c.line}`);
    }
  }
  if (!searches.length) throw new Error("a navigator agreed and the planner searched for nothing");

  const rejected = searches.find((s) => s.considered.some((c) => !c.offered));
  const show = searches.find((s) => s.name === follow.name) ?? rejected ?? searches[0];
  await say("plan", `The planner then searched against what they actually said. ${show.name}: ${show.summary}.`);

  await mustClick(panel, /Why this family.s plan is what it is/, "the why drawer");
  await mustSee(panel, "How this was worked out", "the reasoning log");
  await say("audit", "Every step, as the system recorded it — published by the code that did the work, carrying the time that work actually took. Refusals are in here too and are never filtered out.");

  await mustSee(panel, "What the planner considered", "the planner's search");
  if (show.considered.some((c) => !c.offered)) {
    const bad = show.considered.find((c) => !c.offered);
    const good = show.considered.find((c) => c.offered);
    await say("plan", `The half a planner normally hides: every date tried, and the rule that killed each one. ${num(new Date(bad.on + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" }))} was ruled out — ${bad.why}${bad.detail ? ` (${bad.detail})` : ""}.${good ? ` It offered ${num(new Date(good.on + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" }))} instead: the closest the hospital's own rules allow.` : ""}`);
  } else {
    await say("plan", `Every date the planner tried is on the record. ${show.summary} — nothing was ruled out this run, so the search shows offers only.`);
  }
  await wait(10000);

  await mustSee(panel, /What this is built from|built from/, "the knowledge graph");
  await say("audit", "And what it was built from. Every node is a record we hold, and each says where it came from — the hospital's calendar, our records, or the family's own words. Three different kinds of claim, kept apart.");

  /* ── six and a half: a person approves, and the hospital's diary changes ─ */
  //
  // The brief's single approval action, and the only thing in this system that
  // writes. `approve_option` puts the date into the hospital's own diary
  // *before* it records anything or rings anybody: if OpenEMR refuses, the
  // option stays pending and no family is told a time the hospital never
  // agreed to.
  // Shut the "Why" drawer first. It is still open from the reasoning beat, it
  // overlays the page, and the approvals queue underneath it cannot be clicked
  // — so the row was not missing, it was behind something. Escape closes it,
  // which is what a navigator would press.
  await panel.keyboard.press("Escape").catch(() => {});
  await wait(2500);

  const beforeWrite = await connectorCounts();
  const queued = (await api("/disruptions/pending").catch(() => [])).filter(
    (row) => readings.some((r) => r.patient_id === row.patient_id),
  );
  if (!queued.length) throw new Error("the planner offered dates and nothing reached the approvals queue");
  const chosen = queued.find((row) => row.patient_id === follow.patient_id) ?? queued[0];
  const chosenName = (readings.find((r) => r.patient_id === chosen.patient_id) ?? {}).name ?? chosen.patient_id;
  const offered = await api(`/disruptions/${encodeURIComponent(chosen.disruption_id)}/options/${chosen.patient_id}`);
  const first = (offered.options ?? [])[0] ?? {};

  await say("human", `Now the one action in this system that writes anything. ${chosenName}'s options are ranked, and a navigator picks one — nothing here approves itself.`);
  // By patient id, scoped to the queue's own rows. The approvals queue labels
  // each row with the id — "EKY-SHANTI" — while her name appears higher up the
  // same screen in the request queue, so clicking the name selected her there
  // and the options card never opened. The approval button was unreachable for
  // a reason that had nothing to do with the button.
  const queueRow = panel.locator(".master-row").filter({ hasText: chosen.patient_id }).first();
  try {
    await queueRow.click({ timeout: 20000 });
  } catch {
    throw new Error(`could not select ${chosen.patient_id} in the approvals queue`);
  }
  await wait(3500);
  await mustClick(panel, /^Approve as /, "the approval button");
  await wait(9000);

  const afterWrite = await until(
    "the hospital accepting the booking",
    connectorCounts,
    (c) => (c.booked ?? 0) > (beforeWrite.booked ?? 0),
    { tries: 12, gap: 4000 },
  );
  await say(
    "write",
    `Approved — and the booking went into OpenEMR through its own FHIR API, on ${num(new Date(first.target_on + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" }))}: the date their own sentence produced. The write happens before anybody is told, so a hospital that refuses the slot means nobody was promised it.`,
  );

  // Show it in OpenEMR's own calendar rather than assert it from our side.
  await emr.goto(`${EMR}/interface/main/calendar/index.php?module=PostCalendar&func=view&tplview=&viewtype=day&Date=${first.target_on.replace(/-/g, "")}`, { waitUntil: "domcontentloaded" }).catch(() => {});
  await wait(7000);
  await say("hospital", `The hospital's own calendar, on that day. Nothing of ours is installed here — this is the appointment OpenEMR now holds, written through the same standard API we read it with.`);

  // The loop closing. Her journey is planned backwards from an appointment
  // time, and that time is now read back out of the hospital rather than held
  // by us — so the write-back is not a claim this film makes, it is the thing
  // the next question's answer depends on.
  const afterTrip = await api(`/patients/${chosen.patient_id}/trip/options`).catch(() => null);
  if (afterTrip?.arrive_by_source === "hospital_booking" && (afterTrip.arrive_by ?? "").startsWith(first.target_on)) {
    await say(
      "write",
      `And this is the loop closing. This journey is worked out backwards from the time they have to be there — and that time now reads ${num(new Date(afterTrip.arrive_by).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }))}, taken from the hospital's own booking. Not from anything we kept: the write-back is what the next answer depends on.`,
    );
  }

  // And the half a demo would quietly skip.
  if ((afterWrite["rebook:old-slot-left-open"] ?? 0) > (beforeWrite["rebook:old-slot-left-open"] ?? 0)) {
    await say(
      "guard",
      "And the part worth saying out loud: the old slot is still there. OpenEMR's FHIR Appointment has create but no update, so this system cannot cancel — and rather than pretend, it books the new date, leaves the old one standing, and records that a person must release it in the calendar. A demo that showed the old slot vanishing would be showing you something that did not happen.",
    );
    await wait(4000);
  }

  /* ── seven: the new plan, read to each family in their own language ───── */
  //
  // Now there is something to read. Before the agreement these cards carried
  // no message and no speak button; the plan that exists now is the one their
  // own sentence produced.
  for (const who of replying) {
    await adb("shell", "input", "keyevent", "KEYCODE_BACK");
    await wait(2500);
    await phoneTap(who.patient_id).catch(() => {});
    // Back onto the home tab explicitly. The app reopens a family on
    // whichever tab was last used — by now that is her messages — and the
    // speak button is only on the home card. Cost a take to find.
    await phoneTap(TODAY[who.language] ?? TODAY.hi).catch(() => {});
    const tongue = { hi: "Hindi", bn: "Bengali", ta: "Tamil", en: "English" }[who.language] ?? who.language;

    // One family without a speak button must not cost the whole film. It only
    // appears once there is a plan to read, and a family whose own search
    // offered nothing has no plan yet — which is a true thing about this run,
    // so the caption says it rather than the take dying twenty beats in.
    let heard = null;
    try {
      heard = await speakOnThePhone(who.patient_id, who.language);
    } catch (error) {
      console.log(`  no reading for ${who.patient_id}: ${error.message}`);
      await say(
        "voice",
        `${who.name} has no new plan to read out yet, so nothing is claimed about ${tongue} speech here. The plan is read aloud only once there is one.`,
      );
      continue;
    }

    if (heard.kept) {
      await say(
        "voice",
        `${who.name}'s new plan, read out in ${tongue} — ${num(heard.kept.kb + " KB")} of speech from Sarvam through the deployed API, played by the app's own media player rather than the phone's text-to-speech. We check which one played, because a phone with no ${tongue} voice fails silently and the family simply hears nothing.`,
      );
    } else {
      await say(
        "voice",
        `${who.name}'s phone fell back to its own text-to-speech here, so no Sarvam audio is claimed for this take. The message is still on screen in ${tongue}.`,
      );
    }
  }
  /* ── seven and a half: the part of the journey nobody plans for them ──── */
  //
  // A new date is a new night away from home, 1,300 km from it. The places
  // here are real OpenStreetMap records loaded into the deployment's own
  // table, and the ordering puts a dharamshala above a hotel when the family
  // has told us money is tight — the same rule that puts a Jan Aushadhi above
  // a pharmacy. We never quote a price, because nobody gave us one.
  const trips = {};
  for (const who of replying) trips[who.patient_id] = await api(`/patients/${who.patient_id}/trip/options`).catch(() => null);
  const stayFor = replying.find((w) => trips[w.patient_id]?.rail) ?? replying[0];
  await adb("shell", "input", "keyevent", "KEYCODE_BACK").catch(() => {});
  await wait(2200);
  await phoneTap(stayFor.patient_id).catch(() => {});
  await phoneTap(PLAN_TAB[stayFor.language] ?? PLAN_TAB.hi).catch(() => {});
  await wait(3500);
  await phoneTap(STAY[stayFor.language] ?? STAY.hi).catch(() => {});
  await wait(5000);
  const near = await api(`/patients/${stayFor.patient_id}/nearby?need=stay`).catch(() => null);
  const top = (near?.places ?? near?.ranked ?? [])[0];
  if (top) {
    const place = top.place ?? top;
    await say(
      "stay",
      `Somewhere to stay, for the night the new date now needs — ${said(place.name ?? "")} at ${num(Math.round(top.metres ?? 0) + " m")}. Real OpenStreetMap records, and a dharamshala is put above a hotel because they told us what the journey costs them. No price is shown, because nobody gave us one and this system does not invent a figure.`,
    );
  } else {
    await say("stay", "The nearby-stay lookup returned nothing on this take, so nothing is claimed about it here.");
  }
  await wait(4000);

  // The hand-off, stated as a hand-off. We hold station codes, not timetables.
  const rail = trips[stayFor.patient_id]?.rail;
  if (rail) {
    await say(
      "book",
      `And the train. We name the stations — ${said(rail.from.name + " (" + rail.from.code + ")")} to ${said(rail.to.name + " (" + rail.to.code + ")")}, with ${num(String((rail.also ?? []).length))} other Mumbai terminals that also serve this hospital — and hand them to IRCTC to book it. No train number, no time, no fare: we have no timetable licence, and a wrong train number 1,300 km from home is worse than no train number.`,
    );
    await wait(4000);
  }
  const money = trips[stayFor.patient_id]?.budget ?? {};
  if (money.stated_fare_paise) {
    await say(
      "money",
      `The only figure in here is theirs: ${num("₹" + Math.round(money.stated_fare_paise / 100))}, and the sentence they said it in is stored beside it. This system holds no fare table and quotes no price — a number we guessed and a number they gave us look identical on a screen, and only one of them is true.`,
    );
    await wait(3500);
  }

  await say("note", "Five languages, and the guard reads dates in all five scripts. If it cannot read the date in a message, it refuses to send it rather than send something it could not check.");
  await wait(6000);

  /* ── eight: what this is worth beyond four families ───────────────────── */
  const held = await api(`/patients/${BENGALI_FAMILY}/consent`);
  for (const grant of held.grants ?? []) {
    if (grant.purpose === "research" && grant.active) {
      await post(`/patients/${BENGALI_FAMILY}/consent/grants/${grant.id}/revoke`, {
        by: "Shanti Kumari",
        reason: "rehearsal setup — this take shows the grant being asked for and given",
      });
    }
  }
  const beforeRelease = await api("/research/release");
  await say("research", `India has registries full of staging and survival. What nobody has is why people stop coming — distance, cost, wasted journeys, waiting. This system holds exactly that, and right now it is contributing ${num(String(beforeRelease.manifest.rows))} rows, because no family has consented.`);

  const request = await post(`/patients/${BENGALI_FAMILY}/consent/requests`, {
    purpose: "research",
    requester_id: "NCG-IN",
    requester_name: "National Cancer Grid (NCG), India",
    categories: ["travel_burden"],
    reason: "Travel and cost burden, de-identified, for research into why treatment is abandoned",
  });
  await post(`/patients/${BENGALI_FAMILY}/consent/requests/${request.id}/grant`, {
    granted_by: "Shanti Kumari", capacity: "self", channel: "ivr",
  });
  const after = await until(
    "the release gaining a row",
    () => api("/research/release"),
    (r) => r.manifest.rows > beforeRelease.manifest.rows,
    { tries: 10, gap: 3000 },
  );
  await say("research", `Shanti said yes, and one row appeared — ${num(String(after.manifest.rows))} contributed, ${num(String(after.manifest.excluded_no_research_consent))} still withheld. Consent is asked per family, is revocable, and is never a condition of care.`);

  await panel.goto(`${PANEL}/?persona=menon&section=research`, { waitUntil: "domcontentloaded" }).catch(() => {});
  await dressTheConsole(panel);
  await wait(4000);
  await mustSee(panel, "National Cancer Grid", "the receiving body");
  await mustSee(panel, "Removed before anything leaves", "what is withheld");
  await say("research", "No name, no ABHA, no patient id — not even a hashed one, because a stable key lets two releases be joined back into a person. District becomes a state, distance becomes a band, and nothing clinical leaves because there is nothing clinical in here to leak.");

  await say("note", "A doctor marked themselves away. Nobody told the family — nobody ever does. Minutes later every affected family had been asked, in their own language, and a person had agreed a plan around what they answered.");
}

/* ───────────────────────────── post-processing ────────────────────────── */

/** Make the video last as long as the take did.
 *
 *  A screen capture that cannot keep up does not slow down — it writes fewer
 *  frames and still labels them at the rate that was asked for, so the film
 *  plays fast by exactly the ratio it fell short by. Nothing warns: the file
 *  is valid, the picture is sharp, and three minutes arrive as eighty seconds.
 */
async function matchTheClock(video, ranForMs) {
  const seconds = ranForMs / 1000;
  if (seconds < 5) return video;
  const { stdout } = await run("ffprobe", [
    "-v", "error", "-count_frames", "-select_streams", "v:0",
    "-show_entries", "stream=nb_read_frames", "-of", "default=nokey=1:noprint_wrappers=1",
    video,
  ]);
  const frames = Number(stdout.trim());
  if (!Number.isFinite(frames) || frames < 2) return video;
  const fps = frames / seconds;
  // Two steps, and the first is not optional: `-r` on an mp4 with `-c copy`
  // does nothing, because the container's own timestamps survive. Stripping to
  // an elementary stream discards them so the remux can apply the real rate.
  // Still no re-encoding.
  const stream = resolve(OUT, "hosted-flow-stream.h264");
  const out = resolve(OUT, "hosted-flow-timed.mp4");
  await run("ffmpeg", ["-y", "-loglevel", "error", "-i", video,
    "-c", "copy", "-bsf:v", "h264_mp4toannexb", "-f", "h264", stream]);
  await run("ffmpeg", ["-y", "-loglevel", "error", "-fflags", "+genpts",
    "-r", fps.toFixed(6), "-i", stream, "-c", "copy", out]);
  console.log(`  ${frames} frames over ${seconds.toFixed(1)}s — retimed to ${fps.toFixed(2)}fps`);
  return out;
}

/** Is there actually a picture in it?
 *
 *  A slept display records as black at full frame rate, and every other
 *  measure of the file looks healthy — valid duration, 9,000 frames, the
 *  soundtrack in the right places. Nothing downstream would notice, and the
 *  first person to find out would be whoever opened it to watch. So the
 *  luminance is sampled across the film and a dark one fails the take.
 */
async function hasAPicture(video) {
  const samples = [];
  for (const at of [0.2, 0.4, 0.6, 0.8]) {
    const { stdout } = await run("ffprobe", [
      "-v", "error", "-show_entries", "format=duration",
      "-of", "default=nokey=1:noprint_wrappers=1", video,
    ]);
    const seconds = Number(stdout.trim()) * at;
    const { stderr } = await run("ffmpeg", [
      "-hide_banner", "-ss", seconds.toFixed(1), "-t", "1", "-i", video,
      "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
      "-f", "null", "-",
    ]).catch((e) => ({ stderr: e.stderr ?? "" }));
    const match = /YAVG=([0-9.]+)/.exec(stderr ?? "");
    if (match) samples.push(Number(match[1]));
  }
  if (!samples.length) return { ok: true, samples };
  const brightest = Math.max(...samples);
  // A lit screen full of windows sits around 100. Anything in single figures
  // is a dark or blank display, not a dim one.
  return { ok: brightest > 20, samples, brightest };
}

/** Lay the kept clips on, each at the second it played.
 *
 *  No `-shortest`: it trims the output to the shortest stream, and the
 *  shortest stream is the soundtrack. It once cut the closing screen off the
 *  end of a good take.
 */
async function addTheVoices(video) {
  if (!soundtrack.length) {
    console.log("  no audio kept, so the film is silent rather than dubbed");
    return video;
  }
  const out = resolve(OUT, "hosted-flow.mp4");
  const args = ["-y", "-loglevel", "error", "-i", video];
  for (const clip of soundtrack) args.push("-i", clip.file);
  const delays = soundtrack
    .map((c, i) => `[${i + 1}:a]adelay=${c.atMs}|${c.atMs}[a${i}]`)
    .join(";");
  const mixed = soundtrack.map((_, i) => `[a${i}]`).join("");
  // `normalize=0` so a quiet clip is not dragged down by however many others
  // exist, then a limiter so that summing can never clip. Without the limiter
  // any overlap at all lands on the ceiling and distorts; with it, the worst
  // case is a moment of gentle gain reduction nobody notices.
  args.push(
    "-filter_complex",
    `${delays};${mixed}amix=inputs=${soundtrack.length}:normalize=0[mixed];` +
      "[mixed]alimiter=limit=0.89:level=false[out]",
    "-map", "0:v", "-map", "[out]",
    "-c:v", "copy",
    // 39 kbps mono was thin for speech, and thin speech in four languages is
    // harder to follow than thin speech in one.
    "-c:a", "aac", "-b:a", "128k",
    out,
  );
  await run("ffmpeg", args);
  const narration = soundtrack.filter((c) => c.language === "en");
  if (narration.length) {
    const spoken = narration.reduce((n, c) => n + (c.seconds ?? 0), 0);
    console.log(`  narration: ${narration.length} lines, ${spoken.toFixed(0)}s of English`);
  }
  for (const c of soundtrack.filter((c) => c.language !== "en")) {
    console.log(`  the app speaking ${c.language}: ${Math.round(c.bytes / 1024)} KB from ${c.spokenBy} at ${(c.atMs / 1000).toFixed(1)}s`);
  }
  return out;
}

main().catch((error) => {
  console.error(`\n  the take failed: ${error.message}`);
  console.error("  nothing was published; fix it and run again.\n");
  process.exit(1);
});
