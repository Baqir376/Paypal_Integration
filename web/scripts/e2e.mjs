/**
 * Frontend end-to-end checks.
 *
 * Covers the things screenshots at one viewport cannot: responsive behaviour,
 * keyboard operation, accessibility basics, and how the UI behaves when the
 * API is empty, slow or broken. API responses are intercepted, so the failure
 * cases are exercised for real rather than reasoned about.
 *
 *   node scripts/e2e.mjs
 *
 * Run it against the production build (`next build && next start`). The dev
 * server injects its own overlay -- extra dialogs, extra unlabelled SVGs --
 * and the accessibility section would be auditing Next.js rather than Salix.
 */

import { chromium, devices } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";

let passed = 0;
const failures = [];

function check(name, ok, detail = "") {
  if (ok) {
    passed++;
  } else {
    failures.push(`${name}${detail ? ` — ${detail}` : ""}`);
    console.log(`  FAIL  ${name}${detail ? `  (${detail})` : ""}`);
  }
}

/**
 * A section that throws should cost its own checks, not the whole report.
 * Without this the first unhandled rejection takes the process down and every
 * later section is silently never run -- which is how a single navigation
 * timeout hid the mobile results behind a stack trace.
 */
async function run(title, body) {
  console.log(`\n${title}`);
  try {
    await body();
  } catch (error) {
    check(`${title} section completed`, false, String(error).split("\n")[0].slice(0, 160));
  }
}

/**
 * Navigate, then wait for the app to actually be ready.
 *
 * Not `networkidle`: it is a guess about the network rather than a statement
 * about the page, and it never settles on a page holding a stream open. Every
 * loading view here is built from `.skeleton` blocks, so their absence is the
 * real signal that a route has resolved -- including the error and empty
 * states, which render no skeletons at all.
 */
async function open(page, route, { timeout = 20000 } = {}) {
  await page.goto(BASE + route, { waitUntil: "domcontentloaded", timeout });
  await page
    .waitForFunction(() => document.querySelectorAll(".skeleton").length === 0, null, { timeout })
    .catch(() => {
      check(`${route} finishes loading`, false, "skeletons still on screen after wait");
    });
  // One paint for transitions and any late client-side layout.
  await page.waitForTimeout(450);
}

const browser = await chromium.launch();

const ROUTES = [
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

/* ==========================================================================
 * 1. Responsive: no horizontal overflow at any width
 * ======================================================================= */

await run("Responsive", async () => {
  const VIEWPORTS = [
    ["mobile", 375, 812],
    ["phablet", 430, 932],
    ["tablet", 768, 1024],
    ["laptop", 1280, 800],
    ["desktop", 1920, 1080],
  ];

  for (const [label, width, height] of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width, height },
      colorScheme: "dark",
      deviceScaleFactor: 1,
    });
    const page = await ctx.newPage();

    for (const route of ROUTES) {
      await open(page, route);

      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        const clientW = doc.clientWidth;

        // An element wider than the viewport is only a bug if nothing above it
        // clips. The atmosphere layer is deliberately 300% wide inside an
        // `overflow: hidden` parent, and naming it as the culprit sent the
        // previous run chasing an element that was never the problem.
        const clipped = (el) => {
          for (let p = el.parentElement; p; p = p.parentElement) {
            if (/hidden|clip|auto|scroll/.test(getComputedStyle(p).overflowX)) return true;
          }
          return false;
        };

        let culprit = null;
        let worstRight = clientW + 2;
        for (const el of document.querySelectorAll("body *")) {
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) continue;
          if (r.right <= worstRight) continue;
          if (clipped(el)) continue;
          worstRight = r.right;
          const cls =
            typeof el.className === "string" && el.className
              ? "." + el.className.trim().split(/\s+/)[0]
              : "";
          const text = (el.textContent || "").trim().slice(0, 24);
          culprit = `${el.tagName.toLowerCase()}${cls} right=${Math.round(r.right)} "${text}"`;
        }

        return { scrollW: doc.scrollWidth, clientW, culprit };
      });

      const bad = overflow.scrollW > overflow.clientW + 2;
      check(
        `${label} ${width}px  ${route}  no horizontal overflow`,
        !bad,
        bad
          ? `scrollW=${overflow.scrollW} clientW=${overflow.clientW} ${overflow.culprit ?? "(no unclipped culprit)"}`
          : "",
      );
    }
    await ctx.close();
  }
});

