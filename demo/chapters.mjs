/**
 * Find the act boundaries in a recording.
 *
 *     node chapters.mjs <file> [step seconds]
 *
 * The demo puts a near-black full-screen card up between acts. Every other
 * frame is dominated by two bright screens, so the share of bright pixels is a
 * clean discriminator: a title card is a frame where almost nothing is light.
 * Sampling that in a canvas costs nothing and gives real timestamps, rather
 * than numbers derived from adding up the script's own waits.
 */
import { chromium } from "playwright";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const file = resolve(process.argv[2] ?? "");
const step = Number(process.argv[3] ?? 1);
const b64 = readFileSync(file).toString("base64");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 640, height: 360 } });
await page.setContent(
  `<body style="margin:0"><video id="v" muted src="data:video/mp4;base64,${b64}"></video>
   <canvas id="c" width="320" height="180"></canvas></body>`,
);
await page.waitForFunction(() => {
  const v = document.getElementById("v");
  return v && v.readyState >= 2 && Number.isFinite(v.duration);
}, null, { timeout: 120000 });

const marks = await page.evaluate(async (stepSeconds) => {
  const v = document.getElementById("v");
  const c = document.getElementById("c");
  const ctx = c.getContext("2d", { willReadFrequently: true });
  const seek = (t) => new Promise((done) => { v.onseeked = done; v.currentTime = t; });

  const rows = [];
  for (let t = 0; t < v.duration; t += stepSeconds) {
    await seek(t);
    ctx.drawImage(v, 0, 0, c.width, c.height);
    const { data } = ctx.getImageData(0, 0, c.width, c.height);
    let bright = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] > 200 && data[i + 1] > 200 && data[i + 2] > 200) bright += 1;
    }
    rows.push({ t, bright: bright / (c.width * c.height) });
  }
  return { rows, duration: v.duration };
}, step);

// A card is a run of dark frames; report where each run starts.
const CARD = 0.04;
const starts = [];
let inCard = false;
for (const { t, bright } of marks.rows) {
  if (bright < CARD && !inCard) { starts.push(t); inCard = true; }
  else if (bright >= CARD) inCard = false;
}

console.log(`${marks.duration.toFixed(1)}s · ${starts.length} cards\n`);
const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, "0")}`;
for (const t of starts) console.log(`  ${mmss(t)}  (${t.toFixed(0)}s)`);
await browser.close();
