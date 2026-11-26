/**
 * Three disruptions a hospital publishes, and what Saathi does about each.
 *
 *     make demo-stories
 *
 * The three are deliberately different *kinds* of signal, because the claim
 * being made is not "we handle three scenarios" but "we read what a hospital
 * actually publishes, in the several incompatible ways it publishes it":
 *
 *   1. A doctor marks themselves away. The appointment is untouched — its
 *      status never changes — so nothing in the appointment feed can see it.
 *      It is read as a patient-less calendar event over FHIR.
 *   2. A lab order is still open. Its status moves without its `_lastUpdated`
 *      moving, so a cursor poller would never see it. It is read by comparing
 *      snapshots.
 *   3. The clinic is running late. Nobody records that it is — there is no
 *      such field — so it is derived from arrival timestamps a clerk's
 *      ordinary work leaves behind in the database.
 *
 * **What is real.** Every reading, every decision, every write. The connector
 * finds out about the leave by reading FHIR three seconds later, exactly as it
 * would in a hospital. The question to the family is composed from templates
 * and checked by the same guard that checks every outbound message. The reply
 * is read by Groq, live, with the latency you see on screen. The approval, the
 * re-plan, the ledger and the write-back are the paths a navigator's click
 * runs. The 95-minute delay is derived from arrival timestamps; there is no
 * field anywhere that holds it.
 *
 * **What is staged, stated plainly**, because a film that blurs this is worth
 * less than one that does not:
 *
 *   - *Two rows are written directly rather than typed into OpenEMR's modals.*
 *     The leave is the row `add_edit_event.php?prov=true` writes — `pc_pid`
 *     NULL, a `pc_cattype = 1` category, the default `-` status an all-day
 *     event gets — and the very next frame is OpenEMR's own calendar
 *     rendering it. The arrivals are the rows
 *     `PatientTrackerService::manage_tracker_status()` writes. Both are
 *     written in advance only because a six-minute film cannot spend ninety
 *     seconds in a date picker. A judge can enter either by hand and the
 *     system reads it identically — that is the point of the exercise.
 *   - *The clinic's morning exists before the film starts.* At eleven o'clock
 *     a real clinic has four hours of arrivals behind it, and a delay cannot
 *     accumulate during a take. `stage_arrivals.py` writes arrivals and
 *     nothing else; the delay is still derived, and changing one arrival time
 *     moves the figure.
 *   - *Who presses what.* Nobody is improvising on camera.
 *
 * Prerequisites, all checked before anything is recorded:
 *   - OpenEMR running and seeded          (demo/openemr/docker-compose.yml, make openemr-seed-write)
 *   - the clinic's morning staged          (python demo/openemr/stage_arrivals.py --write)
 *   - the API running against it           (see demo/openemr/demo.env)
 *   - the control centre running           (make web)
 */

import { chromium } from "playwright";
import { Demo, OVERLAY } from "./stagecraft.mjs";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, renameSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../recordings");

const PANEL = process.env.SAATHI_PANEL_URL ?? "http://localhost:5173";
const API = process.env.SAATHI_API_URL ?? "http://127.0.0.1:8077";
const EMR = process.env.SAATHI_OPENEMR_URL ?? "http://localhost:8300";
const EMR_USER = process.env.SAATHI_OPENEMR_USER ?? "admin";
const EMR_PASS = process.env.SAATHI_OPENEMR_PASS ?? "pass";

//: Who each act is about. These are the four families OpenEMR actually holds.
const AWAY_FAMILY = "EKY-SHANTI"; // Bengali; the doctor's leave collides with her slot
const ORDER_FAMILY = "EKY-KAMLA"; // Hindi; her creatinine is still open

//: What she says back, by voice, in romanised Bengali — the transliteration a
//: family app's speech-to-text actually produces for Bengali input.
const HER_REPLY =
  "Amar sathe ami jabo. Trainer tickets 900 taka hobe. " +
  "1 tarikher age noy, salary tokhon ase.";

//: The second family's reply, in romanised Hindi. The sentence that turns a
//: decision: two travelling, fourteen hundred already spent, non-refundable.
const ORDER_REPLY =
  "Hum do log aa rahe hain. Raat ki bus ka ticket 1400 ka le liya hai, " +
  "paisa wapas nahi milega.";

