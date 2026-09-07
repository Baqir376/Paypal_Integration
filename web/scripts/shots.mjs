/**
 * Screenshot every surface so the design can actually be looked at.
 *
 * Building a UI without ever seeing it rendered is how you end up asserting
 * it looks good. This script exists so that claim is checkable.
 *
 *   node scripts/shots.mjs [outDir] [theme] [width]
 */

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const OUT = process.argv[2] ?? "shots";
const THEME = process.argv[3] ?? "dark";
const WIDTH = Number(process.argv[4] ?? 1560);
const BASE = process.env.BASE ?? "http://127.0.0.1:3000";

const PAGES = [
  ["landing", "/", 2600],
  ["console", "/console", 1700],
  ["call", "/calls/call_halcyon_1", 2600],
  ["rep", "/reps/rep_bilal", 1700],
  ["playbook", "/playbook", 1500],
  ["deals", "/deals", 1500],
  ["dojo", "/dojo", 1500],
  ["report", "/report", 1500],
  ["upload", "/upload", 1200],
  ["calls", "/calls", 1500],
];

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: WIDTH, height: WIDTH < 700 ? 900 : 1000 },
  deviceScaleFactor: 1,
  colorScheme: THEME === "light" ? "light" : "dark",
});

const page = await context.newPage();
const problems = [];
page.on("console", (m) => {
  if (m.type() === "error") problems.push(m.text().slice(0, 200));
});
page.on("pageerror", (e) => problems.push(`PAGEERROR ${String(e).slice(0, 200)}`));

for (const [name, path, settle] of PAGES) {
  try {
    await page.goto(BASE + path, { waitUntil: "domcontentloaded", timeout: 45000 });
    // Every loading view is built from `.skeleton` blocks, so their absence is
    // the signal that the route resolved. `networkidle` is a guess about the
    // network and never settles on a page holding a stream open.
    await page
      .waitForFunction(() => document.querySelectorAll(".skeleton").length === 0, null, { timeout: 20000 })
      .catch(() => console.log(`  warn ${name}: still loading`));
    // The WebGL first frame and entrance transitions need a beat to land.
    await page.waitForTimeout(settle);
    await page.screenshot({ path: `${OUT}/${THEME}-${WIDTH}-${name}.png` });
    console.log(`  ok   ${THEME}-${WIDTH}-${name}`);
  } catch (e) {
    console.log(`  FAIL ${name}: ${String(e).split("\n")[0]}`);
  }
}

await browser.close();

if (problems.length) {
  console.log("\nconsole errors:");
  for (const p of [...new Set(problems)].slice(0, 12)) console.log("  -", p);
} else {
  console.log("\nno console errors");
}
