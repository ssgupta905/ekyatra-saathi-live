/**
 * Two hospitals, two different systems, one journey — driven and recorded.
 *
 *     make demo-two-hospital
 *
 * The other recorder (`autodemo.mjs`) films the family's phone and the staff
 * screens reacting to each other. This one films the claim underneath that:
 * Kamla is treated in Mumbai and has her bloods done in Gaya, the two
 * hospitals run unrelated systems that cannot see each other, and Saathi is
 * the only thing that sees both.
 *
 * **What is real.** Everything. The cancellation is a real `status-change`
 * against a real Bahmni; the connector really polls it; the disruption, the
 * holding message, the options and the write-back are the same code paths a
 * person's click runs. The second hospital is a real FHIR server. Nothing on
 * screen is a fixture.
 *
 * **What is staged** is only who presses what, and one honest substitution:
 * the Bahmni cancellation goes through Bahmni's API rather than its web UI,
 * because driving that UI needs a login this script will not perform for you.
 * On the day, a judge does it by hand in the Appointments screen and the rest
 * of the film is unchanged — that is the point of it being an API in the
 * first place. The caption says so rather than implying a button was pressed.
 *
 * Prerequisites, all checked before anything is recorded:
 *   - the API running with both hospitals configured (see the Makefile target)
 *   - the control centre running
 *   - Bahmni seeded: `make bahmni-seed-write`
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
const BAHMNI = process.env.SAATHI_BAHMNI_BASE_URL ?? "https://demo.standard.mybahmni.in";
const BAHMNI_USER = process.env.SAATHI_BAHMNI_USERNAME ?? "superman";
const BAHMNI_PASS = process.env.SAATHI_BAHMNI_PASSWORD ?? "Admin123";

//: The staff account the panel is driven as. A navigator, because approving a
//: scan-level option is a navigator's to make — the doctor gate is a separate
//: beat and this film is about the two hospitals, not the role split.
const STAFF_USER = process.env.SAATHI_STAFF_USER ?? "seema";
const STAFF_PASS = process.env.SAATHI_STAFF_PASSWORD ?? "saathi-dev";

const PATIENT = "EKY-KAMLA";
const SERVICE = "MRI machine 1";

const VIEWPORT = { width: 1600, height: 900 };
const BEAT = Number(process.env.SAATHI_DEMO_BEAT ?? 1100);

const auth = "Basic " + Buffer.from(`${BAHMNI_USER}:${BAHMNI_PASS}`).toString("base64");

async function bahmni(path, init = {}) {
  const response = await fetch(`${BAHMNI}/openmrs/ws/rest/v1${path}`, {
    ...init,
    headers: { Authorization: auth, "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) throw new Error(`bahmni ${path} -> ${response.status}`);
  return response.status === 204 ? null : response.json();
}

/** Kamla's standing MRI slot, which is the one the hospital cancels. */
async function kamlasSlot() {
  const today = new Date();
  const from = new Date(today.getTime() - 2 * 864e5);
  const to = new Date(today.getTime() + 30 * 864e5);
  const rows = await bahmni("/appointments/search", {
    method: "POST",
    body: JSON.stringify({ startDate: from.toISOString(), endDate: to.toISOString() }),
  });
  return (rows ?? []).find(
    (r) =>
      r?.patient?.identifier === PATIENT &&
      r?.service?.name === SERVICE &&
      r?.status === "Scheduled",
  );
}

/** Fail before the camera rolls, not three minutes into a take. */
async function checkReady() {
  const problems = [];

  for (const [what, url] of [
    ["the control centre", PANEL],
    ["the API", `${API}/api/health`],
  ]) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(4000) });
      if (!response.ok) problems.push(`${what} answered ${response.status} at ${url}`);
    } catch {
      problems.push(`${what} is not running at ${url}`);
    }
  }

  let slot = null;
  try {
    slot = await kamlasSlot();
    if (!slot) {
      problems.push(
        `Bahmni holds no scheduled "${SERVICE}" for ${PATIENT}. ` +
          `Run: make bahmni-seed-write`,
      );
    }
  } catch (error) {
    problems.push(`could not read Bahmni at ${BAHMNI}: ${error.message}`);
  }

  if (problems.length) {
    console.error("\nNot ready to record:\n");
    for (const problem of problems) console.error(`  - ${problem}`);
    console.error("");
    process.exit(1);
  }
  return slot;
}

