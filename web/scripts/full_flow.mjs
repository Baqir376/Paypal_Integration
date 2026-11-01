/**
 * The whole product, in one browser, as two companies.
 *
 *   sign in -> paywall -> buy credits on PayPal -> upload -> deal score -> plan ->
 *   closing test -> invite a colleague -> a rival company sees none of it
 *
 * Against api/tests/e2e_server.py:
 *   python -m uvicorn tests.e2e_server:app --port 8010
 *   SALIX_API_URL=http://127.0.0.1:8010 npx next start
 *   node scripts/full_flow.mjs
 */

import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
let failed = 0;
const problems = [];
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${name}${!ok && detail ? `  (${String(detail).slice(0, 300)})` : ""}`);
  if (!ok) failed++;
};

const browser = await chromium.launch();

function person(label) {
  return browser.newContext({ viewport: { width: 1280, height: 900 } }).then(async (ctx) => {
    const page = await ctx.newPage();
    page.on("pageerror", (e) => problems.push(`${label}: ${String(e).slice(0, 200)}`));
    page.on("response", (r) => {
      if (r.status() >= 500) {
        r.text()
          .catch(() => "(no body)")
          .then((body) => problems.push(`${label}: ${r.status()} ${r.url()} ${body.slice(0, 200)}`));
      }
    });
    return page;
  });
}

const textOf = (page) => page.locator("body").innerText();
async function see(page, pattern, timeout = 12000) {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    if (pattern.test(await textOf(page))) return true;
    await page.waitForTimeout(150);
  }
  return false;
}

async function signIn(page, who) {
  await page.getByRole("link", { name: /continue with google/i }).click();
  await page.waitForURL("**/api/e2e/google**");
  await page.getByRole("link", { name: who }).click();
}

const mp3 = { name: "bilal.mp3", mimeType: "audio/mpeg", buffer: Buffer.alloc(4096, 7) };

/* --- Signed out ----------------------------------------------------------- */

const amna = await person("amna");

await amna.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
check("the marketing page is public", !amna.url().includes("/login"));

for (const path of ["/console", "/calls", "/team", "/billing", "/upload", "/reps/rep_x"]) {
  await amna.goto(`${BASE}${path}`);
  await amna.waitForURL("**/login**", { timeout: 15000 }).catch(() => {});
  // The shell and a refused request can each redirect. Let the second one land too.
  await amna.waitForLoadState("networkidle").catch(() => {});
  await amna.waitForTimeout(400);
  check(`${path} sends a stranger to sign in`, amna.url().includes("/login"), amna.url());
}
await amna.goto(`${BASE}/archive`);
await amna.waitForURL("**/login**", { timeout: 15000 }).catch(() => {});
check("/archive sends a stranger to sign in", amna.url().includes("/login"), amna.url());

const probe = await amna.request.get(`${BASE}/api/calls`);
check("the API refuses a stranger", probe.status() === 401, probe.status());
const posted = await amna.request.post(`${BASE}/api/billing/reconcile`);
check("a signed-out POST is a 401, not an outage", posted.status() === 401, posted.status());
const upload = await amna.request.post(`${BASE}/api/calls/upload`, {
  multipart: { salesperson: "X", file: { name: "a.mp3", mimeType: "audio/mpeg", buffer: Buffer.alloc(64, 7) } },
});
check("so is a signed-out upload", upload.status() === 401, upload.status());
const audio = await amna.request.get(`${BASE}/audio/call_nothing.mp3`);
check("recordings refuse a stranger", audio.status() === 404, audio.status());

/* --- Cancelling, then signing in ------------------------------------------- */

await amna.goto(`${BASE}/login?next=/upload`);
await amna.getByRole("link", { name: /continue with google/i }).click();
await amna.waitForURL("**/api/e2e/google**");
await amna.getByRole("link", { name: "Cancel" }).click();
await amna.waitForURL("**/login?error=cancelled**");
check("cancelling at Google is explained", await see(amna, /cancelled/i));

await amna.goto(`${BASE}/login?next=/upload`);
await signIn(amna, "Amna Khan");
await amna.waitForURL("**/upload", { timeout: 20000 });
check("signing in returns to where you were going", amna.url().endsWith("/upload"));
check("the rail shows who is signed in", await see(amna, /Amna Khan/) && (await see(amna, /Amna's team/)));

const cookies = await amna.context().cookies();
const session = cookies.find((c) => c.name === "salix_session");
check("the session cookie is HttpOnly", session?.httpOnly === true);
check("the session cookie is SameSite=Lax", session?.sameSite === "Lax");
check("scripts cannot read the session", !(await amna.evaluate(() => document.cookie)).includes("salix_session"));

/* --- The paywall ------------------------------------------------------------ */

check("a new team starts with no credits", await see(amna, /out of credits/i));
await amna.setInputFiles('input[type="file"]', mp3);
await amna.getByPlaceholder("Bilal's Call").fill("Bilal's Call");
check(
  "the analysis cannot start with no credits",
  !(await amna.getByRole("button", { name: /start the analysis/i }).isEnabled()),
);

await amna.getByRole("link", { name: /buy credits/i }).click();
await amna.waitForURL("**/billing");
check("simulated payments are called out", await see(amna, /Simulated payments/));

await amna.getByRole("button", { name: /simulated paypal checkout/i }).first().click();
await amna.waitForURL("**/api/paypal-simulator?**", { timeout: 15000 });
check("the checkout page says it is not PayPal", await see(amna, /This is not PayPal/));
await amna.getByRole("link", { name: /cancel and return/i }).click();
await amna.waitForURL("**/billing?cancelled=1");
check("cancelling at PayPal is acknowledged", await see(amna, /nothing was charged/i));
check("cancelling grants nothing", await see(amna, /0\s*credits left/i));

await amna.getByRole("button", { name: /simulated paypal checkout/i }).first().click();
await amna.waitForURL("**/api/paypal-simulator?**", { timeout: 15000 });
await amna.getByRole("link", { name: /approve simulated payment/i }).click();
await amna.waitForURL("**/billing/return**");
check("paying adds the credits", await see(amna, /5\s*credits added/i), await textOf(amna));

const returned = amna.url();
await amna.goto(returned);
check("reloading the return page does not add them again", await see(amna, /You now have\s*5\s*credits/i));

/* --- Upload to plan ---------------------------------------------------------- */

await amna.getByRole("link", { name: /analyse a call/i }).first().click();
await amna.waitForURL("**/upload");
check("the balance is on the upload page", await see(amna, /5\s*credits left/i));
await amna.setInputFiles('input[type="file"]', mp3);
await amna.getByPlaceholder("Bilal's Call").fill("Bilal's Call");
await amna.getByRole("button", { name: /start the analysis/i }).click();
await amna.getByText(/Analysis complete|Finished, with gaps/).waitFor({ timeout: 60000 });
let text = await textOf(amna);
check("the analysis finished", /Analysis complete/.test(text), text.slice(0, 300));
check("the language was detected", /English detected/.test(text));
check("the deal was scored", /deal score/i.test(text));

await amna.getByRole("button", { name: /open the call/i }).click();
await amna.waitForURL("**/calls/**");
const callUrl = amna.url();
check("the call shows its deal score", await see(amna, /Deal score/));
await amna.getByRole("link", { name: /^coaching plan$/i }).click();
await amna.waitForURL("**/reps/**");
const repUrl = amna.url();
check("the plan is there with nothing clicked", await see(amna, /Test me on this plan/));

await amna.goto(`${BASE}/billing`);
check("one credit was used", await see(amna, /4\s*credits left/i));
check("the history says where they went", await see(amna, /Bought on PayPal/) && (await see(amna, /Recording analysed/)));

/* --- The closing test --------------------------------------------------------- */

await amna.goto(repUrl);
await amna.getByRole("link", { name: /test me on this plan/i }).click();
await amna.waitForURL("**/dojo**");
check("the closing test says what it is", await see(amna, /Can you close it now/));
await amna.getByRole("button", { name: /start the session/i }).click();
const box = amna.locator("textarea, input[type=text]").last();
await box.waitFor({ timeout: 15000 });

const lines = [
  "What does this problem cost you each quarter, and who decides on fixing it?",
  "A customer like you cut that in half. What would you need to see from us?",
  "On price, what are you comparing us with today, and what would make it worth it?",
  "Can we book a pilot review next Tuesday at ten with your finance lead?",
];
for (const line of lines) {
  await box.fill(line);
  await box.press("Enter");
  await amna.waitForTimeout(1200);
}
check("the buyer agreed when asked", await see(amna, /Yes, that works for me/));
await amna.getByRole("button", { name: /^(end|finish|score)/i }).first().click();
check("the verdict is shown", await see(amna, /You closed it|Closed, with gaps/, 20000), (await textOf(amna)).slice(-400));
check("it quotes the buyer's agreement", await see(amna, /Yes, that works for me/));

await amna.goto(repUrl);
check("the result stays on the rep's page", await see(amna, /Last closing test/));

/* --- A second company ------------------------------------------------------------ */

const bilal = await person("bilal");
await bilal.goto(`${BASE}/login`);
await signIn(bilal, "Bilal Shah");
await bilal.waitForURL("**/console", { timeout: 20000 });
check("a second company gets its own team", await see(bilal, /Bilal's team/));
await bilal.goto(`${BASE}/calls`);
await bilal.waitForTimeout(1200);
check("it sees none of the first company's calls", !/Bilal's Call/.test(await textOf(bilal)));

const stolen = await bilal.request.get(`${BASE}/api/calls/${callUrl.split("/").pop()}`);
check("it cannot open the call by id", stolen.status() === 404, stolen.status());
const stolenRep = await bilal.request.get(`${BASE}/api/reps/${repUrl.split("/").pop()}`);
check("it cannot open the rep by id", stolenRep.status() === 404, stolenRep.status());
const stolenAudio = await bilal.request.get(`${BASE}/audio/${callUrl.split("/").pop()}.mp3`);
check("it cannot download the recording", stolenAudio.status() === 404, stolenAudio.status());
const ownAudio = await amna.request.get(`${BASE}/audio/${callUrl.split("/").pop()}.mp3`);
check("the owner can", ownAudio.status() === 200, ownAudio.status());

/* --- A colleague ------------------------------------------------------------------ */

await amna.goto(`${BASE}/team`);
await amna.getByLabel("Colleague's email").fill("sana@acme.com");
await amna.getByRole("button", { name: "Invite" }).click();
check("an invite is listed", await see(amna, /sana@acme\.com/) && (await see(amna, /invited/i)));

const sana = await person("sana");
await sana.goto(`${BASE}/login`);
await signIn(sana, "Sana Malik");
await sana.waitForURL("**/console", { timeout: 20000 });
check("an invited colleague joins the team", await see(sana, /Amna's team/));
await sana.goto(`${BASE}/calls`);
check("and sees its calls", await see(sana, /Bilal's Call/));
await sana.goto(`${BASE}/team`);
await see(sana, /Who can sign in/);
check("but cannot manage access", (await sana.getByRole("button", { name: "Invite" }).count()) === 0);

await amna.goto(`${BASE}/team`);
await amna.getByRole("button", { name: /remove access/i }).click();
await see(amna, /Who can sign in/);
await amna.waitForTimeout(600);
await sana.goto(`${BASE}/calls`);
await sana.waitForURL("**/login**", { timeout: 15000 }).catch(() => {});
check("removing access ends their session", sana.url().includes("/login"), sana.url());

/* --- Signing out -------------------------------------------------------------------- */

await amna.goto(`${BASE}/console`);
await amna.getByRole("button", { name: /sign out/i }).click();
await amna.waitForURL("**/login**", { timeout: 15000 });
check("signing out lands on the login page", true);
await amna.goto(`${BASE}/calls`);
await amna.waitForURL("**/login**", { timeout: 15000 }).catch(() => {});
check("and the session is really over", amna.url().includes("/login"), amna.url());

check("nothing threw and nothing answered 5xx", problems.length === 0, problems.join(" | "));

await browser.close();
console.log(failed ? `\n${failed} FAILED` : "\nall passed");
process.exit(failed ? 1 : 0);
