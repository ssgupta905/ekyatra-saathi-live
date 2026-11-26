/**
 * The hospital's own screen, and what the agents did about it.
 *
 *     make demo-hospital
 *
 * Five acts. A person cancels an appointment in OpenEMR's real calendar;
 * Saathi notices within seconds; the agent work, the dependency graph and the
 * evidence chain are shown; a navigator approves a re-plan; and the new slot
 * appears back in the hospital's own diary.
 *
 * **What is real.** All of it. The cancellation is a human double-clicking an
 * appointment in a running OpenEMR and setting its status — the calendar
 * writes `pc_apptstatus` and never touches FHIR, and the connector finds out
 * by reading FHIR three seconds later, exactly as it would in a hospital.
 * The disruption, the holding message, the ranked options, the approval gate,
 * the ledger rows and the write-back are the same code paths a person's click
 * runs. Nothing on screen is a fixture.
 *
 * **What is staged** is only who presses what. There is no narration track and
 * no substituted API call: the earlier Bahmni film had to cancel over HTTP
 * because that instance was somebody else's hosted box. This one does not.
 *
 * Prerequisites, all checked before anything is recorded:
 *   - OpenEMR running and seeded (`make openemr-seed-write`)
 *   - the API running against it, and the control centre running
 */

import { chromium } from "playwright";
import { Demo, OVERLAY } from "./stagecraft.mjs";
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
const STAFF_USER = process.env.SAATHI_STAFF_USER ?? "seema";
const STAFF_PASS = process.env.SAATHI_STAFF_PASSWORD ?? "saathi-dev";

const PATIENT = "EKY-KAMLA";
const VIEWPORT = { width: 1600, height: 900 };
const BEAT = Number(process.env.SAATHI_DEMO_BEAT ?? 1100);
//: Days forward from the calendar's default (today) to the seeded slot.
const DAYS_AHEAD = Number(process.env.SAATHI_DEMO_DAYS_AHEAD ?? 3);

/** A staff token, so the film can ask the API where the slot ended up.
 *
 *  Read-only and off-camera: this is the script checking its own caption is
 *  true before it says it, not part of what is being demonstrated. */
async function apiToken() {
  try {
    const r = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username: STAFF_USER, password: STAFF_PASS }),
    });
    return r.ok ? (await r.json()).token : null;
  } catch {
    return null;
  }
}

/** Midnight today, for turning a date into "how many days forward". */
function startOfToday() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
}

async function ready() {
  const problems = [];
  for (const [what, url] of [
    ["the control centre", PANEL],
    ["the API", `${API}/api/health`],
    ["OpenEMR", `${EMR}/interface/login/login.php?site=default`],
  ]) {
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (!r.ok) problems.push(`${what} answered ${r.status} at ${url}`);
    } catch {
      problems.push(`${what} is not running at ${url}`);
    }
  }
  if (problems.length) {
    console.error("\nNot ready to record:\n");
    for (const p of problems) console.error(`  - ${p}`);
    console.error("");
    process.exit(1);
  }
}

/** Sign in to the control centre, if it asks. */
async function signIn(page, demo) {
  const username = page.locator('input[autocomplete="username"]').first();
  const inside = page.locator(".cc-main").first();
  // `isVisible()` does not wait, so race the two states rather than guessing
  // which one this load will settle into.
  await Promise.race([
    username.waitFor({ state: "visible", timeout: 25000 }).catch(() => {}),
    inside.waitFor({ state: "visible", timeout: 25000 }).catch(() => {}),
  ]);
  if (await username.isVisible().catch(() => false)) {
    await demo.type(username, STAFF_USER);
    await demo.type(page.locator('input[type="password"]').first(), STAFF_PASS);
    await demo.click(page.locator("button", { hasText: "Sign in" }).first(), {
      label: "sign in",
    });
  }
  await inside.waitFor({ timeout: 25000 });
}