async function main() {
  const slot = await checkReady();
  console.log(`Kamla's ${SERVICE} slot: ${new Date(slot.startDateTime).toISOString()}`);

  if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });
  const stills = resolve(OUT, "two-hospital-stills");
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
  await context.addInitScript(OVERLAY);
  const page = await context.newPage();
  const demo = new Demo(page, { viewport: VIEWPORT, beat: BEAT, stills });

  try {
    await page.goto(`${PANEL}/#/hospital`, { waitUntil: "domcontentloaded" });
    await demo.raiseTitle("Two hospitals", "One journey. Neither system can see the other.");

    // Sign in. Real mode means real accounts; the gate is part of the product.
    // Addressed by autocomplete rather than name/id, because the form has
    // neither — it labels its fields, which is the accessible thing to do and
    // happens to be the stable selector too.
    //
    // `isVisible()` does not wait — it answers about this instant. Called
    // straight after `domcontentloaded`, while React is still mounting, it
    // said "no form" and the sign-in was skipped silently; the only symptom
    // was a timeout twenty-five seconds later on a selector that was never
    // going to appear. So wait for the form or the signed-in screen, whichever
    // arrives, and then decide.
    const username = page.locator('input[autocomplete="username"]').first();
    const signedIn = page.locator(".today-tiles").first();
    await Promise.race([
      username.waitFor({ state: "visible", timeout: 25000 }).catch(() => {}),
      signedIn.waitFor({ state: "visible", timeout: 25000 }).catch(() => {}),
    ]);
    if (await username.isVisible().catch(() => false)) {
      await demo.type(username, STAFF_USER);
      await demo.type(page.locator('input[type="password"]').first(), STAFF_PASS);
      // The button, not Enter: it stays disabled until both fields have
      // values, so clicking it also proves React saw the typing.
      await demo.click(page.locator("button", { hasText: "Sign in" }).first(), {
        label: "sign in",
      });
    }
    await page.locator(".today-tiles").first().waitFor({ timeout: 25000 });
    await demo.dropTitle();

    // ---------- act one: who is watching what ----------
    await demo.say(
      "Mumbai runs Bahmni. Gaya runs a FHIR server. Saathi reads both through one adapter.",
      3200,
    );
    await demo.lookAt(page.locator(".today-tiles .ui-stat").nth(1));
    await demo.shot("both-connected");
    await demo.say("Two of three hospitals being read — bahmni and fhir.", 2600);

    await demo.scroll(page.locator("body"), 420);
    await demo.say(
      "Kamla is treated in Mumbai. Her creatinine is done in Gaya — nobody travels a thousand kilometres for a blood test.",
      3600,
    );
    await demo.shot("two-boards");

    // ---------- act two: the hospital changes something ----------
    await demo.title("The hospital changes its mind", "A real cancellation, in a real Bahmni");

    await demo.say(
      `Cancelling Kamla's ${SERVICE} in Bahmni now — on the day a judge does this by hand in the Appointments screen.`,
      3400,
    );
    await bahmni(`/appointments/${slot.uuid}/status-change`, {
      method: "POST",
      body: JSON.stringify({ toStatus: "Cancelled" }),
    });
    console.log("cancelled in Bahmni; waiting for the connector…");

    // The connector polls every three seconds. Wait for the board to say so
    // rather than sleeping a guessed number of seconds.
    await demo.say("Nobody told Saathi. It is reading Bahmni every three seconds.", 2800);
    await page.goto(`${PANEL}/#/hospital`, { waitUntil: "domcontentloaded" });
    const lost = page.locator(".hn-row", { hasText: "slot lost" }).first();
    await lost.waitFor({ timeout: 45000 });
    await demo.lookAt(lost);
    await demo.say("There it is — lifted to the top, because she is already travelling.", 3000);
    await demo.shot("slot-lost");

    // ---------- act three: a person decides ----------
    await demo.title("A person decides", "Saathi suggests. The desk approves.");
    await page.goto(`${PANEL}/#/approvals`, { waitUntil: "domcontentloaded" });

    const row = page.locator(".master-row", { hasText: PATIENT }).first();
    await row.waitFor({ timeout: 30000 });
    await demo.click(row, { label: "Kamla" });
    await demo.say("Ranked options, each with what it costs the family. No score.", 3000);
    await demo.shot("options");

    const welfare = page.locator(".opt-welfare").first();
    if (await welfare.isVisible().catch(() => false)) {
      await demo.lookAt(welfare);
      await demo.say(
        "The hospital caused this, so the family should not pay for it.",
        2600,
      );
    }

    const approve = page.locator(".option-card button", { hasText: "Approve" }).first();
    await demo.click(approve, { label: "approve" });
    await demo.say("Approved. Now it is written back into Bahmni's own diary.", 3000);
    await demo.shot("approved");

    // ---------- act four: the hospital's own record ----------
    await demo.title("Back in the hospital", "The new slot, in their system");
    const booked = await kamlasSlot();
    if (booked) {
      await demo.say(
        `Bahmni now holds ${SERVICE} for Kamla on ` +
          `${new Date(booked.startDateTime).toUTCString().slice(0, 16)}.`,
        3600,
      );
      console.log("write-back confirmed in Bahmni:", booked.uuid);
    } else {
      // Said out loud rather than quietly skipped: a film that implies a
      // booking that did not happen is worse than one that admits it.
      await demo.say(
        "The write-back did not land this run — the audit trail records the attempt.",
        3400,
      );
      console.warn("no rebooked slot found in Bahmni");
    }

    await page.goto(`${PANEL}/#/hospital`, { waitUntil: "domcontentloaded" });
    await page.locator(".today-tiles").first().waitFor({ timeout: 25000 });
    await demo.shot("after");
    await demo.title(
      "Neither hospital learned about the other",
      "Only Saathi saw both.",
      4200,
    );
  } finally {
    await demo.clear().catch(() => {});
    await context.close();
    await browser.close();
  }

  // Playwright names videos by an internal hash. Rename to something findable.
  const videos = readdirSync(OUT)
    .filter((f) => f.endsWith(".webm"))
    .map((f) => ({ f, at: statSync(resolve(OUT, f)).mtimeMs }))
    .sort((a, b) => b.at - a.at);
  if (videos.length) {
    const named = resolve(OUT, "two-hospital.webm");
    renameSync(resolve(OUT, videos[0].f), named);
    console.log(`\nrecorded: ${named}`);
    console.log(`stills:   ${stills}`);
  }
}

await main();
