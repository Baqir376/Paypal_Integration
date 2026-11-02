> **Out of date on licensing.** This project is now MIT licensed, as the PayPal AI Hackathon
> requires an open-source licence. What follows about an all-rights-reserved licence no
> longer applies. `npm run dev` and `npm run build` no longer run the vault: it wrote old
> encrypted copies over current files. `npm run design:unlock` still would, so do not run it.

# Protecting the frontend

You asked for a mechanism that makes the UI impossible to copy, even by someone
feeding the code to an AI. This document is the honest answer, and then the
things that actually work.

## The part that cannot be done

**A frontend you ship cannot be made uncopyable.** This is not a gap in the
tooling; it is what shipping a web page means.

The browser has to receive renderable HTML and CSS or there is nothing to look
at. Anyone who can see the page can:

- open developer tools and read the **computed styles** of any element — this
  shows the final values regardless of how the source was written;
- take a screenshot and hand it to a model, which will approximate the layout,
  palette and type from the image alone, with no code involved at all;
- record a screen capture, which gives away the motion design.

Every technique sold as "code protection" fails against those three. Minifying
CSS does not help, because DevTools shows computed values, not source.
Obfuscating JavaScript does not help, because the design is in the CSS and the
DOM. Blocking right-click and blocking DevTools are theatre — bypassed in
seconds via view-source, the network tab, or simply disabling JavaScript — and
they break accessibility and keyboard use for legitimate visitors.

So: anyone determined enough will reproduce the *look*. What you can control is
whether they get the **implementation** handed to them, how much effort a copy
costs, and whether you can prove it happened.

## What was verified about this build

Measured on the actual production output, not assumed:

| | Result |
|---|---|
| Design-rationale comments in shipped CSS | **stripped** — none survive the build |
| Source maps | **not shipped** |
| Class names (`.svc-col`, `.sx-hero`) | **present**, and must be |
| Design tokens (`--ease-luxury`, `--accent-signal`) | **present**, and must be |

The reasoning behind the design does not ship. The design itself does, because
the browser renders from it.

## The mechanism: the design vault

`web/scripts/design-vault.mjs`

Every design-bearing file is **AES-256-GCM encrypted at rest**. The repository
carries the ciphertext; the plaintext is gitignored and never committed. A key
held only by you decrypts them before `dev` and `build`, automatically.

```bash
npm run design:keygen     # once — store the key somewhere safe
npm run design:lock       # encrypt for committing
npm run design:unlock     # restore for working (runs before dev/build)
npm run design:status     # what is protected, and its current state
```

The key comes from `SALIX_DESIGN_KEY` or `web/.design-key` (gitignored). Each
file gets its own random salt and IV, so identical files encrypt differently
and nothing can be inferred by comparison. The key is stretched with scrypt at
N=2^15, which is what stops a passphrase being brute-forced out of a public
repository.

### What is in the vault

18 files: the art direction, the product design system, every set piece, the
editorial compositions and the root layout.

```
app/system.css
app/effects.css
app/globals.css
components/system/ChapterSlides.tsx
components/system/Chrome.tsx
components/system/Cursor.tsx
components/system/HorizontalRun.tsx
components/system/Instruments.tsx
components/system/Loader.tsx
components/system/SiteFooter.tsx
components/system/StatusPill.tsx
components/system/SvcCols.tsx
components/system/TelemetryRail.tsx
components/system/primitives.tsx
app/page.tsx
app/archive/page.tsx
components/Motion.tsx
app/layout.tsx
```

### Verified, by building an actual keyless clone

A copy of the repository was made containing only what `git` would track — no
key, no plaintext — and then built and run.

| Check | Result |
|---|---|
| Signature colour `#d4f55a` anywhere | **not present** |
| Bark gold `#c7a15c` | **not present** |
| House easing `cubic-bezier(0.75, 0, 0.25, 1)` | **not present** |
| Typeface choices (`Instrument_Serif`, `Nastaliq`) | **not present** |
| Set-piece internals (`svc-col-spine`) | **not present** |
| `npm run build` | **succeeds** |
| Every route | **200** |
| JavaScript errors | **none** |

The clone resolves `--accent-signal` to a neutral blue, `--ease-luxury` to
plain `ease`, a white background and a system font — and renders a plain,
working page. With the key, the same checkout returns to `#d4f55a`, the real
curve and the full design.

