/**
 * The automatic demo: a real browser, driven, recorded.
 *
 *     make demo-video
 *
 * Playwright moves a real cursor, types into real fields and clicks real
 * buttons against the running console. Nothing is simulated at the app layer —
 * every Advance press runs the same `LiveRunner` method a person's click would,
 * the planner really re-runs, Groq really writes the family's message, and the
 * guard really reads it. The recording differs slightly between runs because
 * the model output does, which is the point: a demo that produced identical
 * frames every time would be a video, not a run.
 *
 * Two things are added for the camera and neither touches the app. A cursor is
 * drawn, because an OS pointer does not appear in a screen recording. And a
 * caption bar narrates, because an audience watching silent automation cannot
 * tell which part was the clever bit.
 */

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "../recordings");

const CONSOLE_URL = process.env.SAATHI_CONSOLE_URL ?? "http://localhost:5173";
const API_URL = process.env.SAATHI_API_URL ?? "http://localhost:8001";
const VIEWPORT = { width: 1440, height: 900 };

/** Slow enough to follow on a projector, quick enough to hold a room. */
const BEAT = Number(process.env.SAATHI_DEMO_BEAT ?? 900);

/* ── the camera layer: a cursor and a caption, injected, app untouched ──── */

const OVERLAY = `
  (() => {
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
  // A rehearsable demo starts from the same world every time. Only the model's
  // words differ between runs.
  await reset();

  const browser = await chromium.launch({
    headless: process.env.SAATHI_DEMO_HEADLESS !== "false",
    args: ["--force-device-scale-factor=1"],
  });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    recordVideo: { dir: OUT, size: VIEWPORT },
  });
  await context.addInitScript(OVERLAY);
  const page = await context.newPage();
  const demo = new Demo(page);

  try {
    await page.goto(CONSOLE_URL, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".story-bar", { timeout: 20000 });
    await page.waitForTimeout(1200);

    await demo.say(
      "EKYATRA Saathi. Families travel hundreds of kilometres for cancer care. " +
        "This is what happens when the hospital has a bad day.",
      2800,
    );

    /* ---------- Story 1: the hospital side ---------- */

    await demo.say("Story one. Shambhu Prasad, 1,771 km from Mumbai, booked for an MRI.", 2300);

    // Scoped to the story bar — the clock has its own "Advance one day" button.
    const advance = page.locator(".story-bar button.btn.primary");

    await demo.say("7:40 am. The radiology desk reports MRI-2 out of service.", 1900);
    await demo.click(advance, { label: "advance" });
    await page.waitForTimeout(2600);
    await demo.say(
      "Watch the order: every affected family is told not to travel BEFORE " +
        "anything works out a new date.",
      3000,
    );

    await demo.say("The family writes back. Groq composes it; the real guard reads it.", 2200);
    await demo.click(advance);
    await page.waitForTimeout(3200);

    await demo.say(
      "Saathi fetched the journey from Gaya — 20 hours by road, from OpenStreetMap, " +
        "not a number anybody typed.",
      3000,
    );

    await demo.say("A navigator approves. A person decides anything touching treatment.", 2200);
    await demo.click(advance);
    await page.waitForTimeout(3000);

    await demo.say("The family confirms on the voice line.", 1700);
    await demo.click(advance);
    await page.waitForTimeout(2600);

    await demo.say(
      "Every dot is something that actually happened, with the measured time it took.",
      2800,
    );

    /* ---------- the hospital's own screens ---------- */

    await demo.clear();
    await demo.click(page.getByRole("button", { name: "Sign in as one person" }));
    await page.waitForTimeout(900);

    await demo.say("The same run, from the hospital's side.", 1800);
    const boards = page.locator(".view-tabs button", { hasText: "Plan boards" });
    await demo.click(boards);
    await page.waitForTimeout(1300);

    await demo.say(
      "Every family's pathway. Columns are the order care happens in — " +
        "so you can see what is waiting on what.",
      3000,
    );

    const firstBoard = page.locator(".board-row").first();
    await demo.click(firstBoard);
    await page.waitForTimeout(1600);
    await demo.say(
      "Booked dates and forecast dates are kept apart: one the hospital committed to, " +
        "one a calibrated interval.",
      3200,
    );

    /* ---------- Story 2: maintenance ---------- */

    await demo.clear();
    await demo.click(page.getByRole("button", { name: "Story view" }));
    await page.waitForTimeout(900);
    const anita = page.locator(".story-bar .segmented button", { hasText: "Anita Devi" });
    await demo.click(anita);
    await page.waitForTimeout(1200);

    await demo.say(
      "Story two. Anita Devi, in maintenance — 17 doses, an echo before every fourth.",
      2600,
    );
    await demo.say("The hub's only echo cardiologist goes on emergency leave.", 2000);

    const advance2 = page.locator(".story-bar button.btn.primary");
    const lines = [
      "The desk reports it. The hub's only echo cardiologist is away for a week.",
      "Her daughter asks what happens to dose 13. The guard allows a process answer only — never a clinical one.",
      "Dr Sinha chooses. One option was removed by a care rule before she ever saw it.",
      "Then the drug delivery is late.",
      "The second disruption makes the plan better than the original: one trip instead of two.",
      "The family confirms — her husband on the voice line, her daughter on WhatsApp.",
    ];
    // Run the story out rather than pressing a fixed number of times. Counting
    // narration lines stops early the moment the story gains a beat, and
    // breaking on a disabled button cannot tell "busy" from "finished" — both
    // of which cut Anita's story short. The progress counter is unambiguous and
    // is what a presenter is reading anyway.
    for (let i = 0; i < 12; i += 1) {
      const progress = await page.locator(".story-progress").first().textContent();
      const [done, total] = (progress ?? "0/0").split("/").map(Number);
      if (!Number.isFinite(total) || done >= total) break;
      if (lines[i]) await demo.say(lines[i], 2100);
      await demo.click(advance2);
      await page.waitForTimeout(2600);
    }

    await demo.say(
      "Synthetic families. Real planner, real tools, real model, real guard — " +
        "and a person decides anything that touches treatment.",
      3600,
    );
    await demo.clear();
    await page.waitForTimeout(600);
  } finally {
    await context.close();
    await browser.close();
  }

  console.log(`\nrecording written to ${OUT}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
