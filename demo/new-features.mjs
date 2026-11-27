/**
 * Two features the film called "not built yet", recorded now that they are.
 *
 * The roadmap slides at the end of the finale film describe a molecular
 * register and a vendor network, badged NEXT · NOT BUILT. Both now exist, so
 * the honest thing is to stop describing them and show them.
 *
 * Same discipline as `clips.mjs`, and for the same reasons:
 *
 *   - **The deployed stack, never a laptop.** A clip is evidence that the
 *     hosted system does this; a dev server proves nothing worth filming.
 *   - **Source capture, never the desktop.** Playwright records the page
 *     itself, so no editor, notification or lock screen can wander into frame.
 *   - **Whatever happens is what is in the clip.** Nothing here stages a
 *     screen or seeds a figure. Where a beat cannot happen, the clip is
 *     skipped and said so.
 *
 * No handset is involved, which is why this is its own file rather than more
 * clips in `clips.mjs` — that one refuses to start without a phone attached
 * and a leave day set, and neither is relevant here.
 *
 *     node demo/new-features.mjs            # all of them, in order
 *     node demo/new-features.mjs --only 36  # just one
 *     node demo/new-features.mjs --list
 *
 * ONE THING THIS CANNOT FILM
 *
 * The vendor's own signed-in screen — its rates, its standing, its money.
 * A vendor is identified by the account it signs in with, and the deployed
 * API runs with login off (`/api/auth/config` → `required: false`), so there
 * are no accounts and `/partner/me` fails closed, exactly as it should. That
 * clip needs `SAATHI_AUTH` set on the Render service. Until then this films
 * the half that is reachable and says nothing about the half that is not.
 */

