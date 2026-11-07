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
/**
 * Which edit to build. `SAATHI_FILM` names a plan beside this file, so a second
 * cut of the same footage is a new plan rather than a fork of the pipeline.
 *   plan        the 12-minute end-to-end film
 *   walkthrough the submission walkthrough: team, approach, partners, product
 */
const PLAN_FILE = `./${process.env.SAATHI_FILM ?? "plan"}.mjs`;
const { PLAN, CANVAS } = await import(PLAN_FILE);

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, "build", process.env.SAATHI_FILM ?? "plan", "art");

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

/** The team, as a grid of name / role / contribution. */
function peopleHtml({ heading, sub, people }) {
  return `<style>${BASE}
    body { width: ${CANVAS.w}px; height: ${CANVAS.h}px; padding: 92px 120px;
           display: flex; flex-direction: column; justify-content: center; }
    h1 { font-size: 62px; font-weight: 700; letter-spacing: -0.03em; }
    .sub { font-size: 26px; color: #2563eb; font-weight: 600; letter-spacing: 0.04em;
           text-transform: uppercase; margin-top: 10px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 26px 48px; margin-top: 52px; }
    .who { border-left: 3px solid #2563eb; padding-left: 22px; }
    .name { font-size: 31px; font-weight: 600; letter-spacing: -0.02em; }
    .role { font-size: 21px; color: #7f8ea3; margin-top: 3px; }
    .did { font-size: 21px; color: #cbd5e1; margin-top: 10px; line-height: 1.45; }
  </style>
  <h1>${heading}</h1><div class="sub">${sub}</div>
  <div class="grid">${people.map(([n, r, d]) =>
    `<div class="who"><div class="name">${n}</div><div class="role">${r}</div>
     <div class="did">${d}</div></div>`).join("")}</div>`;
}

/** What we thought, and what we built instead. */
function turnHtml({ heading, before, after, note }) {
  return `<style>${BASE}
    body { width: ${CANVAS.w}px; height: ${CANVAS.h}px; padding: 100px 120px;
           display: flex; flex-direction: column; justify-content: center; }
    h1 { font-size: 62px; font-weight: 700; letter-spacing: -0.03em; }
    .row { display: flex; align-items: center; gap: 56px; margin-top: 64px; }
    .box { flex: 1; padding: 40px 36px; border-radius: 16px; font-size: 33px;
           line-height: 1.3; white-space: pre-line; }
    .was { background: #141d2e; color: #64748b; text-decoration: line-through;
           text-decoration-color: #475569; }
    .is { background: #2563eb; color: #fff; font-weight: 600; }
    .arrow { font-size: 54px; color: #2563eb; }
    .note { margin-top: 56px; font-size: 24px; color: #94a3b8; line-height: 1.5;
            max-width: 1360px; }
  </style>
  <h1>${heading}</h1>
  <div class="row"><div class="box was">${before}</div><div class="arrow">→</div>
    <div class="box is">${after}</div></div>
  <div class="note">${note}</div>`;
}

/** A labelled list: partners, or results. */
function stackHtml({ heading, rows }) {
  return `<style>${BASE}
    body { width: ${CANVAS.w}px; height: ${CANVAS.h}px; padding: 96px 120px;
           display: flex; flex-direction: column; justify-content: center; }
    h1 { font-size: 62px; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 52px; }
    .row { display: grid; grid-template-columns: 330px 1fr; gap: 40px; padding: 24px 0;
           border-top: 1px solid #1e293b; align-items: baseline; }
    .k { font-size: 34px; font-weight: 700; color: #2563eb; letter-spacing: -0.02em; }
    .v { font-size: 24px; color: #cbd5e1; line-height: 1.45; }
  </style>
  <h1>${heading}</h1>
  ${rows.map(([k, v]) => `<div class="row"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}`;
}

/**
 * Where Saathi sits.
 *
 * The single most misread thing about this product is that it looks like a
 * hospital system. It is not one, and it does not want to be: it reads status
 * out of whatever the hospital already runs, decides, and tells people. This
 * diagram exists to say that before anybody sees a screen.
 */
function archHtml({ heading, sub, above, core, below }) {
  const chip = (c) => `<div class="chip"><b>${c[0]}</b><span>${c[1]}</span></div>`;
  return `<style>${BASE}
    body { width: ${CANVAS.w}px; height: ${CANVAS.h}px; padding: 70px 110px;
           display: flex; flex-direction: column; justify-content: center; }
    h1 { font-size: 54px; font-weight: 700; letter-spacing: -0.03em; }
    .sub { font-size: 23px; color: #7f8ea3; margin-top: 8px; }
    .band { font-size: 15px; letter-spacing: 0.16em; text-transform: uppercase;
            color: #64748b; margin: 32px 0 14px; }
    .row { display: flex; gap: 18px; }
    .chip { flex: 1; background: #141d2e; border: 1px solid #223049; border-radius: 13px;
            padding: 17px 19px; }
    .chip b { display: block; font-size: 23px; font-weight: 600; }
    .chip span { display: block; font-size: 17px; color: #8a97ab; margin-top: 5px;
                 line-height: 1.35; }
    .flow { display: flex; justify-content: center; gap: 190px; color: #2563eb;
            font-size: 26px; margin: 12px 0; letter-spacing: 0.3em; }
    .core { border: 2px solid #2563eb; background: #11203f; border-radius: 17px;
            padding: 24px 30px; }
    .core .t { font-size: 31px; font-weight: 700; }
    .core .d { font-size: 19px; color: #9fb4d4; margin-top: 7px; }
    .core .steps { display: flex; gap: 12px; margin-top: 16px; flex-wrap: wrap; }
        .core .steps span { background: #0d1b36; border: 1px solid #2d4a7a;
            border-radius: 99px; padding: 7px 15px; font-size: 17px; color: #cfe0ff; }
  </style>
  <h1>${heading}</h1><div class="sub">${sub}</div>
  <div class="band">What the hospital already runs</div>
  <div class="row">${above.map(chip).join("")}</div>
  <div class="flow">↓ ↓ ↓</div>
  <div class="core"><div class="t">${core.title}</div><div class="d">${core.detail}</div>
    <div class="steps">${core.steps.map((s) => `<span>${s}</span>`).join("")}</div></div>
  <div class="flow">↓ ↓ ↓</div>
  <div class="row">${below.map(chip).join("")}</div>`;
}

const LAYOUT = { people: peopleHtml, turn: turnHtml, stack: stackHtml, arch: archHtml };

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ deviceScaleFactor: 1 });
const page = await context.newPage();

let made = 0;
for (const seg of PLAN) {
  if (LAYOUT[seg.kind]) {
    await page.setViewportSize({ width: CANVAS.w, height: CANVAS.h });
    await page.setContent(LAYOUT[seg.kind](seg.card));
    await page.screenshot({ path: resolve(OUT, `${seg.id}.png`) });
    made += 1;
  } else if (seg.kind === "card") {
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