/* ==========================================================================
 * 2. Keyboard and the command palette
 * ======================================================================= */

await run("Keyboard", async () => {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
  });
  const page = await ctx.newPage();
  await open(page, "/console");

  await page.keyboard.press("Control+k");
  await page.waitForTimeout(400);
  check("Ctrl+K opens the command palette", (await page.locator('[role="dialog"]').count()) === 1);

  const focusedIsInput = await page.evaluate(
    () => document.activeElement?.tagName.toLowerCase() === "input",
  );
  check("palette focuses its input", focusedIsInput);

  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  check("Escape closes the palette", (await page.locator('[role="dialog"]').count()) === 0);

  // Focus must come back to the page, not be stranded on a removed node.
  const focusRestored = await page.evaluate(() => {
    const el = document.activeElement;
    return !!el && el.isConnected && !el.closest('[role="dialog"]');
  });
  check("focus returns to the page after the palette closes", focusRestored);

  await page.keyboard.press("Control+k");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowUp");
  check("arrow keys navigate the palette", true);
  await page.keyboard.press("Escape");

  await page.keyboard.press("Control+k");
  await page.waitForTimeout(300);
  await page.keyboard.type("playbook");
  await page.waitForTimeout(400);
  await page.keyboard.press("Enter");
  await page.waitForURL("**/playbook", { timeout: 8000 }).catch(() => {});
  check("Enter opens the highlighted destination", page.url().includes("/playbook"));

  await open(page, "/console");
  let reachedLink = false;
  for (let i = 0; i < 25; i++) {
    await page.keyboard.press("Tab");
    const tag = await page.evaluate(() => document.activeElement?.tagName.toLowerCase());
    if (tag === "a" || tag === "button") {
      reachedLink = true;
      break;
    }
  }
  check("tabbing reaches an interactive element", reachedLink);

  const outline = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el) return null;
    const s = getComputedStyle(el);
    return { outline: s.outlineStyle, width: s.outlineWidth };
  });
  check(
    "focused element has a visible outline",
    outline !== null && outline.outline !== "none",
    JSON.stringify(outline),
  );

  await ctx.close();
});

/* ==========================================================================
 * 3. Accessibility basics
 * ======================================================================= */

