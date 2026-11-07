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

/**
 * Substitute the same late values `to-pdf.mjs` does, before measuring.
 *
 * Without this the check measures `__DEMO_VIDEO_LINK__` — nineteen characters
 * standing in for a hundred and three — and reports a link fits when the
 * printed page will have it running off the edge. A fit check that tests
 * different content from the renderer is worse than none, because it is
 * believed.
 */
await p.evaluate((pairs) => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    for (const [token, value] of Object.entries(pairs)) {
      if (value && node.nodeValue.includes(token)) {
        node.nodeValue = node.nodeValue.replaceAll(token, value);
      }
    }
  }
}, {
  __DEMO_ADMIN_PASSWORD__: process.env.SAATHI_DEMO_PASSWORD,
  __DEMO_VIDEO_LINK__: process.env.SAATHI_DEMO_VIDEO,
});

/**
 * Any URL that wrapped or ran past its column.
 *
 * A URL broken across two lines cannot be typed from a printout or
 * double-clicked to copy, and it reads as a typo. `getClientRects()` returns
 * one box per line a span occupies, so more than one means it wrapped — which
 * is a thing you can measure, unlike "does this look right".
 */
const urls = await p.evaluate(() => {
  //: Measured against the printable area of the page, not against the
  //: element's own parent. A centred block shrinks to fit its widest line, so
  //: a URL inside one always "ends exactly at its parent's edge" — which read
  //: as an overflow on a link that in fact had ninety pixels to spare.
  return [...document.querySelectorAll(".url")]
    .map((el) => {
      const page = el.closest(".page, .slide");
      const pad = getComputedStyle(page);
      const area = page.getBoundingClientRect();
      const right = area.right - parseFloat(pad.paddingRight);
      const box = el.getBoundingClientRect();
      return {
        text: el.textContent.trim().slice(0, 52),
        lines: el.getClientRects().length,
        over: Math.round(box.right - right),
      };
    })
    .filter((u) => u.lines > 1 || u.over > 0);
});

const report = await p.evaluate(() => {
  const mm = 1280 / 338.7;
  const out = [];
  document.querySelectorAll(".page, .slide").forEach((page, i) => {
    const over = page.scrollHeight - page.clientHeight;
    out.push({ what: `page ${i + 1}`, over: Math.round(over / mm) });
    page.querySelectorAll(".box").forEach((box) => {
      const title = box.querySelector("h2")?.textContent ?? "?";
      //: A flex box reports a millimetre over even when the page itself fits
      //: and nothing is clipped — border and sub-pixel rounding. Anything
      //: genuinely cut off runs to several millimetres, and the page total
      //: catches it anyway, so one millimetre is not worth reporting.
      const spill = Math.round((box.scrollHeight - box.clientHeight) / mm);
      out.push({ what: `  ${title}`, over: spill <= 1 ? 0 : spill });
    });
  });
  return out;
});
await b.close();

let bad = urls.length;
for (const u of urls) {
  console.log(
    u.lines > 1
      ? `WRAP        ${u.lines} lines  ${u.text}`
      : `OVERFLOW  ${String(u.over).padStart(4)}px  ${u.text}`,
  );
}
for (const row of report) {
  const fits = row.over <= 0;
  if (!fits) bad += 1;
  console.log(`${fits ? "fits  " : "OVER  "} ${String(row.over).padStart(4)}mm  ${row.what}`);
}
console.log(bad ? `\n${bad} problem(s)` : "\neverything fits, no URL wraps");
process.exit(bad ? 1 : 0);
