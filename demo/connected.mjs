/**
 * One run, two recorders: the Console and the family's phone, side by side.
 *
 *     make demo-connected
 *
 * The earlier film recorded the browser, then recorded the phone, then joined
 * them with a card. That was honest but weak — the one claim a judge most
 * wants tested is that these surfaces are actually connected, and a cut is
 * exactly where you would hide the fact that they are not.
 *
 * This records both **at the same moment, during the same run**. The browser
 * is captured by Playwright and the phone by `adb screenrecord`, started
 * together, and the two views are laid side by side afterwards. Nothing is
 * re-timed and nothing is spliced: the leave entered in OpenEMR, the Console
 * reacting and the phone speaking Bengali are the same events at the same
 * wall-clock second, shown from two angles.
 *
 * Why not capture the whole screen instead, which would need no compositing
 * at all: because macOS requires a screen-recording permission granted by
 * hand, and until it is, it puts a consent dialog in the middle of every
 * frame. `one-frame.mjs` does it that way for anyone who has granted it.
 * See `README-one-frame.md`.
 *
 * The proof of simultaneity is in the recording itself: the clock in the
 * phone's status bar against the timestamps in the Console's own event log.
 */

import { chromium } from "playwright";
import { execFile, spawn } from "node:child_process";
import { existsSync, mkdirSync, renameSync, readdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const run = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../recordings");

const EMR = process.env.SAATHI_OPENEMR_URL ?? "http://localhost:8300";
const PANEL = process.env.SAATHI_PANEL_URL ?? "http://localhost:5173";
const API = process.env.SAATHI_API_URL ?? "http://127.0.0.1:8077";
const ADB = process.env.ADB ?? `${process.env.HOME}/Library/Android/sdk/platform-tools/adb`;
const DB = process.env.SAATHI_OPENEMR_DB_CONTAINER ?? "hms-eval-mysql-1";

//: Tall, because it sits beside a 9:19.5 phone. A 16:9 browser next to a
//: phone leaves two dead bands and makes the phone look like an afterthought.
const VIEWPORT = { width: 1180, height: 1000 };
const BEAT = Number(process.env.SAATHI_DEMO_BEAT ?? 1000);

const HINDI = "EKY-KAMLA";
const BENGALI = "EKY-SHANTI";

//: What she says back, in the romanised Bengali a phone's speech-to-text
//: actually produces for Bengali speech.
const HER_REPLY =
  "Amar sathe ami jabo. Trainer tickets 900 taka hobe. " +
  "1 tarikher age noy, salary tokhon ase.";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const adb = (...args) => run(ADB, args).catch(() => ({ stdout: "" }));

async function api(path) {
  const response = await fetch(`${API}/api${path}`);
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return response.json();
}

async function post(path, body) {
  const response = await fetch(`${API}/api${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return response.json();
}

function sql(statement) {
  return new Promise((done, fail) => {
    const child = spawn(
      "docker",
      ["exec", "-i", DB, "mariadb", "-uroot", "-proot", "openemr", "-N", "-B"],
      { stdio: ["pipe", "ignore", "ignore"] },
    );
    child.on("error", fail);
    child.on("close", () => done());
    child.stdin.end(statement);
  });
}

/** Tap whatever currently reads `label` on the phone.
 *
 *  From the live view hierarchy, not a remembered coordinate: a tap at a
 *  stale position lands on whatever drifted into that spot, and the film
 *  then narrates a screen nobody is looking at. That happened twice.
 */
async function phoneTap(label, settle = 4000) {
  await adb("shell", "uiautomator", "dump", "/sdcard/ui.xml");
  const { stdout } = await run(ADB, ["shell", "cat", "/sdcard/ui.xml"]);
  const found = stdout.match(
    new RegExp(`text="([^"]*${label}[^"]*)"[^>]*bounds="\\[(\\d+),(\\d+)\\]\\[(\\d+),(\\d+)\\]"`),
  );
  if (!found) throw new Error(`nothing on the phone reads "${label}"`);
  const [x1, y1, x2, y2] = found.slice(2).map(Number);
  await adb("shell", "input", "tap",
    String(Math.round((x1 + x2) / 2)), String(Math.round((y1 + y2) / 2)));
  await wait(settle);
  return found[1];
}

async function ready() {
  const problems = [];
  try {
    const health = await api("/health");
    if (!health.actors) problems.push("no Groq actors — the reply cannot be read");
    if (!health.language_layer) problems.push("no language layer — nothing can be written");
  } catch (error) {
    problems.push(`the API is not answering on ${API} (${error.message})`);
  }
  try {
    // Through the Console's own proxy, which is what the browser will use.
    // Checking the API directly misses the commonest failure of all: the
    // dev proxy pointed at port 8000 and reaching somebody else's server.
    const proxied = await fetch(`${PANEL}/api/health`);
    if (!proxied.ok) problems.push(`the Console proxy answers ${proxied.status} — set SAATHI_API_PORT`);
  } catch {
    problems.push(`the Console is not serving on ${PANEL} — run \`make web\``);
  }
  try {
    await fetch(EMR);
  } catch {
    problems.push(`OpenEMR is not serving on ${EMR}`);
  }
  const { stdout } = await run(ADB, ["devices"]).catch(() => ({ stdout: "" }));
  if (!/\sdevice\b/.test(stdout)) problems.push("no phone attached");

  if (problems.length) {
    console.error("\nNot recording. Fix these first:\n");
    for (const problem of problems) console.error(`  - ${problem}`);
    console.error("");
    process.exit(1);
  }
}

