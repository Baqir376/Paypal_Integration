/**
 * Report every failing network request per page.
 *
 * A console error tells you something broke; this tells you what asked for it,
 * which is the part that lets you fix it.
 */

import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
const PAGES = [
  "/",
  "/console",
  "/calls",
  "/calls/call_halcyon_1",
  "/reps/rep_bilal",
  "/playbook",
  "/deals",
  "/dojo",
  "/report",
  "/upload",
];

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1560, height: 1000 },
  colorScheme: "dark",
});
const page = await context.newPage();

const failures = [];
page.on("response", (r) => {
  if (r.status() >= 400) failures.push(`${r.status()}  ${r.request().method()}  ${r.url()}`);
});
page.on("pageerror", (e) => failures.push(`PAGEERROR  ${String(e).slice(0, 160)}`));

for (const path of PAGES) {
  const before = failures.length;
  await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(1800);
  const added = failures.slice(before);
  console.log(`${added.length ? "FAIL" : "ok  "}  ${path}`);
  for (const f of added) console.log(`        ${f}`);
}

await browser.close();
console.log(failures.length ? `\n${failures.length} failing request(s)` : "\nno failing requests");
