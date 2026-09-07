/**
 * Drive every page at data designed to break it, and report what broke.
 *
 * The pipeline lets each stage fail on its own, which is the right design and
 * means the interface has to render every partial combination those failures
 * produce: a transcript with no analysis, a scorecard with no transcript, a
 * call that failed at stage one and carries nothing at all. The API is
 * perfectly happy to return null for any of it. The crash happens afterwards,
 * in a component that assumed a field was there, in front of whoever is
 * watching.
 *
 *   cd api && .venv/Scripts/python -m scripts.hostile_data
 *   cd web && node scripts/crash_hunt.mjs
 *   cd api && .venv/Scripts/python -m scripts.hostile_data --clean
 *
 * A page counts as broken if it throws, logs an error, renders Next's
 * "Application error" boundary, or comes back effectively blank. Anything
 * else -- an empty state, a "not found", a message explaining what is missing
 * -- is the interface doing its job.
 */

import { chromium } from "playwright";

const BASE = process.env.SALIX_CHECK_URL ?? "http://127.0.0.1:3000";

const HOSTILE = [
  ["hostile_failed", "failed at transcription, no artefacts at all"],
  ["hostile_running", "still transcribing, reached by a bookmark"],
  ["hostile_nometrics", "transcript only, analysis failed"],
  ["hostile_notranscript", "metrics with no transcript to cite into"],
  ["hostile_empty", "one zero-length segment, no words"],
  ["hostile_badcites", "citations naming segments that do not exist"],
  ["hostile_nasty", "markup, emoji, a 900-character token, mixed script"],
  ["hostile_extremes", "a twenty-four hour call, 100% talk ratio, zero pace"],
];

const STATIC = [
  ["/", "index"],
  ["/console", "command centre"],
  ["/calls", "every call"],
  ["/deals", "deals at risk"],
  ["/playbook", "the playbook"],
  ["/report", "cycle report"],
  ["/upload", "ingest"],
  ["/dojo", "the dojo"],
  ["/archive", "provenance"],
  ["/calls/does-not-exist", "a call id that was never real"],
  ["/reps/does-not-exist", "a rep id that was never real"],
  ["/playbook/does-not-exist", "a play id that was never real"],
];

const results = [];

const browser = await chromium.launch();
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();

async function visit(path, label) {
  const thrown = [];
  const logged = [];
  const onError = (e) => thrown.push(String(e).split("\n")[0].slice(0, 120));
  const onConsole = (m) => {
    if (m.type() !== "error") return;
    const text = m.text();
    // Next prefetches links and aborts the ones still in flight on navigation.
    if (/_rsc=|ERR_ABORTED/.test(text)) return;
    // A 404 for a record that genuinely does not exist is the API answering
    // correctly. The browser logs it either way; what matters is whether the
    // page then rendered a "not found" or fell over, and the checks below
    // already decide that.
    if (/status of 40[34]/.test(text)) return;
    logged.push(text.slice(0, 120));
  };

  page.on("pageerror", onError);
  page.on("console", onConsole);

  let status = "?";
  let body = "";
  try {
    const response = await page.goto(BASE + path, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    status = response?.status() ?? "?";
    // Long enough for the client fetch to land and the component to render it.
    await page.waitForTimeout(3000);
    body = await page.evaluate(() => document.body.innerText);
  } catch (e) {
    thrown.push("navigation: " + String(e.message ?? e).slice(0, 100));
  }

  page.off("pageerror", onError);
  page.off("console", onConsole);

  const boundary = /Application error|client-side exception/i.test(body);
  // A deliberate empty or not-found state is short and says so. Only silence
  // counts as blank.
  const explained = /not found|no calls|0 calls|nothing yet|cannot load|analyse a call/i.test(body);
  const blank = body.trim().length < 120 || (body.trim().length < 300 && !explained);
  const broken = thrown.length > 0 || logged.length > 0 || boundary || blank;

  results.push({ path, label, status, broken, thrown, logged, boundary, blank, chars: body.trim().length });

  const mark = broken ? "\x1b[31mBROKEN\x1b[0m" : "\x1b[32m  ok  \x1b[0m";
  const why = boundary ? "error boundary"
    : blank ? `blank (${body.trim().length} chars)`
    : thrown[0] ?? logged[0] ?? `${body.trim().length} chars`;
  console.log(`  ${mark} ${path.padEnd(34)} ${why}`);
}

console.log("\n  --- every page, normal data ---");
for (const [path, label] of STATIC) await visit(path, label);

console.log("\n  --- calls built to break the renderer ---");
for (const [id, label] of HOSTILE) await visit(`/calls/${id}`, label);

const broken = results.filter((r) => r.broken);
console.log("\n  " + "=".repeat(68));
console.log(`  ${results.length - broken.length}/${results.length} pages survived`);

if (broken.length) {
  console.log("\n  what broke:\n");
  for (const r of broken) {
    console.log(`  ${r.path}  —  ${r.label}`);
    for (const t of r.thrown) console.log(`      threw:   ${t}`);
    for (const l of r.logged) console.log(`      logged:  ${l}`);
    if (r.boundary) console.log("      rendered Next's error boundary");
    if (r.blank) console.log(`      rendered ${r.chars} characters`);
    console.log();
  }
}

await browser.close();
process.exit(broken.length ? 1 : 0);
