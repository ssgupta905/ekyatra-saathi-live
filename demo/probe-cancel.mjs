import { chromium } from "playwright";
const EMR = "http://8.231.81.219:8300";
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto(`${EMR}/interface/login/login.php?site=default`, { waitUntil: "domcontentloaded", timeout: 90000 });
await p.fill("#authUser","admin"); await p.fill("#clearPass", process.env.PASS); await p.click("#login-button");
await p.waitForTimeout(14000);
await p.goto(`${EMR}/interface/main/calendar/index.php?module=PostCalendar&func=view&tplview=&viewtype=day&Date=${process.env.DAY}`,
  { waitUntil: "domcontentloaded", timeout: 90000 });
await p.waitForTimeout(4000);
await p.getByText("Lakra,Josephine").first().click({ timeout: 20000 }).catch(e => console.log("  click failed:", e.message.slice(0,60)));
await p.waitForTimeout(6000);
console.log("  url after click:", p.url().slice(0, 120));
const status = await p.locator('[name="form_apptstatus"]').count();
console.log("  form_apptstatus present:", status > 0);
if (status) {
  const opts = await p.locator('[name="form_apptstatus"] option').evaluateAll(
    els => els.map(e => `${e.value}=${(e.textContent||"").trim()}`).slice(0, 8));
  console.log("  statuses:", opts.join(" | "));
}
await b.close();