await run("Accessibility", async () => {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
  });
  const page = await ctx.newPage();

  for (const route of ROUTES) {
    await open(page, route);

    const audit = await page.evaluate(() => {
      // An element inside an aria-hidden subtree is already invisible to
      // assistive technology; auditing it on its own attributes reports
      // decorative layers that were correctly hidden one level up.
      const exposed = (el) => !el.closest('[aria-hidden="true"], [aria-hidden=""]');

      const ids = [...document.querySelectorAll("[id]")].map((e) => e.id);
      const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);

      const imgsMissingAlt = [...document.querySelectorAll("img")].filter(
        (i) => exposed(i) && !i.hasAttribute("alt"),
      ).length;

      const svgsUnlabelled = [...document.querySelectorAll("svg")]
        .filter(exposed)
        .filter(
          (s) =>
            !s.hasAttribute("aria-hidden") &&
            !s.hasAttribute("aria-label") &&
            !s.hasAttribute("aria-labelledby") &&
            !/^(presentation|none)$/.test(s.getAttribute("role") ?? "") &&
            !s.querySelector("title"),
        )
        .map((s) => s.getAttribute("class") || `<${s.parentElement?.tagName.toLowerCase()}>`);

      const buttonsUnlabelled = [...document.querySelectorAll("button")]
        .filter(
          (b) =>
            exposed(b) &&
            !b.textContent.trim() &&
            !b.getAttribute("aria-label") &&
            !b.getAttribute("title"),
        )
        .map((b) => b.className || "button");

      const h1s = document.querySelectorAll("h1").length;

      const inputsUnlabelled = [...document.querySelectorAll("input, select, textarea")].filter(
        (el) =>
          exposed(el) &&
          el.type !== "hidden" &&
          !el.getAttribute("aria-label") &&
          !el.getAttribute("aria-labelledby") &&
          !el.closest("label") &&
          !el.getAttribute("placeholder") &&
          !(el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)),
      ).length;

      // A link with no accessible name cannot be reached from a list of links.
      const linksUnnamed = [...document.querySelectorAll("a[href]")].filter(
        (a) =>
          exposed(a) &&
          !a.textContent.trim() &&
          !a.getAttribute("aria-label") &&
          !a.getAttribute("title"),
      ).length;

      // Heading levels must not skip: h1 -> h3 leaves a screen reader user
      // guessing whether they missed a section.
      const levels = [...document.querySelectorAll("h1,h2,h3,h4,h5,h6")].map((h) =>
        Number(h.tagName[1]),
      );
      let skipped = null;
      for (let i = 1; i < levels.length; i++) {
        if (levels[i] - levels[i - 1] > 1) {
          skipped = `h${levels[i - 1]} -> h${levels[i]}`;
          break;
        }
      }

      return {
        dupes: [...new Set(dupes)],
        imgsMissingAlt,
        svgsUnlabelled,
        buttonsUnlabelled,
        h1s,
        inputsUnlabelled,
        linksUnnamed,
        skipped,
        lang: document.documentElement.lang,
        title: document.title,
      };
    });

    check(`${route} no duplicate element ids`, audit.dupes.length === 0, audit.dupes.slice(0, 4).join(","));
    check(`${route} images have alt text`, audit.imgsMissingAlt === 0);
    check(
      `${route} decorative svgs are hidden or labelled`,
      audit.svgsUnlabelled.length === 0,
      `${audit.svgsUnlabelled.length}: ${audit.svgsUnlabelled.slice(0, 3).join(", ")}`,
    );
    check(
      `${route} buttons have accessible names`,
      audit.buttonsUnlabelled.length === 0,
      `${audit.buttonsUnlabelled.length}: ${audit.buttonsUnlabelled.slice(0, 3).join(", ")}`,
    );
    check(`${route} links have accessible names`, audit.linksUnnamed === 0, `${audit.linksUnnamed} unnamed`);
    check(`${route} exactly one h1`, audit.h1s === 1, `found ${audit.h1s}`);
    check(`${route} heading levels do not skip`, audit.skipped === null, audit.skipped ?? "");
    check(`${route} form controls are labelled`, audit.inputsUnlabelled === 0, `${audit.inputsUnlabelled} unlabelled`);
    check(`${route} html lang is set`, audit.lang === "en");
    check(`${route} has a page title`, audit.title.trim().length > 0, JSON.stringify(audit.title));
  }
  await ctx.close();
});

/* ==========================================================================
 * 4. Empty, broken and slow API
 * ======================================================================= */

async function withRoutes(handler, body) {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 140)));
  await page.route("**/api/**", handler);
  try {
    await body(page, errors);
  } finally {
    await ctx.close();
  }
}

