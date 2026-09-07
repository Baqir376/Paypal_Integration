# Asset manifest

Every image slot in the Salix frontend, the plate currently sourced for it, and
what to generate or shoot if you want to replace it.

## How the slots work

No image is referenced from markup. Every plate is a CSS custom property
declared once in [`web/app/system.css`](../web/app/system.css), section 1:

```css
:root {
  --img-hero:  url("https://images.unsplash.com/photo-1478737270239-…");
  --img-ch-01: url("https://images.unsplash.com/photo-1590602847861-…");
  /* … */
}
```

Components reference the *name* of the variable, never the URL, so swapping the
sourced photograph for a local file is one edit per slot and never a hunt
through JSX:

```css
--img-hero: url("/images/hero-bg.webp");
```

**Colour grading is done in CSS, not in the file.** Every plate is rendered
through some combination of `grayscale(1) contrast(1.2) brightness(0.3–0.62)`
plus a gradient scrim, so one photograph serves the whole palette and replacing
it never re-opens the grade. Deliver source files **ungraded** — full colour,
full range. If you hand over an already-desaturated plate it will be
desaturated twice and go flat.

**Where to put local files.** Next serves `web/public/` at the site root, so a
file at `web/public/images/hero-bg.webp` is `url("/images/hero-bg.webp")`.

---

## Download / generation table

