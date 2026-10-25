/**
 * Does the stage still have what the recorder needs, where it needs it?
 *
 *     make demo-check
 *
 * The recorder (`autodemo.mjs`) drives the apps by CSS selector, inside named
 * frames, and a full run needs a Groq key and about four minutes. This checks the
 * contract it depends on in seconds and with no key: every frame exists, every
 * selector is in the right app, and the focus buttons really switch screens.
 * Run it after touching a class name or splitting an app.
 */

import { chromium } from "playwright";

const STAGE_URL = process.env.SAATHI_STAGE_URL ?? "http://localhost:5190";
const TIMEOUT = 20000;

const failures = [];
const check = (ok, what) => {
  console.log(`${ok ? "  ok " : "FAIL "} ${what}`);
  if (!ok) failures.push(what);
};

const browser = await chromium.launch({ headless: true });
try {
  const page = await (await browser.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
  await page.goto(`${STAGE_URL}/?phones=P-SHAMBHU`, { waitUntil: "domcontentloaded" });

  const frames = {
    phone: page.frameLocator('iframe[title^="Family app"]'),
    desk: page.frameLocator('iframe[title="Desk app"]'),
    nav: page.frameLocator('iframe[title="Navigator app"]'),
  };

  // The read-aloud button only exists once a message has been written, and a
  // message needs a language layer. Without a key that is not a broken stage.
  const health = await page.request.get(`${STAGE_URL}/api/health`).then((r) => r.json()).catch(() => ({}));
  const hasMessages = Boolean(health.language_layer);

  // [where, what, selector, optional text, needs a written message]
  const expected = [
    [page, "stage", ".story-bar button.btn.primary"],
    [page, "stage", ".story-progress"],
    [page, "stage", ".story-bar .segmented button", "Anita"],
    [page, "stage", ".st-focus button", "All"],
    [page, "stage", ".st-focus button", "Phone"],
    [page, "stage", ".st-focus button", "Desk"],
    [page, "stage", ".st-focus button", "Navigator"],
    [frames.phone, "phone", ".fx-app"],
    [frames.phone, "phone", ".fx-scroll"],
    [frames.phone, "phone", ".fx-speak", undefined, true],
    [frames.phone, "phone", ".fx-mic"],
    [frames.phone, "phone", ".fx-send"],
    [frames.phone, "phone", '.fx-langs button[title="Bengali"]'],
    [frames.desk, "desk", ".iss-text"],
    [frames.desk, "desk", ".iss-entry button"],
    [frames.nav, "navigator", ".hx-worklist"],
    [frames.nav, "navigator", ".hx-work"],
    [frames.nav, "navigator", ".hx-lens button", "Pathway"],
    [frames.nav, "navigator", ".hx-lens button", "Why this answer"],
    [frames.nav, "navigator", ".hx-row", "P-ANITA"],
  ];

  for (const [scope, app, selector, text, needsMessage] of expected) {
    if (needsMessage && !hasMessages) {
      console.log(`  skip ${app}: ${selector} (no language layer, so no message to read aloud)`);
      continue;
    }
    const locator = scope.locator(selector, text ? { hasText: text } : undefined).first();
    let found = true;
    try {
      await locator.waitFor({ state: "attached", timeout: TIMEOUT });
    } catch {
      found = false;
    }
    check(found, `${app}: ${selector}${text ? ` "${text}"` : ""}`);
  }

  // The things the recorder never needs but a person does: nothing from one role
  // has leaked into another.
  const absent = [
    [frames.nav, "navigator", ".iss-text", "has no issue reporter (that is the desk's)"],
    [frames.nav, "navigator", ".story-bar", "has no story bar (that is the stage's)"],
    [frames.desk, "desk", ".hx-worklist", "has no worklist (that is the navigator's)"],
    [frames.desk, "desk", ".story-bar", "has no story bar"],
  ];
  for (const [scope, app, selector, what] of absent) {
    check((await scope.locator(selector).count()) === 0, `${app} ${what}`);
  }

  // Focus: each mode shows exactly the screens it should.
  const visible = async () =>
    page.evaluate(() => ({
      phone: !!document.querySelector(".st-phone") && getComputedStyle(document.querySelector(".st-phone")).display !== "none",
      desk: getComputedStyle(document.querySelector('[data-screen="desk"]')).display !== "none",
      navigator: getComputedStyle(document.querySelector('[data-screen="navigator"]')).display !== "none",
    }));
  const modes = {
    All: { phone: true, desk: true, navigator: true },
    Phone: { phone: true, desk: false, navigator: false },
    Desk: { phone: false, desk: true, navigator: false },
    Navigator: { phone: false, desk: false, navigator: true },
  };
  for (const [mode, want] of Object.entries(modes)) {
    await page.locator(".st-focus button", { hasText: mode }).click();
    await page.waitForTimeout(150);
    const got = await visible();
    check(JSON.stringify(got) === JSON.stringify(want), `focus "${mode}" shows ${Object.keys(want).filter((k) => want[k]).join(", ")}`);
  }
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(`\n${failures.length} thing(s) the recorder depends on are missing or misplaced.`);
  process.exit(1);
}
console.log("\nthe stage has everything the recorder needs.");
