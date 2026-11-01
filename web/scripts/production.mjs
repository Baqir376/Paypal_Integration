/**
 * Is this safe to put in front of people?
 *
 * Run against the PRODUCTION build with a key configured:
 *
 *   cd web && npm run build
 *   SALIX_API_KEY=<key> SALIX_API_URL=http://127.0.0.1:8010 npx next start
 *   SALIX_API_KEY=<key> node scripts/production.mjs
 *
 * It must be the production build. Dev mode hides the three things this exists
 * to catch: a key leaking into a client bundle, a route that only works
 * because of dev's forgiving proxy, and a hydration mismatch that dev logs as
 * a warning and production renders wrongly.
 *
 * Two halves. First that everything works -- every page, both languages, both
 * voices, the streaming turn. Then that everything fails well: the value of an
 * error screen is entirely in whether its instruction is true, and a screen
 * that confidently tells an operator to restart a healthy API is worse than no
 * screen at all.
 */
import { chromium } from "playwright";

const BASE = process.env.SALIX_CHECK_URL ?? "http://127.0.0.1:3000";
const KEY = process.env.SALIX_API_KEY ?? "";

const results = [];
const pass = (n, d = "") => results.push({ ok: true, n, d });
const fail = (n, d) => results.push({ ok: false, n, d });

const browser = await chromium.launch();
// ignoreHTTPSErrors so the same check runs against a local Caddy using its
// internal CA, not only against a publicly trusted certificate.
const context = await browser.newContext({ permissions: [], ignoreHTTPSErrors: true });
const page = await context.newPage();

const consoleErrors = [];
const failedRequests = [];
const keyLeaks = [];

page.on("console", (m) => {
  if (m.type() === "error") consoleErrors.push(`${page.url().replace(BASE,"")}: ${m.text().slice(0, 200)}`);
});
page.on("pageerror", (e) => consoleErrors.push(`PAGEERROR ${page.url().replace(BASE,"")}: ${String(e).slice(0,200)}`));
page.on("requestfailed", (r) => {
  const u = r.url();
  if (!u.startsWith(BASE)) return;
  // Next prefetches every visible link and aborts the ones still in flight
  // when navigation happens. Those are cancellations, not failures.
  if (u.includes("_rsc=") && r.failure()?.errorText === "net::ERR_ABORTED") return;
  failedRequests.push(`${r.method()} ${u.replace(BASE,"")} — ${r.failure()?.errorText}`);
});
// Every byte the browser is ever sent, checked for the secret.
page.on("response", async (r) => {
  if (!KEY || !r.url().startsWith(BASE)) return;
  const ct = r.headers()["content-type"] ?? "";
  if (!/text|json|javascript/.test(ct)) return;
  try {
    const body = await r.text();
    if (body.includes(KEY)) keyLeaks.push(r.url().replace(BASE, ""));
  } catch { /* streamed or already consumed */ }
});

// Also: does any request the browser makes carry the key outward?
page.on("request", (r) => {
  if (!KEY) return;
  const h = JSON.stringify(r.headers());
  if (h.includes(KEY) || r.url().includes(KEY)) keyLeaks.push(`REQUEST ${r.url().replace(BASE,"")}`);
});

// ---------------------------------------------------------------- pages
const PAGES = ["/", "/console", "/calls", "/team", "/billing", "/deals", "/playbook", "/report", "/upload", "/dojo", "/archive"];
for (const path of PAGES) {
  try {
    const r = await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 45000 });
    const status = r?.status();
    const text = await page.evaluate(() => document.body.innerText);
    if (status !== 200) fail(`page ${path}`, `status ${status}`);
    else if (text.trim().length < 60) fail(`page ${path}`, `rendered ${text.trim().length} chars — blank?`);
    else if (/Cannot reach the Salix API|requires a key|unauthorized/i.test(text))
      fail(`page ${path}`, `error surface: ${text.match(/.{0,90}(Cannot reach|requires a key|unauthorized).{0,60}/i)?.[0]}`);
    else pass(`page ${path}`, `${text.trim().length} chars`);
  } catch (e) {
    fail(`page ${path}`, String(e).slice(0, 160));
  }
}

// ------------------------------------------------------- data actually arrived
await page.goto(BASE + "/console", { waitUntil: "networkidle" });
const consoleText = await page.evaluate(() => document.body.innerText);
// Not "Meridian" -- that is the demo corpus. The console must render the
// organisation it actually has, whatever it is called.
if (/·\s*\w/.test(consoleText) && /calls, listened to properly/i.test(consoleText))
  pass("console renders the organisation it has");
