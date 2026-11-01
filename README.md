# Salix

**Sales conversation intelligence built on Alibaba Cloud Model Studio.**

Salix listens to every call a sales team runs, measures what actually happened
down to the millisecond, extracts the narrative moves that close deals, and
hands them to the reps who are missing quota — in their own colleagues' words,
with the recording to prove it.

At the end of the cycle it writes the report explaining why the number landed
where it did.

---

## PayPal AI Hackathon

**What is new since the submission period opened:** the credit paywall (PayPal Orders
through the APIMatic-generated SDK, and Braintree), Google sign-in with isolated teams,
automatic language detection, the deal score and coaching threshold, the closing test
roleplay, and AI failover. See [`docs/APIMATIC.md`](docs/APIMATIC.md) for how APIMatic's
SDK and Context Plugin were used.

**To see the purchase flow with no accounts at all,** follow the Quickstart with this in
`.env` at the repository root. Payments then run through the real SDK code against a
local stand-in that is clearly labelled as simulated:

```
SALIX_PAYPAL_SIMULATOR=true
```

**To run real sandbox payments,** add your own keys instead. The app uses them
automatically, with PayPal taking priority over Braintree:

```
SALIX_PAYPAL_CLIENT_ID=...          # PayPal Orders through the APIMatic SDK
SALIX_PAYPAL_CLIENT_SECRET=...
SALIX_BRAINTREE_MERCHANT_ID=...     # or Braintree
SALIX_BRAINTREE_PUBLIC_KEY=...
SALIX_BRAINTREE_PRIVATE_KEY=...
```

This was built in Pakistan, where PayPal does not open accounts, so the PayPal Orders
path has been tested against a stand-in at the HTTP layer rather than PayPal's live
sandbox. Braintree's sandbox accepts Pakistani applicants.

## Quickstart

You need **Python 3.11+** and **Node 20+**. Nothing else — no Docker, no
database server, and **no API key**. Salix runs end to end on deterministic
offline stand-ins for every model, so a fresh clone is fully demonstrable
offline and the test suite passes with no network.

```bash
git clone https://github.com/Baqir376/Paypal_Integration.git
cd Paypal_Integration
```

**1 — Install the backend.**

```bash
cd api
python -m venv .venv

.venv/Scripts/python -m pip install -r requirements-dev.txt     # Windows
# .venv/bin/python -m pip install -r requirements-dev.txt       # macOS / Linux
```

**2 — Run the test suite.** Still in `api/`:

```bash
.venv/Scripts/python -m pytest -q     # 1378 passed, 10 skipped
```

Everything below assumes `.venv/Scripts/python` on Windows; on macOS and Linux
that path is `.venv/bin/python` throughout.

**3 — Seed the database.** From the **repository root**, not `api/`:

```bash
api/.venv/Scripts/python -m seed.build --reset --report
```

This is not a fixture dump. Ten scripted sales conversations are pushed through
the *real* seven-stage pipeline — the same one an uploaded recording goes
through — which is why it takes a minute and why the playbook, the coaching
plans, the deal trajectories and the cycle report all come out consistent with
each other. It writes `api/salix.db`.

**4 — Start both servers**, in two terminals:

```bash
# terminal 1 — the API on :8000
cd api && .venv/Scripts/python -m uvicorn salix.app:app --reload

# terminal 2 — the interface on :3000
cd web && npm install && npm run dev
```

**5 — Open <http://localhost:3000>.**

### What works without a key, and what does not

The sidebar badge says **offline mode**, and `/api/health` names the provider
behind each of the four capabilities separately rather than showing one badge
for all of them — because they are not one switch.

| | Without a key | With a key |
|---|---|---|
| Every seeded call, scorecard, playbook, deal and report | real | real |
| The measurement engine — talk ratio, monologue, patience, interruptions, questions, pace, fillers | **real arithmetic either way**, no model involved | same |
| Search over conversational moments | stable, correctly shaped, unrelated results | genuinely semantic |
| Call anatomy, play extraction, coaching, the Dojo's replies | scripted stand-ins | a live model |
| **Uploading your own recording** | stored, never listened to; a stand-in conversation is analysed in its place, and the upload page says so before you drop a file | actually transcribed and diarized |

