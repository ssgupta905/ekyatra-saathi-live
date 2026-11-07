/**
 * Short clips of the deployed apps, recorded one subject at a time.
 *
 *     SAATHI_ADMIN_PASSWORD=… node record-clips.mjs partner
 *
 * Not the autodemo. That drives the local demo stage end to end and produces
 * one long film; this records the pieces the 7 November set is missing, each
 * as its own file so they can be cut in without re-recording the rest.
 *
 * It drives the **deployed** apps, because that is what will be shown. The
 * only thing injected is the sign-in token: typing a password on camera would
 * put it in the footage, and a recording is not the place for a credential.
 */

import { chromium } from "playwright";
import { mkdirSync, readdirSync, renameSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Demo, OVERLAY } from "./stagecraft.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = process.env.SAATHI_CLIPS_DIR
  ?? resolve(process.env.HOME ?? HERE, "Downloads/demo-recordings");

const API = process.env.SAATHI_API_URL ?? "https://ekyatra-saathi-ueoa.onrender.com";
const CONTROL = process.env.SAATHI_CONTROL_URL ?? "https://ekyatra-saathi-control-centre.onrender.com";
const PARTNER = process.env.SAATHI_PARTNER_URL ?? "https://ekyatra-saathi-partner.onrender.com";

const VIEWPORT = { width: 1600, height: 1000 };
const BEAT = Number(process.env.SAATHI_DEMO_BEAT ?? 1100);

/** Render's free tier sleeps; the first call after that takes most of a minute. */
async function wake(label, url) {
  process.stdout.write(`  waking ${label}… `);
  const started = Date.now();
  for (let i = 0; i < 4; i += 1) {
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(90_000) });
      if (r.ok) return console.log(`${((Date.now() - started) / 1000).toFixed(0)}s`);
    } catch {
      /* cold start; try again */
    }
  }
  throw new Error(`${label} did not wake: ${url}`);
}

