/**
 * Does the mouse wheel actually scroll whatever it is over?
 *
 * Smooth-scroll libraries listen for wheel on the window and drive the document,
 * so a scrollable box inside the page can look frozen. That only shows up with a
 * real wheel event in a real browser, which is what this sends.
 *
 *   BASE=http://127.0.0.1:3000 node scripts/scroll_check.mjs
 */

import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
let failed = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
  if (!ok) failed++;
};

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 620 } })).newPage();
const open = async (path) => {
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
  // Past the loader and page transition, and long enough for Lenis to start.
  await page.waitForTimeout(2200);
};

/** Wheel over `selector`, and report whether it and the page moved. */
async function wheelOver(selector) {
  const box = page.locator(selector).first();
  await box.waitFor({ timeout: 8000 });
  await box.scrollIntoViewIfNeeded();
  await page.waitForTimeout(250);
  const rect = await box.boundingBox();
  const viewport = page.viewportSize();
  const top = Math.max(rect.y, 0);
  const bottom = Math.min(rect.y + rect.height, viewport.height);
  await page.mouse.move(rect.x + rect.width / 2, (top + bottom) / 2);
  const before = await box.evaluate((el) => [el.scrollTop, el.scrollHeight, el.clientHeight, window.scrollY]);
  for (let i = 0; i < 4; i++) {
    await page.mouse.wheel(0, 120);
    await page.waitForTimeout(120);
  }
  await page.waitForTimeout(700);
  const after = await box.evaluate((el) => [el.scrollTop, window.scrollY]);
  return {
    scrollable: before[1] > before[2] + 2,
    moved: after[0] - before[0],
    pageMoved: after[1] - before[3],
    sh: before[1],
    ch: before[2],
  };
}

// The page itself.
await open("/calls");
{
  const before = await page.evaluate(() => window.scrollY);
  await page.mouse.move(800, 400);
  for (let i = 0; i < 4; i++) {
    await page.mouse.wheel(0, 200);
    await page.waitForTimeout(100);
  }
  await page.waitForTimeout(900);
  const after = await page.evaluate(() => window.scrollY);
  const room = await page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
  if (room > 10) check("the page scrolls", after > before, `moved ${after - before}`);
  else console.log("  --    the page has nothing to scroll");
}

// The command palette: a modal over the page, where the wheel must not leak.
await open("/console");
await page.keyboard.press("Control+k");
await page.waitForTimeout(500);
const panels = await page.evaluate(() =>
  [...document.querySelectorAll('[role="dialog"] *, [role="dialog"]')]
    .filter((el) => {
      const s = getComputedStyle(el);
      return /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 2;
    })
    .map((el) => {
      el.setAttribute("data-scroll-probe", "1");
      return `${el.tagName}.${String(el.className).slice(0, 40)} ${el.scrollHeight}/${el.clientHeight}`;
    }),
);
console.log("  scrollable inside the palette:", panels.join(" | ") || "none");
if (panels.length) {
  const r = await wheelOver('[data-scroll-probe="1"]');
  check("the open palette scrolls", r.moved > 0, `moved ${r.moved}`);
  check("the page behind the palette stays still", r.pageMoved === 0, `page moved ${r.pageMoved}`);
} else {
  check("the palette has content to scroll in a short window", false, "none found");
}
await page.keyboard.press("Escape");

// Every other box the app makes scrollable, found rather than listed.
for (const path of ["/console", "/calls", "/playbook", "/deals", "/dojo", "/report", "/team", "/billing", "/upload"]) {
  await open(path);
  const found = await page.evaluate(() => {
    let n = 0;
    return [...document.querySelectorAll("main *, aside, aside *")]
      .filter((el) => {
        const s = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return (
          /(auto|scroll)/.test(s.overflowY) &&
          el.scrollHeight > el.clientHeight + 4 &&
          r.height > 30 &&
          r.top < innerHeight - 40 &&
          r.top >= 0
        );
      })
      .map((el) => {
        const id = `probe-${n++}`;
        el.setAttribute("data-probe", id);
        return id;
      });
  });
  for (const id of found) {
    const r = await wheelOver(`[data-probe="${id}"]`);
    check(`${path} inner box ${id}`, r.moved > 0, `moved ${r.moved}, ${r.sh}/${r.ch}`);
  }
  if (!found.length) console.log(`  --    ${path}: no inner scroll boxes on screen`);
}

// A short window must still reach everything in the sidebar.
await open("/console");
const rail = await page.evaluate(() => {
  const el = document.querySelector(".app-rail");
  const s = getComputedStyle(el);
  const foot = document.querySelector(".app-rail-foot").getBoundingClientRect();
  return { overflowY: s.overflowY, sh: el.scrollHeight, ch: el.clientHeight, footBottom: Math.round(foot.bottom), vh: innerHeight };
});
console.log("  sidebar:", JSON.stringify(rail));
check(
  "the bottom of the sidebar is reachable in a short window",
  rail.footBottom <= rail.vh || /auto|scroll/.test(rail.overflowY),
);

await browser.close();
console.log(failed ? `\n${failed} FAILED` : "\nall passed");
process.exit(failed ? 1 : 0);
