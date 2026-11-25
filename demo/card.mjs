/** Render a title card to PNG.
 *
 *  This ffmpeg build has no `drawtext` (no libfreetype), and Playwright is
 *  already a dependency for filming — so the card is a web page screenshotted
 *  at the film's own resolution. It also means the card uses the same fonts
 *  and colours as the Console, which a burned-in ffmpeg caption would not.
 */
import { chromium } from "playwright";

const [, , out, heading, sub] = process.argv;
const html = `<!doctype html><meta charset="utf-8"><style>
  html,body{margin:0;height:100%;background:#0b1220;display:grid;place-items:center;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}
  div{text-align:center}
  h1{color:#fff;font-size:46px;font-weight:600;margin:0 0 18px;letter-spacing:-.01em}
  p{color:#93a4bd;font-size:26px;margin:0;font-weight:400}
</style><div><h1>${heading}</h1><p>${sub}</p></div>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.setContent(html);
await page.screenshot({ path: out });
await browser.close();