else fail("console renders the organisation it has", consoleText.slice(0, 200));

// --------------------------------------------------- Roman Urdu round trip
//
// The product offers two languages and no more: English, and Roman Urdu --
// Urdu vocabulary in Latin letters, which is what a Pakistani floor actually
// types. What matters is not that a reply arrives but that it arrives in the
// right SCRIPT: a model handed Latin-script Urdu answers in Nastaliq unless
// told not to, and that is unreadable to the rep who just typed the question.

const NASTALIQ = /[\u0600-\u06FF]/;

async function dojoTurn(language, text, difficulty) {
  return page.evaluate(async (args) => {
    // Whoever is on the roster. Hard-coding "rep_zara" tied the check to the
    // demo corpus, so it broke the moment somebody started from a blank
    // database with their own team -- which is exactly when you most want the
    // check to still work.
    const reps = await fetch("/api/reps").then((r) => r.json());
    const repId = reps[0]?.rep?.id;
    if (!repId) return { status: 0, len: 0, opening: "", said: "", note: "no reps" };

    const start = await fetch("/api/dojo/start", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rep_id: repId, difficulty: args.difficulty, language: args.language,
      }),
    }).then((r) => r.json());

    const res = await fetch("/api/dojo/turn", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: start.session, text: args.text }),
    });
    const body = await res.text();
    // Reassemble the streamed deltas into what the buyer actually said.
    const said = body
      .split("\n")
      .filter((l) => l.startsWith("data:"))
      .map((l) => { try { return JSON.parse(l.slice(5)).text ?? ""; } catch { return ""; } })
      .join("");
    return { status: res.status, len: body.length, opening: start.opening, said };
  }, { language, text, difficulty });
}

await page.goto(BASE + "/dojo", { waitUntil: "networkidle" });

const roman = await dojoTurn(
  "ur-roman", "Aap ki price bohat zyada hai, hamare paas itna budget nahi hai.", 3,
);

if (roman.status === 200 && roman.len > 50) pass("Roman Urdu turn streams", `${roman.len} bytes`);
else fail("Roman Urdu turn streams", JSON.stringify(roman).slice(0, 200));

if (roman.opening && !NASTALIQ.test(roman.opening)) pass("the opening greets in Roman Urdu", roman.opening.slice(0, 44) + "…");
else fail("the opening greets in Roman Urdu", String(roman.opening).slice(0, 90));

if (roman.said && !NASTALIQ.test(roman.said)) pass("the buyer answers in Roman Urdu", roman.said.slice(0, 52) + "…");
else if (!roman.said) fail("the buyer answers in Roman Urdu", "no text in the stream");
else fail("the buyer answers in Roman Urdu", "Nastaliq in the reply: " + roman.said.slice(0, 60));

const english = await dojoTurn("en", "Your price is far too high.", 2);
if (english.status === 200 && english.said && !NASTALIQ.test(english.said))
  pass("the English session stays English", english.said.slice(0, 46) + "…");
else fail("the English session stays English", JSON.stringify(english).slice(0, 180));

// --------------------------------------------------------- Roman Urdu spoken
const tts = await page.evaluate(async () => {
  const r = await fetch("/speech/tts?text=" + encodeURIComponent("Aap ka waqt dene ka shukriya.") + "&lang=en");
  const b = await r.blob();
  return { status: r.status, type: b.type, size: b.size, voice: r.headers.get("x-salix-voice") };
});
if (tts.status === 200 && tts.size > 2000) pass("Roman Urdu spoken aloud", `${tts.size}B ${tts.voice}`);
else fail("Roman Urdu spoken aloud", JSON.stringify(tts));

// ------------------------------------------------------------ English TTS
const ttsEn = await page.evaluate(async () => {
  const r = await fetch("/speech/tts?text=" + encodeURIComponent("Thanks for making the time today.") + "&lang=en");
  const b = await r.blob();
  return { status: r.status, size: b.size, voice: r.headers.get("x-salix-voice") };
});
if (ttsEn.status === 200 && ttsEn.size > 2000) pass("English neural voice", `${ttsEn.size}B ${ttsEn.voice}`);
else fail("English neural voice", JSON.stringify(ttsEn));

// ----------------------------------------------------- the cookie was minted
const cookies = await context.cookies();
const salix = cookies.find((c) => c.name === "salix_client");
if (salix?.httpOnly) pass("rate-limit cookie is httpOnly", salix.value.slice(0, 8) + "…");
else fail("rate-limit cookie is httpOnly", JSON.stringify(salix ?? null));