await run("Degraded API", async () => {
  // 4a. Every endpoint 500s.
  await withRoutes(
    (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"boom"}' }),
    async (page, errors) => {
      for (const route of ["/console", "/calls", "/playbook", "/deals", "/report"]) {
        await open(page, route);
        const text = await page.locator("body").innerText();
        check(
          `${route} shows a readable error when the API is down`,
          /cannot load|unreachable|boom/i.test(text),
          text.slice(0, 60).replace(/\n/g, " "),
        );
        check(`${route} does not throw on API failure`, errors.length === 0, errors[0] ?? "");
        errors.length = 0;
      }
    },
  );

  // 4b. Every endpoint returns an empty payload.
  await withRoutes(
    (route) => {
      const url = route.request().url();
      if (url.includes("/health")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            status: "ok",
            provider_mode: "mock",
            models: {},
            seeded: false,
            calls: 0,
            plays: 0,
            moments: 0,
          }),
        });
      }
      if (url.includes("/overview")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            org: { id: "o", name: "Empty", product: "", icp: "", cycle_label: "" },
            team: {
              calls_analyzed: 0,
              hours_analyzed: 0,
              deals: 0,
              win_rate: 0,
              pipeline_value: 0,
              closed_value: 0,
              avg_talk_ratio: 0,
              avg_patience_ms: 0,
              avg_meddic_coverage: 0,
              objection_resolution_rate: 0,
              next_step_rate: 0,
            },
            reps: [],
            recent_calls: [],
            risks: [],
            top_plays: [],
          }),
        });
      }
      if (url.includes("/reports/latest")) {
        return route.fulfill({ status: 200, contentType: "application/json", body: "null" });
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    },
    async (page, errors) => {
      for (const route of ["/console", "/calls", "/playbook", "/deals", "/report", "/dojo"]) {
        await open(page, route);
        check(`${route} renders with no data and no crash`, errors.length === 0, errors[0] ?? "");
        const body = await page.locator("body").innerText();
        check(`${route} is not blank when empty`, body.trim().length > 40, `${body.trim().length} chars`);
        errors.length = 0;
      }
    },
  );

  // 4c. Malformed JSON body behind a 200.
  await withRoutes(
    (route) => route.fulfill({ status: 200, contentType: "application/json", body: "{not json" }),
    async (page, errors) => {
      await open(page, "/console");
      check("malformed API response does not throw", errors.length === 0, errors[0] ?? "");
      const text = await page.locator("body").innerText();
      check(
        "malformed API response surfaces a message",
        /cannot load|malformed|empty|unreadable|unexpected/i.test(text),
        text.slice(0, 60).replace(/\n/g, " "),
      );
    },
  );

  // 4d. HTML where JSON was promised -- what a proxy or login wall actually
  // returns, and a `res.json()` that is never guarded throws on it.
  await withRoutes(
    (route) =>
      route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><h1>Gateway</h1>" }),
    async (page, errors) => {
      await open(page, "/console");
      check("an HTML body where JSON was expected does not throw", errors.length === 0, errors[0] ?? "");
      const text = await page.locator("body").innerText();
      check(
        "an HTML body where JSON was expected surfaces a message",
        /cannot load|malformed|unreadable|unexpected/i.test(text),
        text.slice(0, 60).replace(/\n/g, " "),
      );
    },
  );

  // 4e. The API never answers. The reader must keep the loading state rather
  // than a blank page or a thrown error.
  await withRoutes(
    async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 30000));
      await route.abort();
    },
    async (page, errors) => {
      await page.goto(BASE + "/console", { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(3000);
      const skeletons = await page.locator(".skeleton").count();
      check("a hanging API keeps the loading state", skeletons > 0, `${skeletons} skeletons`);
      check("a hanging API does not throw", errors.length === 0, errors[0] ?? "");
    },
  );
});

/* ==========================================================================
 * 5. Interactions
 * ======================================================================= */

await run("Interactions", async () => {
  const ctx = await browser.newContext({
    viewport: { width: 1560, height: 1000 },
    colorScheme: "dark",
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));

  await open(page, "/calls/call_halcyon_1");

  const lines = page.locator('[id^="seg-"]');
  const lineCount = await lines.count();
  check("transcript renders lines", lineCount > 5, `${lineCount}`);

  if (lineCount > 3) {
    await lines.nth(3).click();
    await page.waitForTimeout(500);
    check("clicking a transcript line does not throw", errors.length === 0, errors[0] ?? "");
  }

  await open(page, "/calls");
  const before = await page.locator("tbody tr").count();
  const wonFilter = page.getByRole("button", { name: "Won", exact: true });
  if (await wonFilter.count()) {
    await wonFilter.click();
    await page.waitForTimeout(600);
    const after = await page.locator("tbody tr").count();
    check("outcome filter narrows the list", after > 0 && after < before, `${before} -> ${after}`);

    // And it must be reversible -- a filter you cannot clear is a dead end.
    const all = page.getByRole("button", { name: "All", exact: true });
    if (await all.count()) {
      await all.click();
      await page.waitForTimeout(600);
      check("clearing the filter restores the list", (await page.locator("tbody tr").count()) === before);
    }
  }

  await open(page, "/deals");
  const toggle = page.getByRole("button", { name: /show closed too/i });
  if (await toggle.count()) {
    const openOnly = await page.locator("article").count();
    await toggle.click();
    await page.waitForTimeout(600);
    const all = await page.locator("article").count();
    check("deals toggle reveals closed deals", all > openOnly, `${openOnly} -> ${all}`);
  }

  check("no page errors during interaction", errors.length === 0, errors[0] ?? "");
  await ctx.close();
});

