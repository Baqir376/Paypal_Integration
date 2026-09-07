/**
 * The landing page pins itself to dark. This checks it puts the user's
 * preference back when they navigate away -- otherwise visiting the home page
 * would silently darken the whole app for a light-mode user.
 */
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
const browser = await chromium.launch();
const ctx = await browser.newContext({ colorScheme: "light", viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

const attr = () => page.evaluate(() => document.documentElement.getAttribute("data-theme"));
const bg = () =>
  page.evaluate(() => getComputedStyle(document.body).backgroundColor);

const checks = [];
const check = (name, pass, detail) => {
  checks.push(pass);
  console.log(`${pass ? "ok  " : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
};

// 1. Cold load of the landing in a light-preference browser.
await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.waitForTimeout(700);
check("landing is dark on cold load", (await attr()) === "dark", await bg());

// 2. Client-side navigation away restores the preference.
await page.click('a[href="/console"]');
await page.waitForURL("**/console");
await page.waitForTimeout(900);
check("console follows light preference after leaving landing", (await attr()) === null, await bg());

// 3. Explicit light choice survives a round trip through the landing.
await page.evaluate(() => localStorage.setItem("salix-theme", "light"));
await page.goto(BASE + "/", { waitUntil: "networkidle" });
await page.waitForTimeout(600);
check("landing still dark with an explicit light preference stored", (await attr()) === "dark");

await page.click('a[href="/console"]');
await page.waitForURL("**/console");
await page.waitForTimeout(800);
check("explicit light preference is restored", (await attr()) === "light");

// 4. A dark-preference user is unaffected either way.
await page.evaluate(() => localStorage.setItem("salix-theme", "dark"));
await page.goto(BASE + "/console", { waitUntil: "networkidle" });
await page.waitForTimeout(600);
check("explicit dark preference honoured in the app", (await attr()) === "dark");

await browser.close();
const failed = checks.filter((c) => !c).length;
console.log(failed ? `\n${failed} failing` : "\nall theme checks passed");
process.exit(failed ? 1 : 0);