const readable = await page.evaluate(() => document.cookie.includes("salix_client"));
if (!readable) pass("page cannot read the client cookie");
else fail("page cannot read the client cookie", "document.cookie exposes it");

// ---------------------------------------------------------------------------
// Recordings
//
// The most confidential thing in the system, and for a long time the only
// thing served with no credential at all -- /audio is not under /api, so the
// key never applied to it. Anyone holding a filename could fetch somebody's
// sales call.
// ---------------------------------------------------------------------------

const recording = await page.evaluate(async () => {
  const calls = await fetch("/api/calls?limit=40").then((r) => r.json());
  const named = calls.find((c) => c.audio_url);
  const name = named?.audio_url?.split("/").pop()?.split("?")[0] ?? null;
  // Only fetch a file that exists. Probing a made-up name would log a 404 to
  // the console, and this same run asserts the console is clean.
  const viaApp = name ? (await fetch(`/audio/${name}`)).status : null;
  return { name: name ?? "call_probe.mp3", viaApp };
});

// Straight at the API, the way somebody who found the filename would try it.
// Only meaningful when the API is reachable from here at all.
const apiOrigin = process.env.SALIX_API_URL;
if (apiOrigin) {
  let direct = null;
  try {
    direct = (await fetch(`${apiOrigin}/audio/${recording.name}`)).status;
  } catch { /* not reachable from here, which is itself fine */ }
  if (direct === null) pass("API not reachable except through the app");
  else if (direct === 401 || direct === 403) pass("a bare filename does not fetch a recording");
  else fail("a bare filename does not fetch a recording", `got ${direct} with no credential`);
} else {
  pass("recordings reachable through the app", `/audio -> ${recording.viaApp}`);
}

if (recording.viaApp === null) pass("no stored recording to play", "seed corpus carries no audio");
else if ([200, 206].includes(recording.viaApp)) pass("the app can still play audio", `${recording.viaApp}`);
else fail("the app can still play audio", `got ${recording.viaApp} through the proxy`);

// ---------------------------------------------------------------------------
// What a rep sees when something goes wrong
//
// These are the three failures a live floor actually hits, and the thing that
// matters is not that they are handled but that each one says something true.
// A blank screen is the worst outcome; a confident wrong instruction is the
// second worst.
// ---------------------------------------------------------------------------

async function underFailure(label, status, body, expect) {
  const p = await context.newPage();
  const crashes = [];
  p.on("pageerror", (e) => crashes.push(String(e).slice(0, 120)));
  await p.route("**/api/**", (r) =>
    r.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }));
  await p.goto(BASE + "/console", { waitUntil: "networkidle" });
  const text = (await p.evaluate(() => document.body.innerText)).replace(/\s+/g, " ");
  await p.close();

  if (crashes.length) fail(label, `uncaught: ${crashes[0]}`);
  else if (text.trim().length < 80) fail(label, "blank screen");
  else if (!expect.test(text)) fail(label, `wrong advice: ${text.slice(0, 160)}`);
  else pass(label);
}

await underFailure(
  "API down says so, and how to start it", 502,
  { error: "api_unreachable", detail: "Cannot reach the Salix API. Is the backend running?", retryable: true },
  /uvicorn|start the api/i);

await underFailure(
  "key mismatch is diagnosed as a key mismatch", 401,
  { error: "unauthorized", detail: "This API requires a key. Send it as X-API-Key." },
  /SALIX_API_KEY.*same|running, but it rejected/i);

await underFailure(
  "rate limit reads as temporary, not broken", 429,
  { error: "rate_limited", detail: "Too many requests to this endpoint. Try again in 42s.", retryable: true },
  /try again|slow down/i);

// --------------------------------------------------------------- verdict
console.log("\n" + "=".repeat(72));
for (const r of results) console.log(`  ${r.ok ? "PASS" : "FAIL"}  ${r.n}${r.d ? "  — " + r.d : ""}`);
console.log("=".repeat(72));
console.log(`console errors:   ${consoleErrors.length}`);
consoleErrors.slice(0, 10).forEach((e) => console.log("   ! " + e));
console.log(`failed requests:  ${failedRequests.length}`);
failedRequests.slice(0, 10).forEach((e) => console.log("   ! " + e));
console.log(`key leaks:        ${keyLeaks.length}`);
keyLeaks.slice(0, 10).forEach((e) => console.log("   ! " + e));

const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
await browser.close();
process.exit(failed || consoleErrors.length || keyLeaks.length ? 1 : 0);