async function signIn(username, password) {
  const r = await fetch(`${API}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
    signal: AbortSignal.timeout(90_000),
  });
  if (!r.ok) throw new Error(`sign-in failed for ${username}: ${r.status}`);
  return (await r.json()).token;
}

/** Put the token where the app looks, before any script runs. */
function carryToken(context, token, origin) {
  return context.addInitScript(
    ([key, value]) => {
      try {
        window.localStorage.setItem(key, value);
      } catch {
        /* storage blocked; the app will ask for a sign-in and the clip fails loudly */
      }
    },
    ["saathi.token", token],
  );
}

async function record(name, { token, origin, play }) {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    headless: process.env.SAATHI_DEMO_HEADLESS === "true",
    args: ["--force-device-scale-factor=1"],
  });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    recordVideo: { dir: OUT, size: VIEWPORT },
  });
  await context.addInitScript(OVERLAY);
  if (token) await carryToken(context, token, origin);
  const page = await context.newPage();
  const demo = new Demo(page, { viewport: VIEWPORT, beat: BEAT });

  try {
    await play(page, demo);
  } finally {
    await context.close();
    await browser.close();
  }

  const newest = readdirSync(OUT)
    .filter((f) => f.endsWith(".webm") && /^[0-9a-f]{8,}|^page@/.test(f))
    .map((f) => ({ f, t: statSync(resolve(OUT, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t)[0];
  if (newest) {
    const named = resolve(OUT, `${name}.webm`);
    renameSync(resolve(OUT, newest.f), named);
    console.log(`\n  ${named}`);
  }
}

/* ── the clips ───────────────────────────────────────────────────────────── */

const CLIPS = {
  /**
   * The partner app. Absent from every recording so far, and it is the only
   * screen in the system belonging to someone outside the hospital.
   */
  async partner() {
    const password = process.env.SAATHI_ADMIN_PASSWORD;
    if (!password) throw new Error("set SAATHI_ADMIN_PASSWORD");
    await wake("API", `${API}/api/health`);
    await wake("partner app", PARTNER);

    const token = await signIn("ola", password).catch(() => null);
    if (!token) {
      throw new Error(
        "no 'ola' partner account on the deployed service — create one in the " +
          "control centre (Registries > staff accounts) bound to cab-ola",
      );
    }

    await record("12-partner-app", {
      token,
      origin: PARTNER,
      play: async (page, demo) => {
        await page.goto(PARTNER, { waitUntil: "networkidle" });
        await page.waitForTimeout(2500);

        await demo.title("The vendor's own screen", "A cab firm, signing in for itself");
        await demo.say(
          "Everyone a journey leans on gets a screen. This is the cab firm's.",
          3400,
        );
        await demo.say(
          "It is not staff. It sees the jobs its own organisation was asked to " +
            "do, and nothing about anybody's care.",
          4000,
        );

        const job = page.locator(".pt-job").first();
        await demo.lookAt(job);
        await demo.say(
          "A first name, a district, and a day only when the plan promises one.",
          3600,
        );
        await demo.say(
          "The phone number is missing on purpose: this family has not agreed " +
            "to share it, and the card says so rather than leaving a blank.",
          4400,
        );

        await demo.scroll(page.locator(".pt-scroll"), 240);
        await demo.say("Three answers, because three is what a vendor actually gives.", 3400);
        await demo.clear();
        await page.waitForTimeout(1200);
      },
    });
  },

  /**
   * Onboarding, and the one stage the 7 November set never captured: medical
   * background. It is not a screen that was skipped for time — it is the stage
   * that proves the sixth invariant, so leaving it out of the footage left the
   * strongest claim in the system unshown.
   */
  async onboarding() {
    const password = process.env.SAATHI_ADMIN_PASSWORD;
    if (!password) throw new Error("set SAATHI_ADMIN_PASSWORD");
    await wake("API", `${API}/api/health`);
    await wake("control centre", CONTROL);

    const token = await signIn("admin", password);

    await record("16-onboarding-medical-background", {
      token,
      origin: CONTROL,
      play: async (page, demo) => {
        await page.goto(CONTROL, { waitUntil: "networkidle" });
        await page.waitForTimeout(3500);

        await demo.title("Taking a family on", "Seven stages, each saved on its own");
        await demo.say(
          "A family is registered once and taken through the stages over days, " +
            "not in one sitting at a counter.",
          4000,
        );

        await demo.click(page.getByRole("button", { name: "Onboarding", exact: true }));
        //: The stage list loads from the API. Waiting for the tab itself rather
        //: than a fixed delay is what the first attempt at this clip got wrong:
        //: the screen was still loading when the camera moved on.
        await page.getByRole("button", { name: "Medical background" }).waitFor({ timeout: 60_000 });
        await page.waitForTimeout(1200);

        const stages = page.locator(".cc-stages");
        await demo.lookAt(stages);
        await demo.say(
          "Seven stages, each ticked off on its own. Anita's outstanding one is " +
            "the agreement to share — the family has not answered it yet.",
          4400,
        );

        await demo.click(page.getByRole("button", { name: "Medical background" }));
        await page.waitForTimeout(1600);
        await demo.say(
          "Medical background, as the family reports it — and only as the family " +
            "reports it.",
          4000,
        );
        await demo.say(
          "No report is uploaded here. Nothing a pathologist wrote enters Saathi " +
            "at any point, in this form or anywhere else.",
          4600,
        );
        await demo.say(
          "This stage is kept apart: doctors and administrators can see it, a " +
            "navigator cannot, and it never reaches the planner or a message.",
          4800,
        );

        await demo.clear();
        await page.waitForTimeout(1200);
      },
    });
  },
};

const which = process.argv[2];
if (!CLIPS[which]) {
  console.error(`usage: node record-clips.mjs <${Object.keys(CLIPS).join("|")}>`);
  process.exit(1);
}
await CLIPS[which]();