/** Sign in to OpenEMR and return its calendar frame. */
async function openCalendar(page, demo) {
  await page.goto(`${EMR}/interface/login/login.php?site=default`, {
    waitUntil: "domcontentloaded",
  });
  await demo.type(page.locator("#authUser"), EMR_USER);
  await demo.type(page.locator("#clearPass"), EMR_PASS);
  await demo.click(page.locator("#login-button"), { label: "sign in to OpenEMR" });
  await page.waitForTimeout(9000);

  // "Ask again later", never "Submit": Submit opts the installation into
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

/** Walk the calendar forward to the day the appointment is on.
 *
 *  By the arrow, not by URL: the calendar ignores date parameters entirely
 *  and reloads on today, which looks like the navigation worked. */
async function goToDay(page, calendar, days) {
  for (let i = 0; i < days; i += 1) {
    await calendar
      .locator('[title*="Next"], .fa-chevron-right')
      .first()
      .click()
      .catch(() => {});
    await page.waitForTimeout(2200);
  }
}

async function main() {
  await ready();
  if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });
  const stills = resolve(OUT, "hospital-stills");
  if (!existsSync(stills)) mkdirSync(stills, { recursive: true });

  const headless = process.env.SAATHI_DEMO_HEADLESS === "true";
  const browser = await chromium.launch({
    headless,
    args: ["--force-device-scale-factor=1"],
  });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    recordVideo: { dir: OUT, size: VIEWPORT },
  });
  // Open the family's layers up front so act three is a scroll, not a hunt.
  await context.addInitScript(() => {
    try {
      localStorage.setItem(
        "saathi.layers.family",
        JSON.stringify(["why", "pathway", "evidence"]),
      );
    } catch {
      /* a blocked storage is not worth failing a recording over */
    }
  });
  await context.addInitScript(OVERLAY);

  const page = await context.newPage();
  // OpenEMR confirms the save with a dialog. Unhandled, it blocks the page
  // and the cancellation silently never happens.
  page.on("dialog", (d) => d.accept().catch(() => {}));
  const demo = new Demo(page, { viewport: VIEWPORT, beat: BEAT, stills });

  try {
    // ---------- act one: the hospital's own screen ----------
    await page.goto(`${EMR}/interface/login/login.php?site=default`, {
      waitUntil: "domcontentloaded",
    });
    await demo.raiseTitle("The hospital's own system", "OpenEMR. Not ours, not a mock.");
    await page.waitForTimeout(2200);
    await demo.dropTitle();

    const calendar = await openCalendar(page, demo);
    await demo.say("This is OpenEMR — a real hospital system, running its own calendar.", 3000);
    await goToDay(page, calendar, DAYS_AHEAD);
    await demo.shot("calendar");

    const slot = calendar.locator("div.event_appointment").filter({ hasText: /Devi|Kamla/ }).first();
    await slot.waitFor({ timeout: 20000 });
    await demo.say("Kamla Devi's MRI, on Friday. She travels a thousand kilometres for it.", 3400);

    await demo.title("The radiology desk changes its mind", "A person, in the hospital's screen");
    await slot.dblclick({ timeout: 15000 });
    await page.waitForTimeout(5500);

    const editor = page.frames().find((f) => /add_edit_event/i.test(f.url()));
    if (!editor) throw new Error("the appointment editor never opened");
    await demo.say("The desk opens the appointment and cancels it. Nothing tells Saathi.", 3400);
    await editor.selectOption('select[name="form_apptstatus"]', "x");
    await demo.shot("cancelling");
    await editor.locator("#form_save").click({ timeout: 12000 });
    await page.waitForTimeout(8000);
    console.log("cancelled in the OpenEMR UI");

    // ---------- act two: Saathi notices ----------
    await demo.title("Saathi notices", "Reading the hospital every three seconds");
    await page.goto(`${PANEL}/#/hospital`, { waitUntil: "domcontentloaded" });
    await signIn(page, demo);
    await page.evaluate(() => {
      location.hash = "#/hospital";
    });

    const lost = page.locator(".hn-row", { hasText: "slot lost" }).first();
    await lost.waitFor({ timeout: 45000 });
    await demo.lookAt(lost);
    await demo.say("There it is — lifted to the top, because she is already travelling.", 3200);
    await demo.shot("noticed");

    // ---------- act three: what the agents did ----------
    await demo.title("What the agents did", "Measured, sourced, and on the record");

    await page.goto(`${PANEL}/#/cohort`, { waitUntil: "domcontentloaded" });
    await page.locator(".feed .feed-row").first().waitFor({ timeout: 30000 }).catch(() => {});
    await demo.say("Every step the system took, with what it actually cost in milliseconds.", 3400);
    await demo.shot("agents");
    await demo.scroll(page.locator("body"), 400);

    // The dependency graph — edges, not just columns.
    await page.goto(`${PANEL}/#/families/${PATIENT}/pathway`, { waitUntil: "domcontentloaded" });
    // `attached`, not `visible`: an SVG path with no fill has no box, so
    // Playwright reports it hidden however well it renders. And a beat to
    // settle, because the edges are measured from the laid-out grid and the
    // first paint has them all at zero length.
    await page
      .locator("svg.board-edges path.board-edge")
      .first()
      .waitFor({ state: "attached", timeout: 30000 });
    await page.waitForTimeout(1800);
    await demo.say("Her care pathway as a graph: what is waiting on what.", 3200);
    await demo.shot("graph");

    // Why — record, rule, model, each named.
    await page.evaluate(() => {
      location.hash = location.hash.replace(/\/pathway$/, "/why");
    });
    await page.locator('[data-layer="why"] .trace .node').first().waitFor({ timeout: 25000 }).catch(() => {});
    await demo.say("And why — every claim naming whether it came from a record, a rule or a model.", 3600);
    await demo.shot("why");

    // The chain.
    await page.evaluate(() => {
      location.hash = location.hash.replace(/\/why$/, "/evidence");
    });
    await page.locator('[data-layer="evidence"]').first().waitFor({ timeout: 25000 }).catch(() => {});
    await demo.say("Hash-chained. The badge is a live recomputation, not a stored flag.", 3200);
    await demo.shot("ledger");

    // ---------- act four: a person decides ----------
    await demo.title("A person decides", "Saathi suggests. The desk approves.");
    await page.goto(`${PANEL}/#/approvals`, { waitUntil: "domcontentloaded" });
    const row = page.locator(".master-row", { hasText: PATIENT }).first();
    await row.waitFor({ timeout: 30000 });
    await demo.click(row, { label: "Kamla" });
    await demo.say("Two options, each with what it costs the family. No score.", 3000);
    await demo.shot("options");

    const welfare = page.locator(".opt-welfare").first();
    if (await welfare.isVisible().catch(() => false)) {
      await demo.lookAt(welfare);
      await demo.say("The hospital caused this, so the family should not pay for it.", 2800);
    }
    await demo.click(
      page.locator(".option-card button", { hasText: "Approve" }).first(),
      { label: "approve" },
    );
    await demo.say("Approved — and written straight back into the hospital's diary.", 3200);
    await demo.shot("approved");

    // ---------- act five: back in the hospital ----------
    await demo.title("Back in the hospital", "The new slot, in their system");
    // The re-plan moves the slot, so act five is a *different* day from act
    // one. Walking back to the original day shows the cancelled appointment
    // under a caption claiming the new one — which is how the first take of
    // this film managed to be wrong while every underlying system was right.
    const token = await apiToken();
    const rebookedOn = await fetch(`${API}/api/patients/${PATIENT}/steps`, {
      headers: token ? { authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((steps) => steps.find((s) => s.kind === "scan")?.scheduled_for ?? null)
      .catch(() => null);
    const days = rebookedOn
      ? Math.round((new Date(rebookedOn) - startOfToday()) / 86400000)
      : DAYS_AHEAD;
    console.log(`the scan now sits on ${rebookedOn} (${days} days out)`);

    const calendar2 = await openCalendar(page, demo);
    await goToDay(page, calendar2, days);
    await page.waitForTimeout(2500);
    const onScreen = await calendar2
      .locator("div.event_appointment")
      .filter({ hasText: /Devi|Kamla/ })
      .count();
    console.log(`Kamla's appointments on ${rebookedOn}: ${onScreen}`);
    // Only claim it if it is there. A caption is a statement about what the
    // audience is looking at, and one that is wrong is worse than none.
    await demo.say(
      onScreen > 0
        ? "OpenEMR holds the new appointment. Nobody retyped anything."
        : "The re-plan is recorded; the hospital's calendar is not showing it here.",
      3400,
    );
    await demo.shot("rebooked");

    await demo.title(
      "One system saw the whole journey",
      "The hospital ran its clinic. Saathi ran the family's trip.",
      4200,
    );
  } finally {
    await demo.clear().catch(() => {});
    await context.close();
    await browser.close();
  }

  const videos = readdirSync(OUT)
    .filter((f) => f.endsWith(".webm"))
    .map((f) => ({ f, at: statSync(resolve(OUT, f)).mtimeMs }))
    .sort((a, b) => b.at - a.at);
  if (videos.length) {
    const named = resolve(OUT, "hospital-demo.webm");
    renameSync(resolve(OUT, videos[0].f), named);
    console.log(`\nrecorded: ${named}`);
    console.log(`stills:   ${stills}`);
  }
}

await main();