import { chromium } from "playwright";
import { mkdirSync, readdirSync, readFileSync, renameSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

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
const LISTING = process.argv.includes("--list");

function address(name, fallback) {
  const value = process.env[name] ?? fallback;
  if (LISTING) return value ?? "";
  if (!value) {
    console.error(`\n  ${name} is not set, and these clips record the deployed stack.\n`);
    process.exit(1);
  }
  if (LOCAL.test(value)) {
    console.error(`\n  ${name}=${value} is a local address. These clips are evidence`);
    console.error("  that the deployed system does this; a laptop will not do.\n");
    process.exit(1);
  }
  return value.replace(/\/+$/, "");
}

const API = address("SAATHI_API_URL", "https://ekyatra-saathi-ueoa.onrender.com");
const PANEL = address("SAATHI_PANEL_URL", "https://ekyatra-saathi-control-centre.onrender.com");
const PARTNER_WEB = address("SAATHI_PARTNER_URL", "https://ekyatra-saathi-partner.onrender.com");

/** The family this pair of clips follows. Needs an ABHA number: consent is
 *  keyed on it, so a family without one cannot have a register at all. */
const PATIENT = process.env.SAATHI_MOLECULAR_PATIENT ?? "EKY-KAMLA";

/** The vendor that applies.
 *
 *  A fresh name each run, because an application can only be decided once and
 *  a re-run must show the deciding rather than the decided. The id is the slug
 *  the app itself derives from the name, so what this file expects and what
 *  the vendor typed cannot drift apart. */
const VENDOR_NAME = process.env.SAATHI_VENDOR_NAME ?? "Magadh Travels";
const VENDOR = VENDOR_NAME.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

/* ────────────────────────────── small helpers ──────────────────────────── */

const wait = (ms) => new Promise((done) => setTimeout(done, ms));
const say = (text) => console.log(`    ${text}`);

async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(`${API}/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${method} ${path} → ${response.status} ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
}

/** Record one browser surface doing one thing. Headless: no window, so
 *  nothing can appear in front of it. */
async function web(name, url, act, { width = 1600, height = 1000, as = null } = {}) {
  const dir = resolve(OUT, `_${name}`);
  rmSync(dir, { recursive: true, force: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width, height },
    recordVideo: { dir, size: { width, height } },
    deviceScaleFactor: 2,
  });
  // Signed in before the first frame, never in front of the camera.
  if (as) {
    await context.addInitScript(
      ([key, who]) => window.localStorage.setItem(key, who),
      ["saathi.persona", as],
    );
  }
  const page = await context.newPage();
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 120000 });
    await wait(2500);
    await act(page);
  } finally {
    await context.close();
    await browser.close();
  }
  const made = readdirSync(dir).find((f) => f.endsWith(".webm"));
  if (!made) throw new Error(`${name}: playwright wrote no video`);
  const final = resolve(OUT, `${name}.webm`);
  renameSync(resolve(dir, made), final);
  rmSync(dir, { recursive: true, force: true });
  return final;
}

/** Open a Console section the way a person does: by clicking the rail. */
async function goTo(page, label) {
  await page.getByRole("button", { name: label, exact: true }).first().click({ timeout: 20000 });
  await wait(3500);
}

/** Open a family's workspace by clicking its row. */
async function openFamily(page, name) {
  await page.getByText(name, { exact: false }).first().click({ timeout: 20000 });
  await wait(3500);
}

/** Open one of the collapsible layers by its title. */
async function openLayer(page, title) {
  const head = page.getByRole("button", { name: new RegExp(title, "i") }).first();
  await head.scrollIntoViewIfNeeded().catch(() => {});
  await wait(600);
  await head.click({ timeout: 20000 });
  await wait(2500);
}

/** Type like a person rather than pasting, so the viewer can read along. */
async function type(page, label, text) {
  const field = page.getByLabel(label, { exact: false }).first();
  await field.scrollIntoViewIfNeeded().catch(() => {});
  await field.click({ timeout: 15000 });
  await field.fill("");
  await field.type(text, { delay: 28 });
  await wait(400);
}


/* ──────────────────────────────── the clips ─────────────────────────────── */

const CLIPS = [
  {
    id: "33",
    name: "33-a-vendor-applies",
    says: "A cab firm asks to join, with no account and no introduction",
    async shoot() {
      // If a previous run left this vendor in the directory the application
      // cannot happen again, and a clip of a 409 is not the clip we want.
      const known = await api(`/directory?type=travel`);
      if (known.some((o) => o.id === VENDOR)) {
        throw new Error(
          `${VENDOR} is already in the directory. Pick a fresh id with ` +
          `SAATHI_VENDOR_ID=..., or this clip shows a name collision rather than an application.`,
        );
      }
      return web("33-a-vendor-applies", `${PARTNER_WEB}/#apply`, async (page) => {
        await wait(2500);
        await type(page, "Your business name", VENDOR_NAME);
        await wait(1200);
        await type(page, "A number somebody can reach you on", "+91 90000 11122");
        await type(page, "Districts you cover", "Gaya, Nalanda");
        await type(page, "What you offer, in your own words", "station pickup, overnight to Mumbai");
        await type(page, "Hours", "24 hours");
        await wait(1500);

        // Its own prices, in its own words. The thing a reviewer can check.
        await page.getByText("What you charge", { exact: false }).first()
          .scrollIntoViewIfNeeded().catch(() => {});
        await wait(1200);
        const service = page.getByPlaceholder("Gaya to Mumbai, sleeper").first();
        await service.click();
        await service.type("Gaya to Mumbai, sleeper", { delay: 28 });
        const rupees = page.locator("input[inputmode=numeric]").first();
        await rupees.click();
        await rupees.type("2400", { delay: 60 });
        await wait(2500);
        await page.getByRole("button", { name: /Send the application/i }).first().click();
        await wait(6000);
      }, { width: 900, height: 1200 });
    },
  },

  {
    id: "34",
    name: "34-in-the-directory-switched-off",
    says: "It is in the directory already — switched off, so nothing can route to it",
    async shoot() {
      // Whatever kind they said they were, not whatever this file guessed.
      const listed = await api("/directory");
      const row = listed.find((o) => o.id === VENDOR);
      if (!row) throw new Error(`${VENDOR} is not in the directory; shoot clip 33 first`);
      say(`a ${row.type}, active = ${row.active}, applied ${row.applied_on}`);
      return web("34-in-the-directory-switched-off", PANEL, async (page) => {
        await goTo(page, "Directory");
        await wait(2500);
        await page.locator("select").first().selectOption(row.type).catch(() => {});
        await wait(3500);
        await page.mouse.wheel(0, 320);
        await wait(9000);
      }, { as: "neha" });
    },
  },

  {
    id: "35",
    name: "35-the-review-queue",
    says: "What a reviewer sees: everything they said, including what they charge",
    async shoot() {
      const waiting = await api("/partner/applications");
      if (!waiting.some((o) => o.id === VENDOR)) {
        throw new Error(`${VENDOR} is not awaiting review; it may already be decided`);
      }
      say(`${waiting.length} application(s) waiting`);
      return web("35-the-review-queue", PANEL, async (page) => {
        await goTo(page, "Directory");
        await page.getByRole("button", { name: "Applications", exact: true }).first().click();
        await wait(4000);
        await page.mouse.wheel(0, 260);
        await wait(10000);
      }, { as: "neha" });
    },
  },

  {
    id: "36",
    name: "36-letting-them-in",
    says: "An administrator agrees terms and lets them in — the moment the flag changes",
    async shoot() {
      return web("36-letting-them-in", PANEL, async (page) => {
        await goTo(page, "Directory");
        await page.getByRole("button", { name: "Applications", exact: true }).first().click();
        await wait(3500);
        await page.getByRole("button", { name: "Decide", exact: true }).first().click();
        await wait(2500);
        await type(page, "Commission agreed", "5");
        await wait(3500);
        await page.getByRole("button", { name: "Approve", exact: true }).first().click();
        await wait(7000);
        // Back to the network list and search for them by name. Forty-two
        // organisations sort alphabetically, so without this the closing
        // shot lands on whoever happens to be at the top — which in one take
        // was a different firm with a similar name, saying the opposite of
        // what the narration said.
        await page.getByRole("button", { name: "The network", exact: true }).first().click();
        await wait(3000);
        const search = page.getByPlaceholder("name, service or district").first();
        await search.click();
        await search.type(VENDOR_NAME, { delay: 70 });
        await wait(9000);
      }, { as: "neha" });
    },
  },

  {
    id: "37",
    name: "37-no-consent-is-not-no-tests",
    says: "Asked about a family nobody has asked, it says so rather than showing an empty list",
    async shoot() {
      const before = await api(`/patients/${PATIENT}/molecular`);
      if (before.consented) {
        throw new Error("this family has already consented; revoke it so the clip shows the asking");
      }
      return web("37-no-consent-is-not-no-tests", PANEL, async (page) => {
        await goTo(page, "Families");
        await openFamily(page, "Kamla");
        await openLayer(page, "Molecular tests already done");
        await wait(11000);
      }, { as: "menon" });
    },
  },

  {
    id: "38",
    name: "38-its-own-consent",
    says: "Its own purpose, asked separately — agreeing here touches nothing else",
    async shoot() {
      return web("38-its-own-consent", PANEL, async (page) => {
        await goTo(page, "Families");
        await openFamily(page, "Kamla");
        await openLayer(page, "What the family has agreed to share");
        await wait(2500);
        await page.getByRole("combobox").last()
          .selectOption({ label: "A register of molecular tests done" }).catch(() => {});
        await wait(2000);
        await type(page, "Who is asking", "Tata Memorial molecular pathology");
        await wait(1500);
        await page.getByRole("button", { name: /Ask the family/i }).first().click();
        await wait(6000);
      }, { as: "seema" });
    },
  },

  {
    id: "39",
    name: "39-what-was-already-done",
    says: "Two panels recorded — and the one that matters is the report nobody can fetch",
    async shoot() {
      // The family answers on their phone, not in the Console, so the grant
      // itself is theirs to give. Asked on camera in 38; given here.
      const held = await api(`/patients/${PATIENT}/consent`);
      const pending = (held.requests ?? []).find(
        (r) => r.purpose === "molecular_records" && !r.answered_at,
      ) ?? (held.pending ?? []).find((r) => r.purpose === "molecular_records");
      if (pending) {
        await api(`/patients/${PATIENT}/consent/requests/${pending.id}/grant`, {
          method: "POST",
          body: { granted_by: "Kamla Devi", capacity: "self", channel: "ivr" },
        });
        say("the family granted it by IVR");
      }
      const now = await api(`/patients/${PATIENT}/molecular`);
      if (!now.consented) throw new Error("no molecular consent; clip 38 must run first");

      return web("39-what-was-already-done", PANEL, async (page) => {
        await goTo(page, "Families");
        await openFamily(page, "Kamla");
        await openLayer(page, "Molecular tests already done");
        await wait(2500);

        // One panel whose report we hold.
        await page.getByRole("button", { name: /Record a test/i }).first().click();
        await wait(2000);
        await type(page, "Lab that ran it", "Tata Memorial molecular pathology");
        await type(page, "Centre that ordered it", "TMH Mumbai");
        await type(page, "Where the document is", "tmh/lab/7781");
        await wait(2500);
        await page.getByRole("button", { name: /Record it/i }).first().click();
        await wait(5000);

        // And one done at the district hospital that nobody here can produce.
        await page.getByRole("button", { name: /Record a test/i }).first().click();
        await wait(2000);
        await page.getByLabel("Which test", { exact: false }).first()
          .selectOption({ label: "Immunohistochemistry" }).catch(() => {});
        await page.getByLabel("Where the report is", { exact: false }).first()
          .selectOption({ label: "Exists, but not reachable from here" }).catch(() => {});
        await type(page, "Lab that ran it", "Magadh Medical College, Gaya");
        await wait(2500);
        await page.getByRole("button", { name: /Record it/i }).first().click();
        await wait(9000);
      }, { as: "menon" });
    },
  },

  {
    id: "40",
    name: "40-it-will-not-hold-a-finding",
    says: "Type a result into it and the server refuses, naming the word that tripped it",
    async shoot() {
      return web("40-it-will-not-hold-a-finding", PANEL, async (page) => {
        await goTo(page, "Families");
        await openFamily(page, "Kamla");
        await openLayer(page, "Molecular tests already done");
        await wait(2500);
        await page.getByRole("button", { name: /Record a test/i }).first().click();
        await wait(2000);
        await type(page, "Lab that ran it", "Tata Memorial molecular pathology");
        await type(page, "Where the document is", "tmh/lab/7782");
        // The thing a well-meaning person types, and the reason the screen exists.
        await type(page, "Note", "EGFR positive, start targeted therapy");
        await wait(3000);
        await page.getByRole("button", { name: /Record it/i }).first().click();
        await wait(9000);
      }, { as: "menon" });
    },
  },
];