So the whole product is walkable with no key. Transcription is the one thing
that genuinely needs one.

### Adding keys (optional, and free)

```bash
cp .env.example .env
```

Two lines make it fully live. Both providers are free and neither asks for a
payment card:

```bash
# Reasoning + embeddings — https://aistudio.google.com/apikey
SALIX_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
SALIX_LLM_API_KEY=...
SALIX_LLM_MODEL_DEEP=gemini-3.1-flash-lite
SALIX_LLM_MODEL_FAST=gemini-3.1-flash-lite
SALIX_LLM_MODEL_EMBEDDING=gemini-embedding-001
SALIX_EMBEDDING_DIM=1536

# Transcription with speaker separation — https://console.deepgram.com
SALIX_DEEPGRAM_API_KEY=...
```

Use `gemini-3.1-flash-lite`, not `flash`. Measured on a real free account,
`gemini-3.5-flash` allows twenty requests **per day**, which does not survive a
single seed run.

Then confirm the keys actually work before wondering why a badge has not
changed — configured is not the same as working, and a mistyped key, an
exhausted quota and a region mismatch all look identical in a `.env` file:

```bash
cd api && .venv/Scripts/python -m scripts.check_providers
```

Restart the API and re-seed. `SALIX_PROVIDER_MODE=mock` forces the offline
twins back on at any time, which is also how the test suite stays hermetic.

### Uploading a real call

`/upload` takes `.mp3`, `.wav`, `.m4a` or `.ogg` up to 200 MB, in **English**
or **Roman Urdu**. Pick the language on the upload form; an Urdu recording is
transcribed and then transliterated into Latin script, so the transcript,
the scorecard and the coaching all read in Roman Urdu and never in Nastaliq or
Devanagari.

[`docs/RECORDING-SCRIPTS.md`](docs/RECORDING-SCRIPTS.md) has four calls to read
aloud into a phone — an English pair and a Roman Urdu pair, each a discovery
call that stalls and the follow-up that closes it. They are written so the
objections, the pauses and the interruptions are known in advance, which is
what makes it possible to check whether the analysis is right rather than just
plausible.

### Setting up your keys

```
python api/scripts/setup_credentials.py          # walks through each key, hidden input
python api/scripts/setup_credentials.py --check  # one real request each; no money moves
```

### When the model refuses

Free tiers answer 429 and 503 under load. `SALIX_LLM_FALLBACK_MODELS` lists other
models on the same key to try in order, and `SALIX_LLM_BACKUP_*` adds another provider.
If everything fails, the error surfaces and the pipeline degrades; it never invents
an answer.

### Accounts

With Google configured, everyone signs in and each team sees only its own data. With
it unset there are no accounts, so a fresh clone still runs.

