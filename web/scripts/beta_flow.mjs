/**
 * What a new customer does on their first day, against an empty database.
 *
 *   SALIX_DATABASE_URL=<empty> SALIX_PROVIDER_MODE=mock uvicorn salix.app:app --port 8010
 *   SALIX_API_URL=http://127.0.0.1:8010 npx next start
 *   node scripts/beta_flow.mjs
 *
 * Set EXPECT_PAYWALL=1 with SALIX_BILLING_MODE=on to check the paywall instead.
 */

import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
const PAYWALL = process.env.EXPECT_PAYWALL === "1";

let failed = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${name}${!ok && detail ? `  (${detail})` : ""}`);
  if (!ok) failed++;
}

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));

const open = async (path) => {
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(250);
};
const body = () => page.locator("body").innerText();
/** Pages animate in, so give the text a moment to arrive before calling it absent. */
const see = async (pattern, timeout = 10000) => {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    if (pattern.test(await body())) return true;
    await page.waitForTimeout(150);
  }
  return false;
};
const shot = async (name) => {
  if (process.env.SHOTS) await page.screenshot({ path: `${process.env.SHOTS}/${name}.png` });
};
const mp3 = { name: "bilal.mp3", mimeType: "audio/mpeg", buffer: Buffer.alloc(4096, 7) };

if (PAYWALL) {
  await open("/upload");
  check("the balance is shown", /out of credits/i.test(await body()));
  await page.setInputFiles('input[type="file"]', mp3);
  await page.getByPlaceholder("Bilal's Call").fill("Bilal's Call");
  check(
    "no credits means no analysis",
    !(await page.getByRole("button", { name: /start the analysis/i }).isEnabled()),
  );
  await page.getByRole("link", { name: /buy credits/i }).click();
  await page.waitForURL("**/billing");
  check("the packs are on offer", await see(/USD 10\.00/));
  check("it says PayPal is not configured", await see(/PayPal is not configured/));
  check("the rail shows the balance", await see(/Credits\s*0/));
  await shot("billing");
  await open("/billing?cancelled=1");
  check("a cancelled checkout is acknowledged", /nothing was charged/i.test(await body()));
  await open("/billing/return");
  check("the return page without an order charges nothing", /nothing was charged/i.test(await body()));
  await open("/billing/return?token=NOTOURS");
  check("an order we did not make is refused", /No order NOTOURS/.test(await body()));
} else {
  for (const path of ["/console", "/calls", "/team", "/playbook", "/deals", "/report", "/dojo", "/billing", "/upload"]) {
    await open(path);
    check(`${path} survives an empty team`, !/application error|unreachable/i.test(await body()));
  }

  await open("/team");
  check("the empty team says what to do", await see(/Nobody yet/));
  await page.getByLabel("New salesperson's name").fill("Zara Sheikh");
  await page.getByRole("button", { name: /add salesperson/i }).click();
  await page.getByRole("link", { name: "Zara Sheikh" }).waitFor();
  check("a salesperson can be added", true);

  await page.getByLabel("New salesperson's name").fill("zara sheikh");
  await page.getByRole("button", { name: /add salesperson/i }).click();
  check("a duplicate is refused with the reason", await see(/already on the team/));

  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Name for Zara Sheikh").fill("Zara Khan");
  await page.getByRole("button", { name: "Save" }).click();
  await page.getByRole("link", { name: "Zara Khan" }).waitFor();
  check("a salesperson can be renamed", true);

  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await page.getByRole("button", { name: /confirm remove/i }).click();
  await page.getByRole("button", { name: "Restore" }).waitFor();
  check("removal moves them to Removed", /Nobody yet/.test(await body()));
  await page.getByRole("button", { name: "Restore" }).click();
  await page.getByRole("link", { name: "Zara Khan" }).waitFor();
  check("a removed salesperson can be restored", true);

  await open("/upload");
  check("there is no language dropdown", (await page.locator('select[name="language"]').count()) === 0);
  await page.setInputFiles('input[type="file"]', mp3);
  const start = page.getByRole("button", { name: /start the analysis/i });
  check("a file alone is not enough", !(await start.isEnabled()));
  await page.getByPlaceholder("Bilal's Call").fill("Bilal's Call");
  check("a new name is called out", /added to your team/.test(await body()));
  check("a file and a name are enough", await start.isEnabled());
  await shot("upload");
  await start.click();

  await page.getByText(/Analysis complete|Finished, with gaps/).waitFor({ timeout: 60000 });
  const text = await body();
  check("it finished cleanly", /Analysis complete/.test(text), text.slice(0, 200));
  check("the language was detected", /English detected/.test(text));
  check("the plan stage ran", /Writing the coaching plan/.test(text));

  await page.getByRole("link", { name: /see the coaching plan/i }).click();
  await page.waitForURL("**/reps/**");
  check("the rep was created from the name", await see(/Rank \d+ of the team/i) && (await see(/Bilal/)));
  check("a coaching plan is waiting, with nothing clicked", await see(/drill/i), (await body()).slice(0, 300));
  await shot("rep");

  await open("/calls");
  check("the call is listed", /Bilal's Call/.test(await body()));
  await page.getByRole("link", { name: /Bilal's Call/ }).first().click();
  await page.waitForURL("**/calls/**");
  check("the call page names the language", await see(/English/));
  await shot("call");

  await open("/console");
  check("the console works with real data", /Bilal/.test(await body()));
}

check("no page threw", errors.length === 0, errors.join(" | "));
await browser.close();
console.log(failed ? `\n${failed} FAILED` : "\nall passed");
process.exit(failed ? 1 : 0);
