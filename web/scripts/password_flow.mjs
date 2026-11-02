/**
 * Email and password, through the real pages, with the mail server replaced.
 *
 *   BASE=http://127.0.0.1:3000 node scripts/password_flow.mjs
 *
 * Needs the API running as `tests.e2e_server`, which is what keeps the emails.
 * OUT, if set, is a folder for screenshots.
 */

import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
const OUT = process.env.OUT;
const PASSWORD = "correct horse battery";
const NEW_PASSWORD = "a different long password";

let failed = 0;
const check = (name, ok, extra = "") => {
  if (!ok) failed++;
  console.log(`${ok ? "ok  " : "FAIL"} ${name}${extra ? ` ${extra}` : ""}`);
};

const browser = await chromium.launch();

async function person(viewport = { width: 1440, height: 900 }) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  page.problems = [];
  page.on("pageerror", (e) => page.problems.push(e.message));
  return page;
}

const shot = async (page, name) => OUT && page.screenshot({ path: `${OUT}/${name}.png` });
const see = (page, text) => page.getByText(text).first().isVisible();
const email = (page) => page.getByLabel("Work email");
const password = (page) => page.getByLabel("Password", { exact: true });

async function latestLink(page, to, subject) {
  const mail = await (await page.request.get(`${BASE}/api/e2e/mail`)).json();
  const found = mail.filter((m) => m.to === to && m.subject.includes(subject)).at(-1);
  return found?.body.match(/http\S+/)?.[0];
}

/** The links in an email carry the server's public address, which here is this one. */
const local = (link) => new URL(link).pathname + new URL(link).search;

const amna = await person();

/* --- Signing up ------------------------------------------------------------ */

await amna.goto(`${BASE}/signup`);
await amna.waitForTimeout(1500);
await shot(amna, "pw_signup");
check("sign up offers Google", await amna.getByRole("link", { name: /continue with google/i }).isVisible());

await amna.getByLabel("Your name").fill("Amna Khan");
await email(amna).fill("amna@acme.com");
await password(amna).fill("short");
check("the meter says it is too short", (await amna.locator(".auth-meter").getAttribute("data-enough")) === "false");
await amna.getByRole("button", { name: "Create account" }).click();
await amna.waitForTimeout(500);
check("a short password is explained", await see(amna, /Use at least 10 characters/));
check("and nothing was sent", amna.url().includes("/signup"));

