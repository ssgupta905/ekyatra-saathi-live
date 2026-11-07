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

/**
 * Fill in the demo sign-in, which the source deliberately does not contain.
 *
 * The submission documents have to print a working password so an evaluation
 * panel can open the control centre. The repository is public, so the source
 * holds a placeholder and the real value arrives from the environment at
 * render time. Without it the PDF says so in the page rather than silently
 * shipping the placeholder, which is the failure that would not be noticed.
 */
const secret = process.env.SAATHI_DEMO_PASSWORD;
await page.evaluate((value) => {
  const token = "__DEMO_ADMIN_PASSWORD__";
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const hits = [];
  while (walker.nextNode()) {
    if (walker.currentNode.nodeValue.includes(token)) hits.push(walker.currentNode);
  }
  for (const node of hits) {
    node.nodeValue = node.nodeValue.replaceAll(token, value ?? "[set SAATHI_DEMO_PASSWORD]");
  }
  return hits.length;
}, secret);
if (!secret) {
  console.warn("  SAATHI_DEMO_PASSWORD is not set — the demo sign-in is blank in this PDF");
}
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