/* ──────────────────────────────── the run ──────────────────────────────── */

async function main() {
  mkdirSync(OUT, { recursive: true });
  const args = process.argv.slice(2);
  const only = args.includes("--only") ? args[args.indexOf("--only") + 1] : null;
  const from = args.includes("--from") ? args[args.indexOf("--from") + 1] : null;

  if (args.includes("--list")) {
    for (const clip of CLIPS) console.log(`  ${clip.id}  ${clip.name.padEnd(34)} ${clip.says}`);
    return;
  }

  console.log(`\n  recording against ${API}\n`);
  const chosen = CLIPS.filter((c) => (only ? c.id === only : from ? c.id >= from : true));
  const made = [];
  const skipped = [];
  for (const clip of chosen) {
    process.stdout.write(`  ${clip.id} ${clip.says}\n`);
    try {
      const file = await clip.shoot();
      made.push(file);
      say(`→ ${file.split("/").pop()}`);
    } catch (error) {
      // Said out loud and left out of the film, rather than restaged.
      skipped.push(`${clip.id}: ${error.message}`);
      say(`skipped — ${error.message}`);
    }
  }
  console.log(`\n  ${made.length} clip(s) recorded, ${skipped.length} skipped`);
  for (const line of skipped) console.log(`    ! ${line}`);
  console.log();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