Create an OAuth client of type "Web application" at
[console.cloud.google.com](https://console.cloud.google.com/apis/credentials), add
`<SALIX_APP_URL>/api/auth/google/callback` as a redirect URI, and set:

```
SALIX_GOOGLE_CLIENT_ID=...
SALIX_GOOGLE_CLIENT_SECRET=...
SALIX_OWNER_EMAIL=you@company.com   # claims the data already in the database
```

The first sign-in creates a team. Owners invite colleagues from the Team page; no
email is sent, so tell them to sign in with the invited address.

### The workflow

Upload, analysis, skill score and deal score. A deal score under
`SALIX_COACHING_THRESHOLD` (75 by default) writes a coaching plan about that call's
weakest skills, and "Test me on this plan" starts a closing test: a roleplay against
a buyer who only commits once the rep has shown those skills. The verdict has to
quote what was actually said.

### Testing beyond the unit tests

```
cd api && pytest                               # includes Schemathesis fuzzing
python -m uvicorn tests.e2e_server:app --port 8010   # Google and PayPal faked at the edge
cd web && node scripts/full_flow.mjs           # two companies, sign-in to closing test
node scripts/scroll_check.mjs                  # real wheel events on every scroll box
node scripts/deep_crawl.mjs                    # presses everything, plus axe-core
python api/scripts/eval_natural_audio.py --fetch   # real speech; costs credit
python api/scripts/eval_core_flow.py           # real model; costs credit
python web/scripts/agent_explore.py            # browser-use AI tester; costs credit
```

### Credits and PayPal

Each recording costs one credit, bought through PayPal Checkout. A failed
analysis returns its credit. With no PayPal credentials the paywall is off, so a
fresh clone still runs end to end.

To turn it on, create a REST app at
[developer.paypal.com](https://developer.paypal.com/dashboard/applications/sandbox)
and put its sandbox credentials in `.env`:

```
SALIX_PAYPAL_CLIENT_ID=...
SALIX_PAYPAL_CLIENT_SECRET=...
SALIX_PAYPAL_ENVIRONMENT=sandbox
SALIX_APP_URL=http://localhost:3000
```

Salix calls PayPal only through
[`paypal-server-sdk`](https://github.com/paypal/PayPal-Python-Server-SDK), which is
generated by APIMatic, and only from `api/salix/billing/paypal.py`. APIMatic has
no runtime key. Its
[Context Plugin](https://github.com/apimatic/context-matic) gives a coding agent
accurate context on that SDK, and is installed in Claude Code with:

```
/plugin marketplace add apimatic/context-matic
/plugin install context-matic@apimatic-context-matic
```

**Three ways to take payment, first match wins.** PayPal Orders through the APIMatic
SDK (`SALIX_PAYPAL_CLIENT_ID`), Braintree (`SALIX_BRAINTREE_*`), or the simulator below.
Braintree is PayPal's gateway and its sandbox needs no PayPal account: apply at
[apply.braintreegateway.com](https://apply.braintreegateway.com/signup/sandbox).

No PayPal account? PayPal does not open accounts in every country, Pakistan included.
`SALIX_PAYPAL_SIMULATOR=true` runs the flow through the same SDK code against a local,
clearly labelled stand-in. Credits are free and nothing reaches PayPal, so it shows this
app's side of the integration and not that PayPal accepts it. Real keys replace it.

Known gaps before taking real money:

- There are no webhooks. A refund or chargeback issued in PayPal does not take
  credits back, and a `pending` payment is only rechecked when the Credits page
  is opened.
- Credits belong to the one organisation this build has. See
  [Putting it in front of real people](#putting-it-in-front-of-real-people).

### The Dojo

`/dojo` is live practice against a buyer persona rather than a recording: you
speak, it answers in a neural voice, and the same metrics engine scores the
conversation afterwards — so practice and real calls are measured on one scale.
It needs microphone permission, which browsers grant on `localhost` and on
`https://`, but **not** on a plain `http://` address other than localhost.

---

## The problem

Your top performer and your struggling rep make the same number of calls. The
difference is what happens inside them, and nobody has time to listen to four
hundred hours of recordings to find out what.

Existing conversation-intelligence tools will tell you that a rep talks too
much. That is true and nearly useless. What changes behaviour is hearing the
exact sentence a colleague used to turn the exact objection that keeps beating
you.

Salix is built around that one idea.

---

## What makes it different

**1. Measurement is arithmetic, not inference.**
Talk ratio, longest monologue, patience, interruptions, question rate, pace and
filler density are computed in Python from diarized millisecond timestamps. No
language model is consulted. Every number a sales manager sees can be
recomputed by hand from the transcript — and is, in 163 unit tests against
hand-computed fixtures.

The engine measures **English, Urdu and Roman Urdu** identically. That is not a
translation layer: Urdu ends a sentence with `۔` and asks with `؟`, and it is
subject-object-verb, so the interrogative lands mid-sentence rather than
opening it. An engine that assumes English does not return slightly worse
numbers on an Urdu call — it returns *zero questions*, and then scores the rep
as though they never asked one. Run the same call through the engine in both
languages and every timing metric matches exactly.

Pace is the one metric that cannot simply be shared, because words per minute
is not comparable between languages -- Urdu needs about a seventh more words to
carry the same content. Its band is therefore derived from a parallel corpus
that ships in the repository rather than from a published figure, so the number
can be recomputed and moves if the corpus is replaced with real call
transcripts. See [`api/salix/metrics/pace_corpus.py`](api/salix/metrics/pace_corpus.py)
and [`api/tests/test_metrics_urdu.py`](api/tests/test_metrics_urdu.py).

The subtleties matter: overlapping speech is unioned rather than summed so
ratios stay coherent; a two-word "mm-hmm" from the buyer does not end the rep's
monologue; interruptions are excluded from the patience mean rather than
dragging it to zero.

**2. Nothing is asserted without its evidence.**
Every finding the language model produces must cite the transcript segments it
came from. The pipeline hydrates those citations against the real transcript; a
segment id that does not exist is treated as a fabrication and the agent is
asked again with the list of ids it may actually use. A citation that still
cannot be resolved is removed rather than displayed.

**3. The playbook converges.**
A team of five reps generates hundreds of play candidates that are mostly the
same handful of moves rediscovered. Candidates are embedded on their
*structure* — kind, thesis, trigger, beats — and a near-match becomes another
instance of an existing play rather than a near-duplicate entry. The library
converges on a dozen named moves instead of sprawling.

**4. Coaching is retrieval, not advice.**
For each axis where a rep trails the team, Salix searches the moment index for
how a colleague *who won* handled the same situation, filtered to exclude the
rep's own habits, diversified with MMR. The generated script is written from
those passages, and every line traces back to a real call — clickable, with the
colleague's name on it.

**5. The Dojo.**
A rep practises by voice against a buyer persona assembled from the objections
that actually killed their own deals, weighted by how badly each was handled. A
live coach rail fires on measurable conditions. The session is scored by the
same metrics engine that scores real recordings, so practice and reality are
comparable.

---

## Providers

| Capability | Model / service |
|---|---|
| File transcription with speaker diarization | `qwen-audio-3.0-asr-flash-filetrans` |
| Call anatomy, play extraction, coaching, reporting | `qwen3.8-max` |
| High-volume / low-latency passes | `qwen-plus` |
| Semantic retrieval over conversational moments | `text-embedding-v4` |
| Dojo buyer voice | `qwen3-tts-instruct-flash` |
| Realtime ASR (Dojo, optional path) | `fun-asr-realtime` |

All text and embedding calls go through the OpenAI-compatible Model Studio
endpoint; file transcription uses the native async DashScope task API
(`X-DashScope-Async: enable`, submit → poll → fetch).

Because that reasoning path is plain OpenAI protocol, it is not welded to one
vendor, and the running demo is proof of it — the instance these screenshots
come from points the reasoning and embedding layers at **Gemini** and
transcription at **Deepgram**, chosen for one practical reason: Model Studio
requires a payment card for identity verification even to spend its free
quota, and neither of those does. `/api/health` names the provider behind each
capability, so what is actually live is never a matter of belief.

| Capability | Model Studio | The free-without-a-card path |
|---|---|---|
| Transcription + diarization | `qwen-audio-3.0-asr-flash-filetrans` | Deepgram Nova-3 |
| Reasoning | `qwen3.8-max` / `qwen-plus` | `gemini-3.1-flash-lite` |
| Embeddings | `text-embedding-v4` | `gemini-embedding-001` |
| Dojo voice | `qwen3-tts-instruct-flash` | Edge neural TTS |

---

## Architecture

```
Browser ── Next.js 15 ──┬── REST            ┌──────────────────────────────┐
                        ├── SSE (pipeline)  │      Analysis DAG            │
                        └── SSE (dojo turn) │                              │
                                  │         │  Transcriptionist            │
                            FastAPI ────────┤        ↓                     │
                                  │         │    Prosodist  (no LLM)       │
                                  │         │        ↓                     │
                                  │         │    Anatomist                 │
                                  │         │        ↓                     │
                                  │         │    Playwright ── moments ──┐ │
                                  │         │        ↓                   │ │
                                  │         │     Analyst                │ │
                                  │         └────────────────────────────┼─┘
                                  │                                      │
                    ┌─────────────┴──────────────┐          Coach ◄──────┘
                    │                            │       (RAG retrieval)
              SQLite / Postgres            Object storage
              + vector index                (OSS in cloud)
```

Full detail, including the degradation rules and why each mapping was chosen:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Running it

Installing, seeding, starting both servers and adding provider keys are in
[Quickstart](#quickstart) at the top. Two things beyond that are worth their
own section: serving this to other people, and putting it on the internet.

### Where each capability can point

The reasoning layer speaks plain OpenAI protocol, so it runs on Model Studio,
Gemini, Groq, Cerebras or OpenRouter without a code change — set
`SALIX_LLM_BASE_URL` and the model names. Embeddings are portable the same way,
which is what turns retrieval from stable-but-unrelated into genuinely
semantic.

**Transcription is the one thing that is not portable.** Separating two
speakers on a recording has no standard protocol, so it needs a provider that
offers it — `SALIX_DEEPGRAM_API_KEY`. Deepgram takes the audio in the request
body rather than fetching it, so no public URL, object storage or signed link
is needed, which is what lets a laptop transcribe a real call. Without it an
upload is stored and never listened to, a stand-in conversation is analysed in
its place, and the upload page says so before anybody drops a file.

`/api/health` reports which service is behind each capability rather than
showing one badge for all four, and `scripts.check_providers` calls each one
once — because a mistyped key, an exhausted free quota and a region mismatch
all look identical in a `.env` file.


### Putting it in front of real people

Everything above runs Salix on a laptop, where the API is open by design so a
fresh clone works with no setup. The moment the port is reachable by anything
else, that openness means every recorded call in the database is readable by
anyone who finds it. Two settings close that.

```bash
# One key, the same value for both processes.
python -c "import secrets; print(secrets.token_urlsafe(32))"

SALIX_API_KEY=<that value>
SALIX_RATE_LIMIT_ENABLED=true   # the default
```

The browser never sees the key. The page calls `/api` on its own origin and
`web/app/api/[...path]/route.ts` attaches the key server-side on the way
through — so the network tab of a deployed instance shows nothing that would
let somebody call the API directly. Set the same value in the API's environment
and in Next's, and restart both; the key is read once, at startup.

Then run it as it will actually run, and check it:

```bash
cd web && npm run build
SALIX_API_KEY=<key> npx next start        # SALIX_API_URL if the API is not on :8000

# in another terminal
SALIX_API_KEY=<key> npm run check:production
```

`check:production` drives the production build in a real browser: every page in
both languages, both neural voices, the streaming Dojo turn, and — the half
that matters more — the three failures a live floor actually hits. It asserts
not that they are handled but that each one says something *true*, because an
error screen that confidently tells an operator to restart a healthy API is
worse than no screen at all.

What the API does once a key is set:

| | |
|---|---|
| **Auth** | `X-API-Key` or `Authorization: Bearer`, compared in constant time. `/api/health`, `/api/ready`, `/docs` stay open — a probe that needs a secret just puts the secret in the probe config. |
| **Rate limits** | Per browser, per endpoint: 30 Dojo turns/min, 10 uploads/5min, 5 reports/5min. Counted against a per-browser id the proxy stamps, not the address — otherwise the whole floor shares one allowance and the second rep to open the Dojo is refused because of the first. |
| **Request ids** | `X-Request-Id` on every response, echoed if you supply one. A screenshot of a browser console is enough to find the server side of the same request. |
| **Failures** | 500s return `{"error", "detail", "request_id"}` and never a traceback. The traceback is in the log against that id. |

Two things the startup log will tell you, once, where somebody about to expose
a port will see them: that no key is set, and that SQLite is fine for one
process but wants Postgres before a second writer.

### Putting it on the internet

```bash
cp .env.example .env      # SALIX_API_KEY, SALIX_DOMAIN, SALIX_PUBLIC_BASE_URL
docker compose up -d --build
docker compose exec api python -m seed.build --reset --report
```

Three containers: Caddy terminates TLS and is the only one published, Next
holds the key, and FastAPI has no port mapping at all. A certificate is
obtained automatically for `SALIX_DOMAIN`, which matters more than it sounds —
browsers refuse microphone access on plain HTTP, so an `http://` deployment
loads perfectly and the Dojo silently cannot listen.

[`docs/DEPLOY.md`](docs/DEPLOY.md) is the whole path;
[`docs/DEPLOY-ALIBABA.md`](docs/DEPLOY-ALIBABA.md) covers Model Studio, OSS and
RDS specifically.

---

## Repository layout

```
api/
  salix/
    schemas/      Pydantic contract — the single source of truth
    metrics/      deterministic engine + benchmarks + cross-call analytics
    providers/    Alibaba Cloud clients and their offline twins
    agents/       the six specialists, plus citation enforcement
    pipeline/     DAG orchestrator and the SSE event bus
    dojo/         persona construction and the turn engine
    store/        tables, typed repository, vector search
    routers/      HTTP surface
  scripts/
    gen_types.py  compiles the Pydantic contract into web/lib/types.ts
  tests/          1388 tests
seed/             the corpus: cast, scripts, and the build pipeline
web/
  app/            index, archive, console, calls, reps, playbook, deals,
                  dojo, report -- plus system.css, the art direction
  components/
    system/       the persistent chrome: telemetry rail, status pill, cursor,
                  scroll-driven primitives, the Dojo instruments
    helix/        the Helix
    effects/      the earlier landing set pieces (no longer routed)
  lib/            API client, the scroll engine, formatting, generated types
docs/
  ARCHITECTURE.md            the backend DAG and its degradation rules
  FRONTEND.md                the design system, the scroll engine, accessibility
  ASSET-MANIFEST.md          every image slot, its art direction and its source
  DEPLOY.md                  one machine, three containers, a real certificate
  RUNNING-IN-PRODUCTION.md   the gate, the limits, and how to check them
  PROTECTING-THE-FRONTEND.md the design vault
  RECORDING-SCRIPTS.md       four calls to read aloud and upload
  DEPLOY-ALIBABA.md
```

---

## Type safety across the boundary

`api/scripts/gen_types.py` compiles the Pydantic models into
`web/lib/types.ts`. Nothing in the frontend declares its own shape for a
backend object, so renaming a field in Python breaks `npm run typecheck`
instead of breaking a page at runtime.

```bash
api/.venv/Scripts/python api/scripts/gen_types.py
cd web && npx tsc --noEmit
```

---

## Not shipping errors

- **Offline mode.** Every provider has a deterministic twin. No key, no
  network, still a complete product.
- **Per-stage degradation.** If play extraction fails, the call keeps its
  transcript, metrics and anatomy. Only transcription is fatal, because
  without it there is nothing to analyse.
- **Repair loops.** Structured output that fails validation is returned to the
  model *with the validator's complaint*; citations that name nonexistent
  segments are returned with the list of legal ids.
- **Typed end to end**, and 1388 tests covering the metrics engine against
  hand-computed fixtures, Urdu and Roman Urdu question and backchannel
  detection, vector search, persistence round-trips, the full DAG, and every
  HTTP endpoint against a really-seeded database.

---

## The seed corpus

Ten conversations across five reps, written so every capability has something
real to bite on and so the numbers tell the truth:

| Call | Rep | Outcome | Designed to show |
|---|---|---|---|
| Northwind discovery | Zara | won | Textbook discovery; the Compounding Cost story |
| Northwind pricing | Zara | won | A price objection turned; multithreaded close |
| Kestrel discovery | Zara | open | The Smoke Alarm reframe |
| Halcyon demo | Bilal | lost | An unbroken **3m 15s** feature monologue at 86% talk ratio |
| Halcyon pricing | Bilal | lost | Price objection met with a discount reflex |
| Brightline scoping | Bilal | open | Improving, but the next step is one-sided |
| Orbit expansion | Daniyal | won | Competent; a proof point lands |
| Tanner evaluation | Daniyal | lost | Incumbent objection raised twice, never resolved |
| Vantage discovery | Fatima | open | Outstanding discovery, no close at all |
| Cobalt intro | Hina | open | Newer rep, good instincts, thin qualification |

A test asserts that the designated top performer measures best and the
struggling rep measures worst. If an edit to the corpus ever inverted that, the
suite fails rather than the demo quietly telling the opposite of the truth.

---

## Licence

MIT. See [`LICENSE`](LICENSE).
