/**
 * Does every box on the brief actually fit inside its page?
 *
 * The page is 338.7mm x 190.5mm, which at 96dpi is exactly 1280x720 — so the
 * check renders at that size and compares each box's scrollHeight against the
 * height it was given. Eyeballing a PDF for overflow is how a page that was
 * 38mm over got called "fits" once already.
 */
import { chromium } from "playwright";
import { resolve } from "node:path";

const file = resolve(process.argv[2]);
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
await p.goto(`file://${file}`, { waitUntil: "networkidle" });
await p.emulateMedia({ media: "print" });

const report = await p.evaluate(() => {
  const mm = 1280 / 338.7;
  const out = [];
  document.querySelectorAll(".page, .slide").forEach((page, i) => {
    const over = page.scrollHeight - page.clientHeight;
    out.push({ what: `page ${i + 1}`, over: Math.round(over / mm) });
    page.querySelectorAll(".box").forEach((box) => {
      const title = box.querySelector("h2")?.textContent ?? "?";
      out.push({
        what: `  ${title}`,
        over: Math.round((box.scrollHeight - box.clientHeight) / mm),
      });
    });
  });
  return out;
});
await b.close();

let bad = 0;
for (const row of report) {
  const fits = row.over <= 0;
  if (!fits) bad += 1;
  console.log(`${fits ? "fits  " : "OVER  "} ${String(row.over).padStart(4)}mm  ${row.what}`);
}
console.log(bad ? `\n${bad} overflowing` : "\neverything fits");
process.exit(bad ? 1 : 0);