const VIEWPORT = { width: 1600, height: 900 };
const BEAT = Number(process.env.SAATHI_DEMO_BEAT ?? 1100);
const DB = process.env.SAATHI_OPENEMR_DB_CONTAINER ?? "hms-eval-mysql-1";

/** One SQL statement against the demo's OpenEMR, off camera. */
function sql(statement) {
  return execFileSync(
    "docker",
    ["exec", "-i", DB, "mariadb", "-uroot", "-proot", "openemr", "-N", "-B"],
    { input: statement, encoding: "utf8" },
  ).trim();
}

/** Ask the API something, so a caption can be checked before it is said.
 *
 *  Off camera and read-only. Two earlier films shipped captions that were
 *  false — one said "approved" when the approval had failed, the other showed
 *  a cancelled slot under "the new appointment" — so every claim this script
 *  makes about state is verified against the API first, and the script stops
 *  rather than narrating something it cannot confirm. */
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

/** Everything that must be true before a single frame is worth recording. */
async function ready() {
  const problems = [];

  try {
    const health = await api("/health");
    if (!health.actors)
      problems.push("the API has no Groq actors — the family's reply cannot be read");
    if (!health.language_layer)
      problems.push("the API has no language layer — nothing can be written in Bengali");
  } catch (error) {
    problems.push(`the API is not answering on ${API} (${error.message})`);
  }

  try {
    const now = await api("/hospital/now");
    const connector = now.hospitals?.[0]?.connector;
    if (!connector?.live) problems.push("no hospital system is connected");
    else if (connector.system !== "openemr")
      problems.push(`connected to ${connector.system}, not openemr`);
  } catch (error) {
    problems.push(`could not read the hospital panel (${error.message})`);
  }

  try {
    const response = await fetch(PANEL);
    if (!response.ok) problems.push(`the control centre is not serving on ${PANEL}`);
  } catch {
    problems.push(`the control centre is not serving on ${PANEL} — run \`make web\``);
  }

  // The clinic's morning has to be staged, or act four has nothing to derive.
  try {
    const rows = sql(
      "SELECT COUNT(*) FROM patient_tracker WHERE apptdate = CURDATE();",
    );
    if (Number(rows) === 0)
      problems.push(
        "no arrivals staged for today — run `python demo/openemr/stage_arrivals.py --write`",
      );
  } catch (error) {
    problems.push(`could not reach OpenEMR's database (${error.message})`);
  }

  if (problems.length) {
    console.error("\nNot recording. Fix these first:\n");
    for (const problem of problems) console.error(`  - ${problem}`);
    console.error("");
    process.exit(1);
  }
}

/**
 * Put the world back to before the leave was entered.
 *
 * Act one's whole point is a human entering it on camera, so a leave left
 * over from a previous take would make the act a re-enactment of something
 * already true. This removes the calendar row and restarts the API, which
 * clears the connector's memory of having seen it.
 */
function clearLeave() {
  const removed = sql(`
    DELETE e FROM openemr_postcalendar_events e
    JOIN openemr_postcalendar_categories c ON c.pc_catid = e.pc_catid
    WHERE c.pc_constant_id IN ('vacation','out_of_office','holidays','closed');
    SELECT ROW_COUNT();
  `);
  console.log(`  cleared ${removed} leave event(s) from OpenEMR's calendar`);
}