### Two supporting changes

The palette used to be duplicated as hex literals inside the canvas and WebGL
components, which put it in the repository twice — once where it could be
protected and once where it could not. Those now read the value from the
stylesheet through `lib/tokens.ts`, so it is defined in exactly one place, and
they follow a theme change for free.

`components/effects/` — about a thousand lines that no route imported — was
deleted. Dead code that leaks design is the worst of both.

### The boundary, stated plainly

This protects the **repository**. Someone who visits a deployed site can still
inspect computed styles or take a screenshot, and a screenshot is enough for a
model to approximate a look. Nothing can change that without destroying the
product. What it does close, completely, is the door you asked about: code
pushed to GitHub, read by a person or fed to an AI, yields nothing.

## Further options, in order of effectiveness

### 1. Do not publish the frontend (the only real protection)

Everything else raises cost. This removes the source entirely.

Publish the backend — which is the substantial engineering, and the part worth
showing — and keep `web/` in a private repository.

```bash
# In the public repo
git rm -r --cached web
echo "web/" >> .gitignore
git commit -m "Move the frontend to a private repository"
```

Then push `web/` to a private repo of its own. If you want one working
checkout, add it back as a private submodule:

```bash
git submodule add git@github.com:<you>/salix-web-private.git web
```

Anyone cloning the public repo gets a complete, runnable backend with its API
contract and an empty `web/` they have no access to.

**The trade-off is real:** hackathon judges and recruiters cannot read what they
cannot clone. Decide which matters more for this repository. A common middle
path is to publish everything *after* judging, or to publish a stripped
frontend with the distinctive design removed.

### 2. Keep the design documentation private

This matters more than the code and is the cheapest thing to fix.

`docs/FRONTEND.md` and `docs/ASSET-MANIFEST.md` describe the entire system in
prose: the three-colour rule, the exact easing curves and why, the structure of
every set piece, the art direction for every image slot, and generation prompts
for recreating the photography.

Someone handed those documents can rebuild the design **without reading a single
line of code**. They are strictly more copyable than the implementation. If you
publish only one of the two, publish the code and keep the docs.

```bash
git rm --cached docs/FRONTEND.md docs/ASSET-MANIFEST.md
echo "docs/FRONTEND.md" >> .gitignore
echo "docs/ASSET-MANIFEST.md" >> .gitignore
```

### 3. Licence it against copying

The repository previously said **MIT**, which is a licence that explicitly
grants everyone the right to copy, modify and redistribute — including
commercially. That directly contradicted the goal.

`LICENSE` is now all-rights-reserved, and states that no permission is granted
for reproduction, derivative works, or use as reference or training material.

This does not stop a copy technically. It is what makes a copy actionable —
which, against anyone with a company or a reputation, is the deterrent that
actually bites. Combined with the watermark below, it is the difference between
"that looks similar" and "that is provably mine".

### 4. Watermark it, so a copy is provable

A wholesale copy carries the marker with it. It costs nothing, changes no
pixels, and turns a suspicion into evidence.

See `--sx-provenance` in `web/app/system.css`. Keep a private note of the value
and the date it was introduced.

### 5. Build hygiene

Already true of this build, and worth not regressing:

- `productionBrowserSourceMaps` stays off, so no original sources ship.
- Comments are stripped from production CSS.
- Do not commit `.next/` or any build output.

### What is deliberately **not** done

- **DevTools blocking / right-click disabling.** Bypassed instantly, breaks
  keyboard and assistive-technology users, and signals amateurism to exactly
  the technical audience you would want to impress.
- **JavaScript obfuscation.** The design is in CSS and DOM structure. This
  would slow the site down and protect nothing.
- **Rendering the UI to canvas or images.** It would defeat screen readers,
  text selection, search and zoom — destroying the product to protect its
  appearance.

## Summary

| Goal | Achievable |
|---|---|
| Nobody can reproduce the look | **No.** A screenshot is enough. |
| Nobody gets your implementation | **Yes** — keep `web/` private. |
| Copying is legally actionable | **Yes** — proprietary licence + watermark. |
| Copying costs real effort | **Yes** — private source, private design docs. |

The strongest realistic position is: publish the backend, keep the frontend and
the design docs private, licence everything all-rights-reserved, and watermark
the build. That is what has been set up. The remaining step — actually splitting
the repository — is one command, and it is your call, because it trades
visibility for protection.