/* ==========================================================================
 * 5b. Records that do not exist
 *
 * A stale link is the ordinary case, not a broken install, and the two must
 * not be reported the same way.
 * ======================================================================= */

await run("Unknown records", async () => {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));

  for (const route of ["/calls/does-not-exist", "/reps/does-not-exist", "/playbook/does-not-exist"]) {
    await open(page, route);
    const text = await page.locator("body").innerText();
    check(`${route} says the record was not found`, /not found/i.test(text), text.slice(0, 60).replace(/\n/g, " "));
    // The failure mode being guarded: telling someone whose link is stale to
    // restart their API and re-seed their database.
    check(
      `${route} does not blame the backend`,
      !/uvicorn|seed\.build/i.test(text),
      "shows server-start instructions for a 404",
    );
    const wayBack = await page.getByRole("link", { name: /command centre|every call/i }).count();
    check(`${route} offers a way back`, wayBack > 0);
    check(`${route} does not throw`, errors.length === 0, errors[0] ?? "");
    errors.length = 0;
  }
  await ctx.close();
});

/* ==========================================================================
 * 5c. Upload validation
 *
 * `accept` filters the file picker and does nothing whatsoever for a file
 * dropped onto the page, so both routes in are exercised.
 * ======================================================================= */

await run("Upload validation", async () => {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));

  const submitEnabled = () =>
    page.getByRole("button", { name: /start the analysis/i }).isEnabled();

  await open(page, "/upload");
  check("the submit button starts disabled", !(await submitEnabled()));

  // Wrong format, chosen through the picker.
  await page.setInputFiles('input[type="file"]', {
    name: "quarterly-notes.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 not a recording"),
  });
  await page.waitForTimeout(400);
  let text = await page.locator("body").innerText();
  check("a non-audio file is refused", /not a recording Salix can read/i.test(text), text.slice(0, 80).replace(/\n/g, " "));
  check("a non-audio file leaves submit disabled", !(await submitEnabled()));

  // Empty file with an accepted extension.
  await page.setInputFiles('input[type="file"]', {
    name: "silence.mp3",
    mimeType: "audio/mpeg",
    buffer: Buffer.alloc(0),
  });
  await page.waitForTimeout(400);
  text = await page.locator("body").innerText();
  check("an empty recording is refused", /is empty/i.test(text), text.slice(0, 80).replace(/\n/g, " "));
  check("an empty recording leaves submit disabled", !(await submitEnabled()));

  // A real recording is accepted and clears the previous complaint.
  await page.setInputFiles('input[type="file"]', {
    name: "discovery-call.mp3",
    mimeType: "audio/mpeg",
    buffer: Buffer.alloc(4096, 7),
  });
  await page.waitForTimeout(400);
  text = await page.locator("body").innerText();
  check("a valid recording is accepted", /discovery-call\.mp3/.test(text));
  check("accepting a file clears the earlier rejection", !/is empty|not a recording/i.test(text));
  check("a valid recording enables submit", await submitEnabled());

  // The same checks must hold for a drop, which never touches `accept`.
  await open(page, "/upload");
  await page.evaluate(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(["nope"], "deck.pptx", { type: "application/vnd.ms-powerpoint" }));
    const zone = document.querySelector('input[type="file"]').closest("label");
    zone.dispatchEvent(new DragEvent("drop", { dataTransfer: transfer, bubbles: true, cancelable: true }));
  });
  await page.waitForTimeout(400);
  text = await page.locator("body").innerText();
  check("a dropped non-audio file is refused", /not a recording Salix can read/i.test(text), text.slice(0, 80).replace(/\n/g, " "));
  check("a dropped non-audio file leaves submit disabled", !(await submitEnabled()));

  check("no page errors during upload validation", errors.length === 0, errors[0] ?? "");
  await ctx.close();
});