await password(amna).fill(PASSWORD);
check("the meter says when it is enough", (await amna.locator(".auth-meter").getAttribute("data-enough")) === "true");
check("the password is hidden", (await password(amna).getAttribute("type")) === "password");
await amna.getByRole("button", { name: "Show password" }).click();
check("and can be shown", (await password(amna).getAttribute("type")) === "text");
await amna.getByRole("button", { name: "Hide password" }).click();
await shot(amna, "pw_signup_filled");
await amna.getByRole("button", { name: "Create account" }).click();
await amna.waitForURL("**/console", { timeout: 20000 });
check("signing up lands in the product", amna.url().endsWith("/console"));
await amna.waitForTimeout(1200);
check("as a new team", await see(amna, /Amna's team/));
check("asked to confirm the address", await see(amna, /to invite teammates/));
await shot(amna, "pw_console_unconfirmed");

await amna.goto(`${BASE}/team`);
await amna.waitForTimeout(1000);
await amna.goto(`${BASE}/console`);

const verify = await latestLink(amna, "amna@acme.com", "Confirm");
check("a confirmation email was sent", !!verify);

await amna.getByRole("button", { name: "Send it again" }).click();
await amna.waitForTimeout(800);
check("it can be sent again", await see(amna, /Sent\. Check your inbox/));
const fresh = await latestLink(amna, "amna@acme.com", "Confirm");
check("with a new link", !!fresh && fresh !== verify);

await amna.goto(`${BASE}${local(fresh)}`);
await amna.waitForURL("**/console", { timeout: 15000 });
await amna.waitForTimeout(1000);
check("opening the link confirms it", !(await see(amna, /to invite teammates/)));

/* --- Logging out and back in ----------------------------------------------- */

await amna.getByRole("button", { name: "Sign out" }).click();
await amna.waitForURL("**/login**", { timeout: 15000 });
await amna.waitForTimeout(1200);

await email(amna).fill("amna@acme.com");
await password(amna).fill("not the right password");
await amna.getByRole("button", { name: "Log in", exact: true }).click();
await amna.waitForTimeout(1000);
check("a wrong password is explained", await see(amna, /do not match/));
check("and stays on the page", amna.url().includes("/login"));
await shot(amna, "pw_wrong");

await password(amna).fill(PASSWORD);
await amna.keyboard.press("Enter");
await amna.waitForURL("**/console", { timeout: 20000 });
check("the right password logs in, with the Enter key", true);

/* --- A second person with the same address --------------------------------- */

const stranger = await person();
await stranger.goto(`${BASE}/signup`);
await stranger.getByLabel("Your name").fill("Someone Else");
await email(stranger).fill("amna@acme.com");
await password(stranger).fill(PASSWORD);
await stranger.getByRole("button", { name: "Create account" }).click();
await stranger.waitForTimeout(1200);
check("an address cannot be taken twice", await see(stranger, /already an account/));

/* --- Where you were going -------------------------------------------------- */

const back = await person();
await back.goto(`${BASE}/login?next=/upload`);
await email(back).fill("amna@acme.com");
await password(back).fill(PASSWORD);
await back.keyboard.press("Enter");
await back.waitForURL("**/upload", { timeout: 20000 });
check("logging in returns to where you were going", back.url().endsWith("/upload"));

const evil = await person();
await evil.goto(`${BASE}/login?next=//evil.example`);
await email(evil).fill("amna@acme.com");
await password(evil).fill(PASSWORD);
await evil.keyboard.press("Enter");
await evil.waitForURL("**/console", { timeout: 20000 });
check("but never to another site", evil.url().startsWith(BASE));

/* --- Forgetting it --------------------------------------------------------- */

const forgot = await person();
await forgot.goto(`${BASE}/login`);
await forgot.waitForTimeout(1300);
await forgot.getByRole("button", { name: "Forgot password?" }).click();
await forgot.waitForTimeout(600);
check("forgot password has its own view", await see(forgot, "Reset your password"));
await shot(forgot, "pw_forgot");
await email(forgot).fill("amna@acme.com");
await forgot.getByRole("button", { name: "Email me a link" }).click();
await forgot.waitForTimeout(900);
check("it says a link is coming", await see(forgot, /a link is on its way/));
await shot(forgot, "pw_forgot_sent");
await forgot.getByRole("button", { name: /Back to log in/ }).click();
await forgot.waitForTimeout(500);
check("and can go back", await see(forgot, "Welcome back"));

const reset = await latestLink(forgot, "amna@acme.com", "Reset");
check("the email was sent", !!reset);
await forgot.goto(`${BASE}${local(reset)}`);
await forgot.waitForTimeout(1500);
check("the link opens the new password page", await see(forgot, "Choose a new password"));
check("with no tabs in the way", (await forgot.locator(".auth-tabs").count()) === 0);
await shot(forgot, "pw_reset");
await password(forgot).fill(NEW_PASSWORD);
await forgot.getByRole("button", { name: "Save new password" }).click();
await forgot.waitForURL("**/console", { timeout: 20000 });
check("choosing one signs you in", true);

await amna.reload();
await amna.waitForURL("**/login**", { timeout: 20000 });
check("and signs out every other browser", amna.url().includes("/login"));
await amna.waitForTimeout(1200);
await email(amna).fill("amna@acme.com");
await password(amna).fill(PASSWORD);
await amna.getByRole("button", { name: "Log in", exact: true }).click();
await amna.waitForTimeout(1000);
check("the old password no longer works", await see(amna, /do not match/));

await forgot.goto(`${BASE}${local(reset)}`);
await forgot.waitForTimeout(1200);
await password(forgot).fill("yet another long password");
await forgot.getByRole("button", { name: "Save new password" }).click();
await forgot.waitForTimeout(1000);
check("the link works only once", await see(forgot, /expired or was already used/));

const lost = await person();
await lost.goto(`${BASE}/reset-password`);
await lost.waitForTimeout(1000);
check("the page without a link explains itself", await see(lost, /needs the link from your email/));

/* --- Fits on one screen ---------------------------------------------------- */

for (const [name, viewport] of [
  ["laptop", { width: 1280, height: 720 }],
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
  ["small", { width: 360, height: 640 }],
]) {
  const page = await person(viewport);
  for (const route of ["login", "signup"]) {
    await page.goto(`${BASE}/${route}`);
    await page.waitForTimeout(1500);
    const m = await page.evaluate(() => {
      const se = document.scrollingElement;
      const card = document.querySelector(".auth-card").getBoundingClientRect();
      const chips = [...document.querySelectorAll(".auth-chip")].filter((c) => c.offsetParent !== null);
      const touching = chips.filter((c) => {
        const r = c.getBoundingClientRect();
        return !(r.right < card.left || r.left > card.right || r.bottom < card.top || r.top > card.bottom);
      }).length;
      return { over: se.scrollHeight - innerHeight, sideways: se.scrollWidth - innerWidth, touching };
    });
    const allowed = name === "small" ? Infinity : 0;
    check(`${name} ${route} fits`, m.over <= allowed && m.sideways <= 0 && m.touching === 0, JSON.stringify(m));
    await shot(page, `pw_${name}_${route}`);
  }
}

check("no page crashed", [amna, stranger, forgot, lost].every((p) => p.problems.length === 0));

await browser.close();
console.log(failed ? `\n${failed} FAILED` : "\nall passed");
process.exit(failed ? 1 : 0);
