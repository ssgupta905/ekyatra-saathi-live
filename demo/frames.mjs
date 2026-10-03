/**
 * Pull frames out of a recording, so a run can be checked rather than assumed.
 *
 *     node frames.mjs ../recordings/<file>.webm [count]
 *
 * There is no ffmpeg on this machine and Playwright's bundled copy is a
 * minimal webm-only build, so this plays the file in a real browser, seeks to
 * evenly spaced timestamps and screenshots each one. Slower than ffmpeg and it
 * needs nothing installed.
 */
import { chromium } from "playwright";
import { mkdirSync, readFileSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";

const file = resolve(process.argv[2] ?? "");
const count = Number(process.argv[3] ?? 12);
const out = resolve(dirname(file), "frames");
mkdirSync(out, { recursive: true });

const b64 = readFileSync(file).toString("base64");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.setContent(
  `<body style="margin:0;background:#000">
     <video id="v" style="width:100vw;height:100vh;object-fit:contain"
            src="data:video/webm;base64,${b64}"></video></body>`,
);
const v = page.locator("#v");
await page.waitForFunction(() => {
  const el = document.getElementById("v");
  return el && el.readyState >= 2 && Number.isFinite(el.duration);
}, null, { timeout: 60000 });

const duration = await page.evaluate(() => document.getElementById("v").duration);
console.log(`${basename(file)} — ${duration.toFixed(1)}s`);

for (let i = 0; i < count; i += 1) {
  const t = (duration * (i + 0.5)) / count;
  await page.evaluate((time) => {
    const el = document.getElementById("v");
    return new Promise((done) => {
      el.onseeked = done;
      el.currentTime = time;
    });
  }, t);
  await page.waitForTimeout(140);
  const name = `${String(i + 1).padStart(2, "0")}-at-${t.toFixed(0)}s.png`;
  await v.screenshot({ path: resolve(out, name) });
  console.log(`  ${name}`);
}
await browser.close();
console.log(`\n${count} frames in ${out}`);