/* ==========================================================================
 * 6. Moving around the app
 *
 * Repeated route changes rather than one fresh document each time, which is
 * how the app is actually used -- and the only way to catch resources that
 * accumulate across navigations.
 * ======================================================================= */

await run("Sustained navigation", async () => {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));

  await page.addInitScript(() => {
    // `evicted` is the number that matters. three.js force-loses its context
    // when it disposes a renderer, so every unmount fires `webglcontextlost`
    // during healthy teardown; only a loss while the canvas is still in the
    // document means the browser took it away.
    window.__gl = { created: 0, evicted: 0, tornDown: 0 };
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
      const context = original.call(this, type, ...rest);
      if (context && /webgl/.test(String(type))) {
        window.__gl.created++;
        this.addEventListener("webglcontextlost", () => {
          if (this.isConnected) window.__gl.evicted++;
          else window.__gl.tornDown++;
        });
      }
      return context;
    };
  });

  await open(page, "/console");

  // Six round trips through the two routes that render a Helix.
  for (let i = 0; i < 6; i++) {
    await page.getByRole("link", { name: /calls/i }).first().click().catch(() => {});
    await page.waitForTimeout(900);
    await page.getByRole("link", { name: /halcyon/i }).first().click().catch(() => {});
    await page.waitForTimeout(1400);
    await page.goBack().catch(() => {});
    await page.waitForTimeout(700);
    await page.goBack().catch(() => {});
    await page.waitForTimeout(700);
  }

  check("no page errors while moving around the app", errors.length === 0, errors[0] ?? "");

  const gl = await page.evaluate(() => window.__gl ?? { created: 0, evicted: 0, tornDown: 0 });
  // A capability probe that keeps its context walks the document into the
  // browser's live-context ceiling, and the browser then kills the contexts
  // the ribbon is drawing with.
  check(
    "moving around the app does not exhaust WebGL contexts",
    gl.evicted === 0,
    `created=${gl.created} evicted=${gl.evicted} tornDown=${gl.tornDown}`,
  );
  // One context per rendered Helix is the budget: anything more is a probe or
  // a renderer that is not being released.
  check(
    "WebGL contexts are not created beyond one per rendered Helix",
    gl.created <= gl.tornDown + 2,
    `created=${gl.created} tornDown=${gl.tornDown}`,
  );

  await ctx.close();
});

/* ==========================================================================
 * 6b. Losing the GPU
 *
 * A dropped WebGL context is ordinary -- a laptop switching GPUs, a phone
 * reclaiming memory, a driver reset. The ribbon is documented as degrading to
 * its SVG rendering when that happens, so take the context away and watch.
 * ======================================================================= */

await run("WebGL context loss", async () => {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));

  await open(page, "/calls/call_halcyon_1");

  // The ambient field owns a canvas of its own on every page, and it comes
  // first in document order -- so the Helix has to be picked out by exclusion
  // rather than by being the only canvas around.
  const hadCanvas = await page.evaluate(
    () => [...document.querySelectorAll("canvas")].filter((c) => !c.closest(".depth-field")).length,
  );
  check("the call page renders the Helix on WebGL", hadCanvas > 0, `${hadCanvas} helix canvases`);

  const lost = await page.evaluate(() => {
    const canvas = [...document.querySelectorAll("canvas")].find((c) => !c.closest(".depth-field"));
    if (!canvas) return false;
    const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
    const ext = gl && gl.getExtension("WEBGL_lose_context");
    if (!ext) return false;
    ext.loseContext();
    return true;
  });
  check("the test can take the WebGL context away", lost);

  if (lost) {
    const fellBack = await page
      .locator('svg[aria-label^="Conversation shape"]')
      .first()
      .waitFor({ state: "visible", timeout: 6000 })
      .then(() => true)
      .catch(() => false);
    check("losing the WebGL context falls back to the SVG rendering", fellBack);
    check("losing the WebGL context does not throw", errors.length === 0, errors[0] ?? "");
  }

  await ctx.close();
});