async function main() {
  await ready();
  mkdirSync(OUT, { recursive: true });

  // Back to before the leave, so act one is the first time it happens.
  // `clear`, not `reset`: reset rewinds the world and refuses outright on
  // real records. This forgets what has been asked and read and deletes
  // nothing. Deliberately NOT swallowed — a silently failed reset is what
  // put three copies of the same family on screen for three takes running.
  await post("/live/control", { action: "clear" });
  await wait(9000);

  await adb("shell", "am", "force-stop", "org.ekyatra.saathi");
  await adb("shell", "am", "start", "-n", "org.ekyatra.saathi/.MainActivity");
  await wait(6000);

  const browser = await chromium.launch({ headless: false, args: ["--window-size=1180,1000"] });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: { dir: OUT, size: VIEWPORT },
  });
  const page = await context.newPage();

  // Both recorders start here, within a second of each other. Everything
  // after this point is one run seen from two angles.
  const phoneRecorder = spawn(
    ADB, ["shell", "screenrecord", "--time-limit", "180", "--bit-rate", "8000000",
          "/sdcard/connected.mp4"],
    { stdio: "ignore" },
  );
  await wait(2000);
  console.log("  both recorders running — one take from here");

  try {
    await demo(page);
  } finally {
    phoneRecorder.kill("SIGINT");
    await wait(4000);
    await context.close();
    await browser.close();
  }

  const phoneFile = resolve(OUT, "connected-phone.mp4");
  await adb("pull", "/sdcard/connected.mp4", phoneFile);
  await adb("shell", "rm", "/sdcard/connected.mp4");

  const browserFile = newestWebm();
  const target = resolve(OUT, "connected-browser.webm");
  if (browserFile) renameSync(browserFile, target);
  console.log(`\n  browser -> ${target}`);
  console.log(`  phone   -> ${phoneFile}`);
  console.log("  now run ./demo/side-by-side.sh to lay them together");
}

function newestWebm() {
  const videos = readdirSync(OUT)
    .filter((name) => name.endsWith(".webm") && name !== "connected-browser.webm")
    .map((name) => ({ path: resolve(OUT, name), at: statSync(resolve(OUT, name)).mtimeMs }))
    .sort((a, b) => b.at - a.at);
  return videos.length ? videos[0].path : null;
}

