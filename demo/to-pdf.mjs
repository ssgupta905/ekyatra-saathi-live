/**
 * Print a document to PDF.
 *
 *     node to-pdf.mjs ../docs/src/solution-note.html ~/Downloads/Name.pdf
 *
 * Chrome's own print engine, which is the one the original notes were made
 * with — same page model, same font rendering, so a page written to look like
 * the earlier notes actually does.
 */
import { chromium } from "playwright";
import { mkdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { homedir } from "node:os";

const expand = (p) => (p.startsWith("~") ? resolve(homedir(), p.slice(2)) : resolve(p));
const source = expand(process.argv[2] ?? "");
const target = expand(process.argv[3] ?? "");

mkdirSync(dirname(target), { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`file://${source}`, { waitUntil: "networkidle" });
// Print rules, not screen rules: the stylesheet sets @page margins and the
// running footer, and emulating screen here would quietly discard both.
await page.emulateMedia({ media: "print" });
await page.pdf({
  path: target,
  format: "A4",
  printBackground: true,
  preferCSSPageSize: true,
});
await browser.close();

const { size } = statSync(target);
console.log(`${target}\n${(size / 1024).toFixed(0)} KB`);