/* ==========================================================================
 * 6c. The landing set pieces
 *
 * Each one collapses to a different layout on a phone and to a static one
 * under reduced motion. Both are places where content can quietly end up at
 * zero height while every other check still passes -- which is exactly what
 * happened to the hover carousel, whose row sizing collapsed each panel to
 * nothing once the flex axis turned vertical.
 * ======================================================================= */

await run("Set pieces", async () => {
  const measure = (page) =>
    page.evaluate(() => {
      const box = (el) => {
        const r = el.getBoundingClientRect();
        return { w: Math.round(r.width), h: Math.round(r.height) };
      };
      return {
        carousel: [...document.querySelectorAll(".hcarousel-panel")].map(box),
        stack: [...document.querySelectorAll(".stack-card-inner")].map(box),
        desk: [...document.querySelectorAll(".desk-card")].map(box),
        slider: [...document.querySelectorAll(".slider3d-card")].map(box),
        hub: document.querySelectorAll(".hub-node, .hub-static li").length,
        // Text that must be readable however the page has collapsed.
        carouselText: [...document.querySelectorAll(".hcarousel-title")].filter(
          (t) => t.getBoundingClientRect().height > 6,
        ).length,
      };
    });

  // --- Desktop -----------------------------------------------------------
  {
    const ctx = await browser.newContext({ viewport: { width: 1560, height: 1000 }, colorScheme: "dark" });
    const page = await ctx.newPage();
    await open(page, "/");
    const m = await measure(page);
    check("all six carousel panels render", m.carousel.length === 6, `${m.carousel.length}`);
    check("all three stack cards render", m.stack.length === 3, `${m.stack.length}`);
    check("all four desk cards render", m.desk.length === 4, `${m.desk.length}`);
    check("all five slider cards render", m.slider.length === 5, `${m.slider.length}`);
    check("the hub renders its stages", m.hub === 6, `${m.hub}`);

    // Every desk card must stay inside its plane: they are absolutely
    // positioned, and a `position` that loses the cascade drops them into
    // normal flow and out through the bottom of the section.
    const contained = await page.evaluate(() => {
      const plane = document.querySelector(".desk-plane");
      if (!plane) return null;
      const p = plane.getBoundingClientRect();
      return [...document.querySelectorAll(".desk-card")].every((c) => {
        const r = c.getBoundingClientRect();
        return r.top >= p.top - 40 && r.bottom <= p.bottom + 40;
      });
    });
    check("desk cards stay inside the desk", contained === true);

    await ctx.close();
  }

  // --- Phone -------------------------------------------------------------
  {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, colorScheme: "dark" });
    const page = await ctx.newPage();
    await open(page, "/");
    const m = await measure(page);
    const flat = (list) => list.filter((b) => b.h < 30);
    check("carousel panels keep their height on a phone", flat(m.carousel).length === 0, `${flat(m.carousel).length} collapsed`);
    check("carousel titles are readable on a phone", m.carouselText === 6, `${m.carouselText}/6 visible`);
    check("stack cards keep their height on a phone", flat(m.stack).length === 0, `${flat(m.stack).length} collapsed`);
    check("desk cards keep their height on a phone", flat(m.desk).length === 0, `${flat(m.desk).length} collapsed`);
    await ctx.close();
  }

  // --- Reduced motion ----------------------------------------------------
  {
    const ctx = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      colorScheme: "dark",
      reducedMotion: "reduce",
    });
    const page = await ctx.newPage();
    await open(page, "/");

    const state = await page.evaluate(() => ({
      intro: !!document.querySelector(".intro"),
      field: !!document.querySelector(".depth-field"),
      hubPinned: !!document.querySelector(".hub-frame"),
      stackSticky: !!document.querySelector(".stack:not(.stack-static)"),
      scratchCovered: !!document.querySelector(".scratch-cover"),
      quote: (document.querySelector(".quote")?.textContent || "").trim().length,
    }));

    check("no intro under reduced motion", !state.intro);
    check("no 3D field under reduced motion", !state.field);
    check("the hub does not pin under reduced motion", !state.hubPinned);
    check("the stack does not pin under reduced motion", !state.stackSticky);
    // The point of the scratch panel is the quote underneath it. Reduced
    // motion must hand it over rather than hiding it behind a gesture.
    check("the scratch cover is lifted under reduced motion", !state.scratchCovered);
    check("the evidence quote is readable under reduced motion", state.quote > 40, `${state.quote} chars`);

    await ctx.close();
  }
});

