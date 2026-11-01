/**
 * Go everywhere and press everything, then report what broke.
 *
 * Scripted tests only find what somebody thought to check. This starts from each
 * page, presses every safe control it can find, follows every internal link, and
 * records page errors, console errors, failed requests and 5xx answers, plus an
 * axe-core accessibility scan (the engine behind most accessibility audits) of each
 * distinct page, at desktop and phone width.
 *
 *   BASE=http://127.0.0.1:3000 node scripts/deep_crawl.mjs
 */

import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
const SEEDS = ["/console", "/calls", "/team", "/playbook", "/deals", "/dojo", "/report", "/upload", "/billing", "/archive", "/"];
/** Anything that leaves, spends, destroys or would take the crawler away for good. */
const DANGEROUS = /sign out|remove|delete|confirm|pay with|start the|generate|regenerate|end and|send|invite|cancel|restore/i;
const MAX_PAGES = Number(process.env.MAX_PAGES ?? 30);
const MAX_CLICKS = Number(process.env.MAX_CLICKS ?? 25);

const browser = await chromium.launch();
const findings = new Map();
const note = (kind, where, detail) => {
  const key = `${kind}: ${String(detail).slice(0, 160)}`;
  if (!findings.has(key)) findings.set(key, { kind, where, detail: String(detail).slice(0, 300), times: 0 });
  findings.get(key).times++;
};

const normalise = (url) => {
  const u = new URL(url);
  return u.pathname.replace(/\/(call|rep|play|deal)_[\w-]+/g, "/$1_ID").replace(/\/(reps|calls|playbook)\/[\w-]+/g, "/$1/ID");
};

async function crawl(viewport, label) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  let current = "";

  page.on("pageerror", (e) => note("page error", current, e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !/favicon|Failed to load resource/.test(m.text())) note("console error", current, m.text());
  });
  page.on("response", (r) => {
    if (r.status() >= 500 && r.url().startsWith(BASE) && !r.url().includes("/speech/tts") && !r.url().includes("/dojo/voice")) {
      note(`HTTP ${r.status()}`, current, new URL(r.url()).pathname);
    }
    if (r.status() === 404 && new URL(r.url()).pathname.startsWith("/_next/")) note("missing asset", current, r.url());
  });

  const queue = [...SEEDS];
  const seen = new Set();
  const scanned = new Set();
  let visited = 0;
  let clicks = 0;

  while (queue.length && visited < MAX_PAGES) {
    const path = queue.shift();
    const shape = normalise(BASE + path);
    if (seen.has(shape)) continue;
    seen.add(shape);
    visited++;
    current = `${label} ${path}`;

    try {
      await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 30000 });
    } catch (e) {
      note("navigation failed", current, e.message.split("\n")[0]);
      continue;
    }
    await page.waitForTimeout(1600);

    const body = await page.locator("body").innerText();
    if (/application error|something failed on our side/i.test(body)) note("error screen", current, body.slice(0, 200));
    if (/\b(undefined|NaN|\[object Object\])\b/.test(body)) {
      note("broken text on screen", current, (body.match(/.{0,50}\b(undefined|NaN|\[object Object\])\b.{0,30}/) ?? [""])[0]);
    }

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    if (overflow > 2) note("sideways scroll", current, `${overflow}px wider than the window`);

    if (!scanned.has(shape)) {
      scanned.add(shape);
      try {
        const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).disableRules(["color-contrast"]).analyze();
        for (const v of results.violations) {
          note(`a11y ${v.impact}`, current, `${v.id}: ${v.help} (${v.nodes[0]?.target?.join(" ")})`);
        }
      } catch (e) {
        note("axe failed", current, e.message.split("\n")[0]);
      }
    }

    const links = await page.$$eval("a[href]", (as) => as.map((a) => a.getAttribute("href")));
    for (const href of links) {
      if (href?.startsWith("/") && !href.startsWith("/api") && !href.startsWith("/audio")) queue.push(href.split("#")[0]);
    }

    // Press what is safe to press, and see whether the page survives it.
    const buttons = page.locator("main button:visible, main [role=tab]:visible, main summary:visible");
    const count = Math.min(await buttons.count(), MAX_CLICKS);
    for (let i = 0; i < count; i++) {
      const button = buttons.nth(i);
      let name = "";
      try {
        name = ((await button.innerText({ timeout: 800 })) || (await button.getAttribute("aria-label")) || "").trim();
        if (DANGEROUS.test(name) || (await button.isDisabled())) continue;
        const before = page.url();
        await button.click({ timeout: 1500 });
        clicks++;
        await page.waitForTimeout(120);
        const after = await page.locator("body").innerText();
        if (/application error/i.test(after)) note("click crashed the page", current, name);
        if (page.url() !== before) {
          await page.goto(before, { waitUntil: "domcontentloaded" });
          await page.waitForTimeout(500);
        }
        await page.keyboard.press("Escape").catch(() => {});
      } catch {
        /* covered, animating, or gone after a re-render: a crawler is not a judge of that */
      }
    }
  }

  await ctx.close();
  console.log(`  ${label}: ${visited} pages, ${clicks} controls pressed`);
}

await crawl({ width: 1280, height: 860 }, "desktop");
await crawl({ width: 390, height: 780 }, "phone");
await browser.close();

const rows = [...findings.values()].sort((a, b) => a.kind.localeCompare(b.kind));
for (const f of rows) console.log(`  [${f.kind}] x${f.times} ${f.where}: ${f.detail}`);
console.log(rows.length ? `\n${rows.length} distinct finding(s)` : "\nno findings");
process.exit(0);
