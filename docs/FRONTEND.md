# The frontend

Salix's frontend is one piece of software with two registers. The index and the
archive are editorial — art-directed against black, locked out of the theme
toggle, composed to be read. The console, the calls, the playbook, the deals,
the report and the Dojo are a tool somebody has open all day, and they follow
the reader's light or dark preference.

What makes them one product rather than two is the chrome: the same telemetry
rail, the same floating status pill, the same grain and the same scroll engine
persist across every route and are never unmounted.

---

## Structure

```
web/
  app/
    layout.tsx          mounts the chrome; pins dark on the editorial routes
    globals.css         the product design system (tokens, panels, tables)
    effects.css         the older landing set pieces
    system.css          THE ART DIRECTION — loaded last, wins every collision
    page.tsx            Route 1 · the index
    archive/page.tsx    Route 4 · provenance
    (app)/
      console           the command centre
      calls, calls/[id] Route 3 · the specification page
      playbook, deals, report, upload, reps/[id]
      dojo/page.tsx     Route 2 · the voice console
  components/system/
    Chrome.tsx          mounts everything below, once, forever
    TelemetryRail.tsx   the fixed CRT bit stream
    StatusPill.tsx      the floating nav + live section readout
    Loader.tsx          the numeric preloader and dual curtain
    primitives.tsx      RevealWords, FadeWords, Parallax, Count, Seal, useProgress
    SvcCols.tsx         the horizontally expanding chapter accordion
    ChapterSlides.tsx   the pinned chapter slides
    HorizontalRun.tsx   the sideways-scrubbed chapter run
    Instruments.tsx     the orb, the waveform, diagnostics, the typewriter
    SiteFooter.tsx      shared by both editorial routes
  lib/
    motion.ts           the single scroll engine: GSAP + ScrollTrigger + Lenis
    lang.ts             direction, Urdu detection, speech languages and voices
```

## The three-file CSS cascade

`globals.css` → `effects.css` → `system.css`, in that order, in `layout.tsx`.
Precedence is stated by import order rather than fought out with selector
weight; when a rule in `system.css` collides with one in `globals.css`, the art
direction wins because it is later, and that is deliberate.

## Design tokens

`system.css` §1 declares the whole language. The three colours that carry every
screen, and nothing else is permitted:

| Token | Value | Role |
|---|---|---|
| `--accent-signal` | `#D4F55A` electric willow | the live, measured, now |
| `--accent-gold` | `#C7A15C` bark gold | provenance, seals, the archive |
| `--bg-primary` | `#08090A` obsidian | warm near-black, never blue-black |

Plus `--text-primary` … `--text-quaternary`, `--line` / `--line-strong` /
`--line-faint`, and the speaker duotone `--voice-rep` / `--voice-buyer` carried
through from the product so a waveform on the index means what it means inside
a call.

Easing is three curves and no more:

| Token | Curve | Used for |
|---|---|---|
| `--ease-luxury` | `cubic-bezier(0.75, 0, 0.25, 1)` | everything structural — curtains, pins, accordion columns |
| `--ease-expo` | `cubic-bezier(0.16, 1, 0.3, 1)` | everything that *arrives* |
| `--ease-out-quart` | `cubic-bezier(0.25, 1, 0.5, 1)` | tone changes |

The same two are registered with GSAP's `CustomEase` as `"luxury"` and
`"expo"`, and `luxury` is the library default, so a tween written without an
ease still matches the CSS.

`system.css` §1b remaps every one of those tokens for light, so the pill, the
rail and the diagnostics panel are one component with two palettes rather than
two components. The editorial routes are unaffected: they pin
`data-theme="dark"` before first paint, which both light selectors exclude.

## One clock

`lib/motion.ts` boots exactly one scroll engine per document, and everything
scroll-driven awaits the same promise.

Lenis is driven from `gsap.ticker`, not from its own `requestAnimationFrame`,
and `ScrollTrigger.update` is called from Lenis's scroll event with
`gsap.ticker.lagSmoothing(0)`. Two rAF loops reading and writing the same
scroll position is how a site ends up with pinned sections that shimmer by a
pixel every frame — the loops are never quite in phase, and the eye reads the
difference as jitter.

GSAP is imported dynamically. A reader on a phone with reduced motion enabled
never downloads a byte of it.