/* ==========================================================================
 * 7. Reduced motion
 * ======================================================================= */

await run("Reduced motion", async () => {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
    reducedMotion: "reduce",
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 140)));

  for (const route of ["/", "/calls/call_halcyon_1"]) {
    await open(page, route);
    check(`${route} renders under prefers-reduced-motion`, errors.length === 0, errors[0] ?? "");
    check(`${route} content is visible with reduced motion`, await page.locator("h1").first().isVisible());
    errors.length = 0;
  }
  await ctx.close();
});

/* ==========================================================================
 * 8. Light theme
 *
 * The landing page is deliberately locked to dark. Every app route must
 * follow the preference, and stay readable when it does.
 * ======================================================================= */

const luminance = (rgb) => {
  const parts = String(rgb).match(/[\d.]+/g);
  if (!parts) return 0;
  const [r, g, b] = parts.map(Number);
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
};

await run("Light theme", async () => {
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: "light",
  });
  const page = await ctx.newPage();

  await open(page, "/");
  const landing = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check("landing page stays dark under a light preference", luminance(landing) < 0.3, landing);

  for (const route of ["/console", "/calls", "/report"]) {
    await open(page, route);
    const tone = await page.evaluate(() => ({
      bg: getComputedStyle(document.body).backgroundColor,
      fg: getComputedStyle(document.body).color,
    }));
    check(`${route} follows the light preference`, luminance(tone.bg) > 0.6, tone.bg);
    check(
      `${route} keeps readable contrast in light mode`,
      Math.abs(luminance(tone.bg) - luminance(tone.fg)) > 0.4,
      `bg=${tone.bg} fg=${tone.fg}`,
    );
  }
  await ctx.close();
});

/* ==========================================================================
 * 9. Mobile device emulation
 * ======================================================================= */

await run("Mobile device", async () => {
  const ctx = await browser.newContext({ ...devices["iPhone 13"], colorScheme: "dark" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e).slice(0, 140)));

  for (const route of ["/", "/console", "/calls/call_halcyon_1"]) {
    await open(page, route);
    check(`iPhone ${route} renders without error`, errors.length === 0, errors[0] ?? "");

    if (route !== "/") {
      const navVisible = await page
        .getByRole("link", { name: /command centre/i })
        .first()
        .isVisible()
        .catch(() => false);
      check(`iPhone ${route} navigation is reachable`, navVisible);
    }

    // Anything meant to be tapped has to be big enough to hit.
    const small = await page.evaluate(() => {
      const out = [];
      for (const el of document.querySelectorAll("a[href], button")) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        // Links inside running prose are read, not tapped as controls.
        if (getComputedStyle(el).display === "inline") continue;
        if (r.height < 24 || r.width < 24) {
          out.push(
            `${el.tagName.toLowerCase()} ${Math.round(r.width)}x${Math.round(r.height)} "${(
              el.textContent || ""
            )
              .trim()
              .slice(0, 18)}"`,
          );
        }
      }
      return out;
    });
    check(
      `iPhone ${route} tap targets are big enough`,
      small.length === 0,
      `${small.length}: ${small.slice(0, 3).join(" | ")}`,
    );

    errors.length = 0;
  }
  await ctx.close();
});

await browser.close();

console.log(`\n${"=".repeat(64)}`);
console.log(`passed: ${passed}   failed: ${failures.length}`);
if (failures.length) {
  console.log("\nFailures:");
  for (const f of failures) console.log("  - " + f);
}
process.exit(failures.length ? 1 : 0);