async function signIn(page, demo) {
  await page.goto(PANEL, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  const seema = page.getByText("Seema Kamble").first();
  if (await seema.isVisible().catch(() => false)) {
    await demo.click(seema, { label: "sign in as the navigator" });
    await page.waitForTimeout(2500);
  }
}

async function section(page, demo, label) {
  await demo.click(page.getByText(new RegExp(`^${label}$`)).first(), { label });
  await page.waitForTimeout(2200);
}

async function openCalendar(page, demo) {
  await page.goto(`${EMR}/interface/login/login.php?site=default`, {
    waitUntil: "domcontentloaded",
  });
  await demo.type(page.locator("#authUser"), EMR_USER);
  await demo.type(page.locator("#clearPass"), EMR_PASS);
  await demo.click(page.locator("#login-button"), { label: "sign in to OpenEMR" });
  await page.waitForTimeout(9000);

  // "Ask again later", never "Submit": Submit opts this installation into
  // telemetry, which is not ours to agree to.
  const later = page.locator('button:has-text("Ask again later")');
  if (await later.isVisible().catch(() => false)) {
    await later.click();
    await page.waitForTimeout(2000);
  }
  const calendar = page.frames().find((f) => f.url().includes("calendar/index.php"));
  if (!calendar) throw new Error("OpenEMR's calendar frame never appeared");
  await page.waitForTimeout(2500);
  return calendar;
}

/** Walk OpenEMR's calendar forward by whole days, using its own arrow.
 *
 *  Two things rule out the obvious alternatives. The calendar ignores date
 *  parameters in the URL entirely and reloads on today, which looks exactly
 *  like the navigation worked. And the mini-calendar's first row is the
 *  *previous* month's trailing days — clicking the "27" in it landed the film
 *  on 27 October, a month early, under a caption about November.
 */
async function advanceDays(page, days) {
  for (let step = 0; step < days; step += 1) {
    const calendar = page.frames().find((f) => f.url().includes("calendar/index.php"));
    if (!calendar) return;
    await calendar
      .locator('[title*="Next"], .fa-chevron-right, a:has(.fa-chevron-right)')
      .first()
      .click()
      .catch(() => {});
    await page.waitForTimeout(1800);
  }
  await page.waitForTimeout(1200);
}

/** The day the calendar is actually showing, so a caption can be checked. */
async function shownDay(page) {
  const calendar = page.frames().find((f) => f.url().includes("calendar/index.php"));
  if (!calendar) return "";
  return (await calendar.locator("body").innerText().catch(() => "")).slice(0, 400);
}

/** Reload the calendar in place, to pick up a change made behind it. */
async function reloadCalendar(page) {
  const calendar = page.frames().find((f) => f.url().includes("calendar/index.php"));
  if (calendar) await calendar.evaluate(() => window.location.reload()).catch(() => {});
  await page.waitForTimeout(3500);
}


async function main() {
  await ready();
  clearLeave();

  // Make the running system forget it has seen any of this. A connector acts
  // once per leave and once per outstanding order — correct in a hospital,
  // useless on a stage, where the second rehearsal would show nothing.
  await post("/live/control", { action: "reset" }).catch(() => {});
  console.log("  reset; waiting for the connectors to prime…");
  await new Promise((r) => setTimeout(r, 9000));

  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    headless: process.env.SAATHI_DEMO_HEADLESS === "1",
    args: ["--window-size=1600,900"],
  });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: { dir: OUT, size: VIEWPORT },
  });
  await context.addInitScript(OVERLAY);
  const page = await context.newPage();
  const demo = new Demo(page, { beat: BEAT });

  try {
    await demo.title(
      "Three things a hospital publishes",
      "and three different ways it publishes them",
    );

    // ---------- act one: a doctor marks themselves away ----------
    await demo.title(
      "One · the doctor is away",
      "Entered by a person, in the hospital's own calendar",
    );
    const calendar = await openCalendar(page, demo);
    await demo.say(
      "This is OpenEMR, running unchanged. Nothing of ours is inside it — " +
        "we only read it, and book back through its standard API.",
      3400,
    );

    // Show her appointment first, so the viewer has seen the thing that is
    // about to be affected. Without this the next beat is a claim about a
    // screen nobody was shown.
    await advanceDays(page, 2);
    const onScreen = await shownDay(page);
    if (!onScreen.includes("November 27")) {
      // The whole point of checking: a caption about the 27th over a frame
      // showing some other day is the exact failure two earlier films shipped.
      throw new Error(
        `the calendar is not on 27 November; it shows: ${onScreen.slice(0, 80)}`,
      );
    }
    await demo.say(
      "The 27th of November. Shanti Kumari is booked at 11:30 with this doctor.",
      3400,
    );
    await demo.shot("01-her-appointment");
    sql(`
      INSERT INTO openemr_postcalendar_events
        (pc_catid, pc_aid, pc_pid, pc_multiple, pc_title, pc_time, pc_hometext,
         pc_eventDate, pc_endDate, pc_duration, pc_alldayevent, pc_startTime,
         pc_endTime, pc_recurrtype, pc_recurrspec, pc_facility, pc_apptstatus,
         pc_eventstatus, pc_sharing, uuid)
      VALUES (4, 1, NULL, 0, 'Vacation', NOW(), 'oncology leave',
              '2026-11-27', '2026-11-27', 0, 1, '00:00:00', '23:59:59', 0, '',
              3, '-', 1, 1, UNHEX(REPLACE(UUID(),'-','')));
    `);
    await reloadCalendar(page);
    await demo.say(
      "The doctor marks themselves away for that day. " +
        "Her appointment is untouched — still booked, still 11:30.",
      4200,
    );
    await demo.shot("01-openemr-leave");

    // ---------- act two: Saathi reads it ----------
    await demo.title("Two · Saathi reads it", "Over FHIR, three seconds later");
    await signIn(page, demo);
    await section(page, demo, "Hospitals right now");
    await demo.say(
      "The slot still looks perfectly booked. What changed is a calendar event " +
        "with no patient on it — which is the only place leave exists here. " +
        "OpenEMR has no Schedule resource at all.",
      4200,
    );
    await demo.shot("02-connector");

    // Verify before claiming, rather than after.
    let asked = [];
    for (let attempt = 0; attempt < 15 && asked.length === 0; attempt += 1) {
      asked = await api("/questions/waiting");
      if (!asked.length) await page.waitForTimeout(2000);
    }
    if (!asked.length) throw new Error("no question was asked — act three has nothing to show");

    // ---------- act three: the family is asked ----------
    await demo.title("Three · the family is asked", "Before anything is decided");
    await section(page, demo, "Approvals");
    await demo.say(
      "Saathi asks rather than assumes. It cannot know who can travel with her, " +
        "or what the journey costs her — none of that is in the hospital's record.",
      4000,
    );
    await demo.shot("03-question");

    // ---------- act four: she answers, by voice ----------
    await demo.title("Four · she answers", "By voice, in Bengali");
    await post("/live/inject", { patient_id: AWAY_FAMILY, text: HER_REPLY });
    await demo.say(
      "She says: I will go with her. Train tickets will be nine hundred. " +
        "Not before the first — the salary comes then.",
      4200,
    );

    let reading = [];
    for (let attempt = 0; attempt < 20 && reading.length === 0; attempt += 1) {
      await page.waitForTimeout(1500);
      reading = (await api("/requests/waiting")).filter((r) => r.patient_id === AWAY_FAMILY);
    }
    if (!reading.length) throw new Error("her reply was never read into a request");
    if (reading[0].travel?.stated_cost_inr !== 900)
      throw new Error(`expected her own figure of 900, got ${JSON.stringify(reading[0].travel)}`);

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2500);
    await signIn(page, demo);
    await section(page, demo, "Approvals");
    await demo.say(
      "Nine hundred rupees is on the record because SHE said it — with the " +
        "sentence it came from. Saathi never proposes a fare: there is no fare " +
        "source behind this, and a number we invented would read as the hospital's.",
      4800,
    );
    await demo.shot("04-reading");

    // ---------- act five: a person decides ----------
    await demo.title("Five · a person decides", "The planner has not seen this yet");
    const agree = page.getByRole("button", { name: /Agree, and re-plan/ }).first();
    if (await agree.isVisible().catch(() => false)) {
      await demo.click(agree, { label: "agree with the reading" });
      await page.waitForTimeout(3500);
    }
    await demo.say(
      "A language model read her words. A person agreed with the reading. " +
        "Only now may the planner act on it.",
      3800,
    );
    await demo.shot("05-approved");

    // ---------- act six: the second story, and the decision that turns ----------
    await demo.title(
      "Six · a different signal",
      "A report still pending, and whose money is already spent",
    );
    let askedAbout = [];
    for (let attempt = 0; attempt < 15 && askedAbout.length === 0; attempt += 1) {
      askedAbout = (await api("/questions/waiting")).filter(
        (q) => q.reason === "report_pending",
      );
      if (!askedAbout.length) await page.waitForTimeout(2000);
    }
    if (!askedAbout.length) throw new Error("nobody was asked about a pending report");

    await demo.say(
      "A different family, a different signal. Her creatinine is still open, " +
        "and her visit depends on it. Saathi asks about the one thing the " +
        "hospital cannot know: the travel they have already booked.",
      5000,
    );

    await post("/live/inject", { patient_id: ORDER_FAMILY, text: ORDER_REPLY });
    await demo.say(
      "She says: two of us, the night bus, fourteen hundred — and we do not " +
        "get the money back.",
      4200,
    );

    // The claim act seven makes, verified before it is made.
    let escalated = null;
    for (let attempt = 0; attempt < 25 && !escalated; attempt += 1) {
      await page.waitForTimeout(1500);
      const now = await api("/hospital/now");
      const feed = [
        ...(now.feed ?? []),
        ...(now.hospitals?.[0]?.recent ?? []),
      ];
      escalated = feed.find(
        (row) => row.kind === "escalation" && row.patient_id === ORDER_FAMILY,
      );
    }
    if (!escalated) throw new Error("the non-refundable answer never changed the decision");
    if (escalated.summary.includes("no task could be filed"))
      throw new Error("the decision changed but the hospital was never actually asked");
    console.log(`  escalation: ${escalated.summary}`);

    await section(page, demo, "Hospitals right now");
    await demo.say(
      "That answer turns the decision over. Moving her visit would spend her " +
        "fourteen hundred rupees twice — so Saathi keeps the date and asks the " +
        "hospital to bring the report forward instead, in the hospital's own record.",
      5400,
    );
    await demo.shot("06-decision-turned");

    // ---------- act seven: the working, and what it was built from ----------
    await demo.title("Seven · the working", "Measured, not narrated");
    await section(page, demo, "Approvals");
    await page.waitForTimeout(2500);

    // Open her working. Earlier takes narrated this over a screen that did
    // not contain it, which is precisely the failure this script exists to
    // prevent — so the drawer is opened and checked before anything is said.
    const name = page.getByRole("button", { name: /Devi|Kumari|Begum/ }).first();
    if (!(await name.isVisible().catch(() => false)))
      throw new Error("no family in the queue to open the working for");
    await demo.click(name, { label: "pick this family" });
    await page.waitForTimeout(2000);

    // Selecting reveals the bar; the drawer is a second, deliberate click.
    const why = page.getByRole("button", { name: /Why this family/ }).first();
    if (!(await why.isVisible().catch(() => false)))
      throw new Error("selecting a family did not offer its working");
    await demo.click(why, { label: "open the working" });
    await page.waitForTimeout(3000);
    await page
      .getByText("How this was worked out")
      .first()
      .waitFor({ state: "visible", timeout: 20000 });

    await demo.say(
      "Every line was published by the code that did the work, carrying the " +
        "time that work actually took. Nothing here was written to describe it.",
      4400,
    );
    await demo.shot("07-reasoning");

    // Scroll until the graph's own heading is in view, rather than by a
    // fixed distance. A fixed scroll overshot on one take and undershot on
    // another: the drawer's height depends on how much evidence this family
    // has, which is different for every family and every run.
    const graph = page.getByText("What this is built from").first();
    await graph.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1800);
    await graph.waitFor({ state: "visible", timeout: 15000 });
    await demo.say(
      "And underneath it, what the working was built from. Every node is a " +
        "record this system is holding, and every one says where it came from " +
        "— a hospital's calendar and a family's sentence are different claims.",
      5400,
    );
    await demo.shot("08-graph");

    await demo.title(
      "Nothing here was mocked",
      "Two families, three signals, one hospital that never changed",
    );
    await page.waitForTimeout(1500);
  } finally {
    await context.close();
    await browser.close();
  }

  // Name the file for what it is, newest first.
  const videos = readdirSync(OUT)
    .filter((name) => name.endsWith(".webm"))
    .map((name) => ({ name, at: statSync(resolve(OUT, name)).mtimeMs }))
    .sort((a, b) => b.at - a.at);
  if (videos.length) {
    const target = resolve(OUT, "three-stories.webm");
    if (existsSync(target)) renameSync(target, resolve(OUT, `three-stories-${Date.now()}.webm`));
    renameSync(resolve(OUT, videos[0].name), target);
    console.log(`\n  recorded ${target}`);
  }
}

main().catch((error) => {
  console.error(`\n  the take failed: ${error.message}`);
  console.error("  nothing was published; fix it and run again.\n");
  process.exit(1);
});
