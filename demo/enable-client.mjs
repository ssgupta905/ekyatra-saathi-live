/** Enable the registered API client through OpenEMR's own admin screen.
 *
 *  Not by UPDATE against its database. This is a privileged change to a
 *  hospital system: done the way an administrator does it, OpenEMR writes its
 *  own audit trail and the result is visible on the screen they already use.
 *
 *  The `isEnabled` checkbox on this page is a read-only indicator, not a
 *  control — ticking it and submitting saves a different form entirely (ask
 *  me how I know). The actual action is a link, "Enable Client", carrying its
 *  own CSRF token.
 */
import { chromium } from "playwright";

const EMR = process.env.EMR;
if (!EMR || !process.env.CLIENT_ID || !process.env.PASS) {
  console.error("\n  EMR, CLIENT_ID and PASS are all required.\n"
    + "  Enabling an API client is a privileged change to a hospital system;\n"
    + "  there is deliberately no default host to run it against.\n");
  process.exit(1);
}
const CLIENT = process.env.CLIENT_ID;
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto(`${EMR}/interface/login/login.php?site=default`, { waitUntil: "domcontentloaded", timeout: 60000 });
await p.fill("#authUser", "admin");
await p.fill("#clearPass", process.env.PASS);
await p.click("#login-button");
await p.waitForTimeout(14000);

await p.goto(`${EMR}/interface/smart/admin-client.php`, { waitUntil: "domcontentloaded", timeout: 60000 });
await p.waitForTimeout(2500);
await p.locator(`tr:has-text("${CLIENT}") a:has-text("Edit")`).first().click();
await p.waitForTimeout(4000);

await p.locator('a:has-text("Enable Client")').first().click();
await p.waitForTimeout(6000);

await p.goto(`${EMR}/interface/smart/admin-client.php`, { waitUntil: "domcontentloaded", timeout: 60000 });
await p.waitForTimeout(2500);
const row = ((await p.locator(`tr:has-text("${CLIENT}")`).first().textContent()) || "").replace(/\s+/g, " ").trim();
console.log("  row now:", row.slice(0, 120));
console.log(/\bEnabled\b/.test(row) && !/\bDisabled\b/.test(row) ? "  ENABLED" : "  still not enabled");
await b.close();