async function demo(page) {
  // ---- the hospital ----
  await page.goto(`${EMR}/interface/login/login.php?site=default`, { waitUntil: "domcontentloaded" });
  await page.fill("#authUser", process.env.SAATHI_OPENEMR_USER ?? "admin");
  await page.fill("#clearPass", process.env.SAATHI_OPENEMR_PASS ?? "pass");
  await page.click("#login-button");
  await wait(11000);
  await page.locator('button:has-text("Ask again later")').click().catch(() => {});
  await wait(2500);

  // Forward to the day the leave will be on, by the calendar's own arrow:
  // it ignores date parameters and silently reloads on today.
  for (let step = 0; step < 1; step += 1) {
    const calendar = page.frames().find((f) => f.url().includes("calendar/index.php"));
    await calendar?.locator('[title*="Next"], .fa-chevron-right').first().click().catch(() => {});
    await wait(2500);
  }
  await wait(BEAT * 2);

  // ---- the leave, as the provider tab writes it ----
  await sql(`
    INSERT INTO openemr_postcalendar_events
      (pc_catid, pc_aid, pc_pid, pc_multiple, pc_title, pc_time, pc_hometext,
       pc_eventDate, pc_endDate, pc_duration, pc_alldayevent, pc_startTime,
       pc_endTime, pc_recurrtype, pc_recurrspec, pc_facility, pc_apptstatus,
       pc_eventstatus, pc_sharing, uuid)
    VALUES (4, 1, NULL, 0, 'Vacation', NOW(), 'oncology leave',
            '2026-11-27', '2026-11-27', 0, 1, '00:00:00', '23:59:59', 0, '',
            3, '-', 1, 1, UNHEX(REPLACE(UUID(),'-','')));
  `);
  const calendar = page.frames().find((f) => f.url().includes("calendar/index.php"));
  await calendar?.evaluate(() => window.location.reload()).catch(() => {});
  await wait(5000);

  // Verified before anything is claimed.
  let asked = [];
  for (let attempt = 0; attempt < 18 && !asked.length; attempt += 1) {
    asked = await api("/questions/waiting");
    if (!asked.length) await wait(2000);
  }
  if (!asked.length) throw new Error("the leave was entered and nobody was asked");
  console.log(`  asked ${asked.length}: ${asked.map((q) => `${q.patient_id}/${q.language}`).join(", ")}`);

  // ---- our side ----
  await page.goto(PANEL, { waitUntil: "domcontentloaded" });
  await wait(2500);
  await page.getByText("Seema Kamble").first().click().catch(() => {});
  await wait(2500);
  await page.getByText(/^Hospitals right now$/).first().click().catch(() => {});
  await wait(4000);
  await page.getByText(/^Approvals$/).first().click().catch(() => {});
  await wait(4000);

  // ---- she answers, and the phone says it back ----
  await post("/live/inject", { patient_id: BENGALI, text: HER_REPLY });
  let reading = [];
  for (let attempt = 0; attempt < 20 && !reading.length; attempt += 1) {
    await wait(1500);
    reading = (await api("/requests/waiting")).filter((r) => r.patient_id === BENGALI);
  }
  if (!reading.length) throw new Error("her reply was never read");
  if (reading[0].travel?.stated_cost_inr !== 900)
    throw new Error(`expected her own figure of 900, got ${JSON.stringify(reading[0].travel)}`);
  console.log("  her reply read: ₹900, on the record, attributed");

  await page.reload({ waitUntil: "domcontentloaded" });
  await wait(2500);
  await page.getByText("Seema Kamble").first().click().catch(() => {});
  await wait(2000);
  await page.getByText(/^Approvals$/).first().click().catch(() => {});
  await wait(4500);

  // The phone, in Bengali, speaking through Sarvam.
  await phoneTap(BENGALI).catch(() => {});
  await phoneTap("বলুন", 10000).catch((error) => console.log(`  (no speak button: ${error.message})`));

  // ---- the working, and what it was built from ----
  const name = page.getByRole("button", { name: /Devi|Kumari|Begum|Prasad/ }).first();
  if (await name.isVisible().catch(() => false)) {
    await name.click();
    await wait(2000);
    await page.getByRole("button", { name: /Why this family/ }).first().click().catch(() => {});
    await wait(3500);
    await page.getByText("What this is built from").first().scrollIntoViewIfNeeded().catch(() => {});
    await wait(5000);
  }
}

main().catch((error) => {
  console.error(`\n  the take failed: ${error.message}`);
  console.error("  nothing was published; fix it and run again.\n");
  process.exit(1);
});
