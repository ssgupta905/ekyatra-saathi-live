/**
 * The still art: title cards, chapter cards, and the side panels that sit
 * beside a phone.
 *
 * Rendered in a browser rather than drawn by ffmpeg, because this ffmpeg has
 * no drawtext filter and because the cards should look like the product —
 * same ink, same accent, same typeface as the control centre.
 */

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { PLAN, CANVAS } from "./plan.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "build/art");

const FONT =
  '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif';

const BASE = `
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: ${FONT}; background: #0b1220; color: #f8fafc;
         -webkit-font-smoothing: antialiased; }
  .mark { width: 54px; height: 54px; border-radius: 15px; background: #2563eb;
          display: grid; place-items: center; font-size: 30px; font-weight: 700;
          letter-spacing: -0.02em; }
  .rule { height: 3px; width: 72px; background: #2563eb; border-radius: 2px; }
`;

/** A full-frame card: either a chapter marker or a statement. */
function cardHtml({ chapter, heading, sub, kicker }) {
  const body = chapter
    ? `<div class="num">${chapter}</div><h1 class="chapter">${heading}</h1>`
    : `<div class="mark">S</div>
       <h1>${heading}</h1>
       ${sub ? `<p class="sub">${sub}</p>` : ""}
       <div class="rule"></div>
       ${kicker ? `<p class="kicker">${kicker}</p>` : ""}`;
  return `<style>${BASE}
    body { display: grid; place-items: center; height: ${CANVAS.h}px; width: ${CANVAS.w}px; }
    .wrap { display: flex; flex-direction: column; gap: 26px; align-items: flex-start;
            max-width: 1180px; }
    h1 { font-size: 86px; font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; }
    .sub { font-size: 38px; color: #cbd5e1; font-weight: 400; letter-spacing: -0.01em; }
    .kicker { font-size: 24px; color: #7f8ea3; line-height: 1.5; max-width: 980px; }
    .num { font-size: 22px; color: #2563eb; font-weight: 700; letter-spacing: 0.22em; }
    h1.chapter { font-size: 76px; }
  </style><div class="wrap">${body}</div>`;
}

/** The panel that sits to the right of a phone. */
function panelHtml({ heading, lines }) {
  return `<style>${BASE}
    body { width: 900px; height: ${CANVAS.h}px; display: flex; align-items: center;
           padding: 0 0 0 20px; background: transparent; }
    .wrap { display: flex; flex-direction: column; gap: 30px; align-items: flex-start; }
    h2 { font-size: 52px; font-weight: 700; letter-spacing: -0.03em; line-height: 1.08; }
    ul { list-style: none; display: flex; flex-direction: column; gap: 20px; }
    li { font-size: 31px; color: #cbd5e1; display: flex; gap: 18px; align-items: baseline;
         line-height: 1.3; }
    li::before { content: ""; width: 9px; height: 9px; border-radius: 99px;
                 background: #2563eb; flex: none; transform: translateY(-6px); }
  </style><div class="wrap">
    <div class="rule"></div>
    <h2>${heading}</h2>
    <ul>${lines.map((l) => `<li>${l}</li>`).join("")}</ul>
  </div>`;
}

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ deviceScaleFactor: 1 });
const page = await context.newPage();

let made = 0;
for (const seg of PLAN) {
  if (seg.kind === "card") {
    await page.setViewportSize({ width: CANVAS.w, height: CANVAS.h });
    await page.setContent(cardHtml(seg.card));
    await page.screenshot({ path: resolve(OUT, `${seg.id}.png`) });
    made += 1;
  } else if (seg.panel) {
    await page.setViewportSize({ width: 900, height: CANVAS.h });
    await page.setContent(panelHtml(seg.panel));
    await page.screenshot({ path: resolve(OUT, `${seg.id}.png`), omitBackground: true });
    made += 1;
  }
}
await browser.close();
console.log(`${made} stills in ${OUT}`);