## Reduced motion

The resting state is the **finished** one, never a faster animation.

- Word reveals resolve to full opacity, no transform.
- Pinned slides unpin into stacked sections — and because `active` drives
  inline styles that a media query cannot override, `ChapterSlides` also sets
  every slide active in JavaScript. CSS alone would have left three quarters of
  that section invisible.
- The horizontal run becomes a draggable scroller.
- The accordion opens every column.
- The orb stops breathing, the grain stops drifting, the rail stops scanning.
- The preloader does not run at all.

## Language: Urdu, Roman Urdu and English

Salix is used on Pakistani sales floors, where one call routinely moves between
Urdu, Roman Urdu and English inside a single sentence. Three rules follow, and
they live in [`web/lib/lang.ts`](../web/lib/lang.ts).

**1. Direction is a property of each string, not of the document.**
Everything user- or model-authored carries `dir="auto"` — Dojo turns, the draft
box, transcript lines, cited quotes, play quotes, search results and the
command palette input. The browser decides from the first strong character, so
a rep's Urdu turn right-aligns while the buyer's English reply beside it does
not, with no mode to switch and nothing to detect. `[dir="auto"]:dir(rtl)` then
sets `text-align: right`, which is what stops the last line of an Urdu
paragraph hanging on the left — the single clearest tell that a product was
never tested in the language.

Roman Urdu deliberately stays LTR. It is Urdu vocabulary in Latin script, and
flipping it would be wrong.

**2. Two Urdu faces, chosen by job.**

| Face | Where | Why |
|---|---|---|
| Noto Naskh Arabic | end of `--font-sans`, `--font-mono`, `--font-display` | Horizontal and compact, so it sits inside a line box sized for Geist. Font stacks resolve per *character*, so Urdu inside an English paragraph picks it up with no class, no `lang`, and no detection. |
| Noto Nastaliq Urdu | `.urdu-prose`, applied only when `isRtl(text)` | The face Urdu is actually read in. It descends steeply and needs roughly double the leading, so it is opt-in — as a global fallback it would clip against every fixed-height control in the product. |

**3. Speech has to be told what language it is in.**
The Dojo carries a four-way language control (English · Pakistani accent /
اردو / Roman Urdu / English · British). It sets:

- `recognition.lang` — previously hardcoded `en-GB`, which meant an Urdu
  speaker's dictation came back as nonsense English and the rep blamed
  themselves.
- `utterance.lang` — previously never set at all, so Urdu script was handed to
  whatever the system default voice was.
- the voice itself, resolved through a fallback chain
  (`ur-PK → ur-IN → ur → hi-IN → ar-SA`).

`pickVoice` returns `null` rather than an arbitrary voice when nothing matches.
The utterance is tagged from the language of the *text*, not of the session,
because the offline twin answers in English even when the rep is speaking Urdu,
and an English sentence marked `ur-PK` is read as badly as the reverse.

### The voice ladder

Requiring every workstation to install an Urdu language pack is not a plan, and
neither Qwen TTS model speaks Urdu, so a voice has to come from somewhere else.
`lib/speech.ts` tries three routes in order and reports which one played:

| # | Route | When |
|---|---|---|
| 1 | **Local voice** via `speechSynthesis` | A voice matching the language is installed. Instant, offline, best quality. |
| 2 | **Network voice** via `GET /speech/tts` | Nothing local matches — in practice, always the Urdu case. |
| 3 | **Silence, stated** | The network voice is unreachable too. The rail reads `unavailable`; the session stays fully usable. |

Order matters: network-first would put a round trip in front of every English
line for nothing, and never going to the network leaves an Urdu session silent
on essentially every machine in the country.

`web/app/speech/tts/route.ts` is a Next route handler, deliberately **not**
under `/api` — that prefix is rewritten to FastAPI in `next.config.ts`, and this
is a frontend concern. It runs server-side because the upstream sends no CORS
headers and answers 404 without a browser user-agent.

It splits text on word boundaries at 180 characters (Urdu joins letterforms, so
a mid-word cut is audibly wrong), fetches the chunks sequentially, and
concatenates them. The chunks come back as bare MPEG frames at a constant
64 kbps / 24 kHz / mono with no ID3, so end-to-end joining produces one playable
stream — verified byte-for-byte against a direct upstream fetch.