| # | Slot | Local path | Ratio & resolution | Art direction | Source (Unsplash CDN) |
|---|------|-----------|--------------------|---------------|----------------------|
| 1 | `--img-hero` | `images/hero-bg.webp` | 16:9 — **2400 × 1350** | A large-diaphragm condenser microphone in a shock mount, three-quarter view, in an unlit studio. Subject occupies the right third; the left two-thirds fall to near-black so the headline has a ground. Specular highlights on the grille only — no visible operator, no branding, no desk clutter. | [`photo-1478737270239-2f02b77fc618`](https://images.unsplash.com/photo-1478737270239-2f02b77fc618?q=80&w=2400&auto=format&fit=crop) |
| 2 | `--img-ch-01` *Transcriptionist* | `images/sections/01.webp` | 4:5 — **1200 × 1500** | A broadcast dynamic microphone on a counterweighted boom arm, hanging into frame from the top left against a seamless charcoal sweep. Hard key from camera left, deep falloff right. The instrument of listening, isolated. | [`photo-1590602847861-f357a9332bbc`](https://images.unsplash.com/photo-1590602847861-f357a9332bbc?q=80&w=1800&auto=format&fit=crop) |
| 3 | `--img-ch-02` *Prosodist* | `images/sections/02.webp` | 4:5 — **1200 × 1500** | A dense measurement grid filling a laptop screen — fine ruled lines, a plotted trace, tick labels too small to read. Shot slightly off-axis so the panel has perspective. No recognisable application chrome. This slot is arithmetic, so it must read as a ruler rather than as a dashboard. | [`photo-1518186285589-2f7649de83e0`](https://images.unsplash.com/photo-1518186285589-2f7649de83e0?q=80&w=1800&auto=format&fit=crop) |
| 4 | `--img-ch-03` *Anatomist* | `images/sections/03.webp` | 4:5 — **1200 × 1500** | Two pairs of hands annotating a printed document with pencils, seen from above at a slight angle. Faces out of frame. The gesture is *marking a specific line* — the visual argument for citation. | [`photo-1454165804606-c3d57bc86b40`](https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?q=80&w=1800&auto=format&fit=crop) |
| 5 | `--img-ch-04` *Playwright* | `images/sections/04.webp` | 4:5 — **1200 × 1500** | Hands caught mid-gesture across a meeting table, a laptop out of focus behind them. Motion implied but not blurred. A move being made, not a meeting being held. | [`photo-1517245386807-bb43f82c33c4`](https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?q=80&w=1800&auto=format&fit=crop) |
| 6 | `--img-ch-05` *Coach* | `images/sections/05.webp` | 4:5 — **1200 × 1500** | Directly overhead: a clean desk with a laptop, a desk phone, a notebook and a single cup. Strong top light, hard shadows, generous negative space. The place a call is actually taken from. | [`photo-1520607162513-77705c0f0d4a`](https://images.unsplash.com/photo-1520607162513-77705c0f0d4a?q=80&w=1800&auto=format&fit=crop) |
| 7 | `--img-ch-06` *Analyst* | `images/sections/06.webp` | 4:5 — **1200 × 1500** | A dark-mode analytics screen filling the frame — several small multiples, plotted series, legible axis furniture but unreadable labels. The report at the end of the cycle. | [`photo-1551288049-bebda4e38f71`](https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=1800&auto=format&fit=crop) |
| 8 | `--img-manifesto` | `images/manifesto.webp` | 3:2 — **2000 × 1333** | A vertical stream of monospaced characters falling down a black field, shallow depth so the near columns bloom. Rendered at 6% opacity behind the manifesto statement, masked to the top-right corner — a texture the eye finds, never a background it reads through. | [`photo-1526374965328-7f61d4dc18c5`](https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?q=80&w=2000&auto=format&fit=crop) |
| 9 | `--img-archive` | `images/archive.webp` | 3:2 — **2000 × 1333** | Rows of nineteenth-century cabinet-card portraits standing on edge in a market tray, one card pulled forward and in focus. Warm, aged, shallow depth. The provenance hero: a physical archive, filed and retrievable. | [`photo-1461360370896-922624d12aa1`](https://images.unsplash.com/photo-1461360370896-922624d12aa1?q=80&w=2000&auto=format&fit=crop) |

### Not photographs

Three visual elements are generated in code and have no file. Do not
commission art for them.

| Element | Where | How it is made |
|---|---|---|
| Film grain | Every page, `.sx-grain` | An inline SVG `feTurbulence` data URI in `--sx-grain-src`, tiled at 200 × 200 and stepped four ways on a 620ms loop. Held at opacity `0.035`. |
| The seal | Index and archive, `<Seal />` | An SVG `<textPath>` on a circular path, rotating on a 26s linear loop. |
| The neural orb | Console and Dojo, `<Orb />` | Three counter-rotating CSS rings around a radial-gradient core, plus a 60-tick SVG dial. Its scale is driven from live microphone amplitude. |

---

## Generation prompts

For Midjourney, Flux, or any comparable model. Each prompt is written to
produce an **ungraded** plate — the CSS applies the desaturation and the
scrim. Append your model's own aspect flag (`--ar 16:9`, `--ar 4:5`, `--ar 3:2`).

**1 — Hero**
> Large-diaphragm condenser microphone suspended in a chrome shock mount, three-quarter view, unlit recording studio, subject positioned in the right third of the frame with the left two-thirds falling into near-black, single hard rim light raking across the grille, deep shadow, shallow depth of field, 85mm, cinematic, editorial product photography, no text, no people, no logos

**2 — Transcriptionist**
> Broadcast dynamic microphone on a counterweighted boom arm entering the frame from the top left, seamless charcoal backdrop, single hard key light from camera left with deep falloff to the right, matte black metal and foam windscreen, studio isolation, 50mm, high contrast, editorial product photography, no text, no people

**3 — Prosodist**
> Extreme close-up of a fine measurement grid on a laptop display, dense ruled lines with a single plotted trace crossing them, tick marks and unreadably small axis labels, shot slightly off-axis so the panel carries perspective, cool monochrome screen glow in a dark room, macro, no recognisable application interface, no readable text, no branding

**4 — Anatomist**
> Two pairs of hands annotating a printed document with pencils on a wooden table, seen from above at a slight angle, faces out of frame, one pencil tip resting on a specific line of text, soft directional daylight from a window, shallow depth of field, documentary editorial photography, no readable text, no faces

**5 — Playwright**
> Hands caught mid-gesture across a meeting table, an open laptop out of focus behind them, warm interior light, the moment of making a point, shallow depth of field, 50mm, candid documentary photography, faces cropped out of frame, no text, no logos

**6 — Coach**
> Directly overhead flat lay of a clean white desk: an open laptop, a desk telephone, a closed notebook with a pen, one cup of coffee, generous empty surface, strong top light casting hard short shadows, architectural symmetry, editorial flat lay, no text, no branding, no hands

**7 — Analyst**
> Dark-mode analytics dashboard filling the frame, four small-multiple charts with plotted line and bar series, legible axis furniture but unreadable labels, cyan and magenta data traces on near-black, screen photographed slightly off-axis with visible pixel structure, no recognisable product interface, no readable text

**8 — Manifesto ground**
> Vertical columns of monospaced characters falling down a pure black field, phosphor-green glow, near columns bloomed out of focus and far columns sharp, dense and continuous, no readable words, no faces, no objects, abstract data texture

**9 — Archive**
> Rows of nineteenth-century cabinet card portraits standing on edge in a wooden market tray, one card pulled forward and in sharp focus, aged sepia paper with foxed edges, warm low-angle daylight, shallow depth of field, 85mm, archival still life, no modern objects, no text

---

## Licensing

The Unsplash plates above are supplied under the
[Unsplash Licence](https://unsplash.com/license): free to use commercially, no
permission needed, attribution appreciated but not required. They are hotlinked
from the Unsplash CDN in the current build, which is fine for development and a
demo and is **not** what you want in production — download them, convert to
WebP or AVIF at the resolutions in the table, put them under
`web/public/images/`, and repoint the custom properties.

## Performance notes

- Prefer **AVIF with a WebP fallback**. At the grades used here (heavy
  desaturation, crushed blacks) AVIF holds up at very aggressive quality
  settings; 60–70 is usually indistinguishable from source.
- The hero plate is the only image above the fold. If you are serving locally,
  preload it: `<link rel="preload" as="image" href="/images/hero-bg.webp">`.
- The six chapter plates live inside the expanding accordion and are painted as
  CSS backgrounds on columns that start at `opacity: 0`. They are still fetched
  on load. If that matters on your connection budget, set them from the
  `data-open` state in JavaScript instead.
- Nothing here goes through `next/image`; the plates are CSS backgrounds, which
  is why they need no `remotePatterns` entry in `next.config.ts`.