Guards: empty text → 400, unlisted language → 400, over 1200 characters → 413,
upstream failure or timeout → 502, which the client treats as "no voice".

**The upstream is undocumented.** It is free, needs no key, and is the only
thing that speaks Urdu without asking a sales floor to install anything — but it
can be rate-limited or withdrawn. Every failure path degrades to route 3 rather
than throwing, and swapping providers is one file.

### Deployment note for Pakistan

Urdu speech is an operating-system capability, not a browser one.

- **Dictation** (`ur-PK`) needs Chrome or Edge. Firefox and Safari have no
  `SpeechRecognition` at all — the mic button disables itself and says so.
- **Playback needs nothing installed.** If a workstation happens to have the
  Urdu speech pack (Settings → Time & Language → add **اردو (پاکستان)** →
  Speech) the local voice is used and playback is instant and offline.
  Otherwise the network voice covers it automatically.
- **Neither Qwen TTS model supports Urdu** — `qwen3-tts-flash` covers ten
  languages and `qwen-audio-3.0-tts` sixteen, and Urdu is in neither list. A
  `DASHSCOPE_API_KEY` does not change the Urdu voice situation, which is why
  the network route exists.
- **Pace is calibrated per language.** Urdu needs ~14% more words to carry the
  same content, so words-per-minute is not comparable across languages; the
  band a call is judged against is derived from a parallel corpus that ships in
  `api/salix/metrics/pace_corpus.py`. The rep's language is detected from their
  own speech and travels on `CallMetrics.language`.
- **Question detection runs through one classifier** (`classify_sentence`) in
  every language, so `is_question` and `is_open_question` cannot disagree —
  they briefly did, and the invariant is now asserted over the whole corpus.
- The **measurement engine handles Urdu natively** (`api/salix/metrics/`).
  Urdu sentence boundaries (`۔` / `؟`), mid-sentence interrogatives, Urdu and
  Roman Urdu backchannels and discourse fillers are all detected. Run one
  identical call through the engine in both languages and every timing metric
  matches exactly; words-per-minute and filler *rate* differ only because Urdu
  uses a different number of words to say the same thing, which is a fact
  about the language rather than a measurement error.

## Accessibility notes

- Split text is `aria-hidden` per word and announced once from the wrapper, so
  a screen reader hears a sentence rather than a list of words.
- Every accordion column is a real `<button>` with `aria-expanded` and
  `aria-controls`, and focus does exactly what hover does. Content behind a
  pointer gesture is content a keyboard user does not have.
- The benchmark sliders on a call page are real `input[type=range]` elements
  with associated labels, so they arrive with keyboard control and the
  platform's own touch target.
- The telemetry rail is `aria-hidden` decoration and the grain is inert; the
  native cursor is used throughout, so pointer behaviour is the platform's.
- Verified: no horizontal overflow on any route at 390px, 768px or 1600px.

## Honest instruments

The orb and the waveform on the Dojo read the microphone through an
`AnalyserNode` and sit at zero when permission is refused or there is no input
device. The latency figure in the diagnostics rail is measured to the first
streamed token of the last turn. The typewriter on the buyer's reply runs
*behind* the SSE stream and never types a character the server has not sent.

An interface that animates over a dead signal is the interface lying about what
it knows — which is exactly the failure this product exists to catch in other
people.

## Images

Every plate is a CSS custom property, graded in CSS rather than in the file.
See [`ASSET-MANIFEST.md`](ASSET-MANIFEST.md) for the download table, the art
direction per slot, and generation prompts.

## Adding a section

Give it `data-status="LABEL"` and the floating pill's readout picks it up.
Nothing is registered from `StatusPill.tsx`, so no file needs editing but the
one you are writing.

## Still on disk, no longer wired up

`components/effects/` — `HoverCarousel`, `InteractiveDesk`, `Intro`,
`MaskReveal`, `ScratchReveal`, `ScrollHub`, `Slider3D`, `StackCards` — served
the previous index and are not imported by any current route. They are kept
because they are working components, not because anything uses them. The same
goes for the `.intro`, `.hero-stage` and `.hero-canvas` rules in `effects.css`.
Delete them when you are sure you do not want them back.
