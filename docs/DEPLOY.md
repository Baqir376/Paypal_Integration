# Deploying Salix

One machine, three containers, a real certificate. Everything below has been
run end to end; the numbers in it are measured, not estimated.

If you are deploying on Alibaba Cloud specifically — Model Studio, OSS, RDS —
[`DEPLOY-ALIBABA.md`](DEPLOY-ALIBABA.md) covers those services in detail. This
document is the host-agnostic path and works on any VM that can run Docker.

---

## What you need

| | |
|---|---|
| A VM | 2 vCPU / 4 GB is comfortable. The work is I/O-bound on model calls, not CPU-bound. Any provider. |
| A domain | An A record pointing at the machine. **Not optional** — see below. |
| Docker | With the compose plugin. |
| A model key | Optional to start. Without one Salix runs its deterministic offline twins: everything works, but nothing is really being reasoned about. |

### Why the domain is not optional

The Dojo listens through the Web Speech API, and **every browser refuses
microphone access on a plain-HTTP origin that is not localhost.** Deployed on
a bare IP, Salix loads perfectly, looks finished, and the entire voice half
silently does nothing. Caddy obtains and renews a certificate by itself as
soon as the name resolves to the machine, so the only work is the DNS record.

---

## Deploy

```bash
git clone <your-repo> salix && cd salix
cp .env.example .env
```

Fill in three values:

```bash
# Generate one. Without it, every recorded call is readable by anyone who
# reaches the port.
SALIX_API_KEY=<python -c "import secrets; print(secrets.token_urlsafe(32))">

SALIX_DOMAIN=salix.example.com
SALIX_PUBLIC_BASE_URL=https://salix.example.com
```

If you have the design vault key, put it in `web/.design-key` before building —
the build reads it as a mounted secret and never writes it to a layer. Without
it the build still succeeds and ships the neutral fallbacks, so the app works
and looks like nothing in particular. `touch web/.design-key` if you do not
have one and want the build to proceed anyway.

```bash
docker compose up -d --build
docker compose exec api python -m seed.build --reset --report
```

Open `https://salix.example.com`.

The seed step is optional and populates ten scripted conversations through the
real pipeline, so the console has something in it. Skip it for an empty
instance that only shows what your own team uploads.

---

## Check it, rather than hoping

```bash
cd web && npm ci
SALIX_CHECK_URL=https://salix.example.com SALIX_API_KEY=<key> npm run check:production
```

Twenty-three checks in a real browser: every page, both languages, both neural
voices, the streaming Dojo turn, no console error, no failed request, the key
absent from every byte the browser is sent, and a recording not fetchable
without a credential. Then the three failures a live floor actually hits — API
down, key mismatch, rate limited — each asserted to say something *true*
rather than merely to be caught.

Expect `23/23`.

---

## How the pieces sit

```
      internet
         |  443
    +----v----+
    |  caddy  |  TLS, obtained automatically
    +----+----+
         |
    +----v----+
    |   web   |  Next. Holds SALIX_API_KEY and attaches it
    +----+----+  to every /api call on the way through.
         |
    +----v----+
    |   api   |  FastAPI. No published port at all.
    +---------+
```

**Only Caddy is published.** The API container has no port mapping, which is
half the reason the key is safe: even a mistyped firewall rule cannot expose
it, because there is nothing bound to expose.

**The key never reaches a browser.** The page calls `/api` on its own origin;
`web/app/api/[...path]/route.ts` attaches the key server-side. The network tab
of a deployed instance shows nothing that would let somebody call the API
directly, and `check:production` asserts exactly that.

A consequence worth knowing: **do not route `/api` around Next.** If a proxy
in front sends `/api/` straight to FastAPI, those requests arrive with no key
and the whole application answers 401.

---

## Going live on real inference

Out of the box the provider mode is `mock` — deterministic offline twins for
transcription, reasoning, embeddings and speech. The app is complete and
nothing is stubbed out, but the analysis is scripted rather than inferred.

Add a key and restart:

```bash
DASHSCOPE_API_KEY=sk-...
docker compose up -d
```

Then prove it, rather than reading the badge and hoping:

```bash
docker compose exec api python -m scripts.check_providers
```

One real call per capability, reported separately. A key that is present but
mistyped, out of quota, or issued for a different region looks exactly like a
working one in `.env` and fails much later, in the middle of a seven-stage
pipeline, wrapped in a stack trace about something else.

The sidebar badge changes from *offline mode* to live, and `/api/health`
reports which service is behind each capability rather than one badge for all
four. New Model Studio accounts get a free quota per model on the Singapore
endpoint the config already points at.

The reasoning layer speaks plain OpenAI protocol, so it can point anywhere —
Gemini, Groq, Cerebras, OpenRouter:

```bash
SALIX_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
SALIX_LLM_API_KEY=...
SALIX_LLM_MODEL_DEEP=gemini-3.1-flash-lite
```

Transcription, speech and embeddings are DashScope services with no standard
protocol; they stay on Model Studio or on the offline twins.

### Transcription, if you want uploads to work

Reasoning and embeddings can point anywhere. Diarized transcription cannot --
it has no standard protocol -- so it needs its own provider:

```bash
SALIX_DEEPGRAM_API_KEY=...
```

$200 of credit, no payment card, and Nova-3 covers Urdu with speaker
separation. It accepts the audio in the request body, so **none of the object
storage below is required for it**: no bucket, no public base URL, no signed
links. That machinery exists for Model Studio, which fetches the file itself.

Without a transcription provider the pipeline still runs, on a stand-in
conversation, and the upload page says so before anybody drops a file.

### The step that is easy to miss

**Model Studio fetches uploaded audio itself.** A local file path is not
something the service can open, so with a live key the recording needs a URL it
can reach. `SALIX_PUBLIC_BASE_URL=https://your-domain` is enough — the API
serves `/audio/{file}`, signed and expiring — or configure OSS and leave it
blank:

```bash
SALIX_OSS_BUCKET=salix-recordings
SALIX_OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com
SALIX_OSS_ACCESS_KEY_ID=...
SALIX_OSS_ACCESS_KEY_SECRET=...
```

Keep the bucket **private**. Objects are uploaded private and handed to the
transcriber as a time-limited signed URL, so recordings are never
world-readable. Salix fails fast with that exact message rather than letting
you discover it as an opaque upstream 400.

---

## Operating it

```bash
docker compose logs -f api          # the pipeline, per stage, with request ids
docker compose ps                   # health of all three
docker compose up -d --build        # redeploy
```

**The data is on a volume.** `salix-data` holds the SQLite file and the
recordings, and survives `down` then `up --build`. `docker compose down -v`
destroys it — that flag is the one to be careful with.

```bash
docker run --rm -v salix_salix-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/salix-backup.tar.gz /data
```

**Recordings are not public.** `/audio` needs the shared key, or a signed URL
that expires after 24 hours — which is what gets handed to Model Studio, since
it fetches the audio from its own servers and has no header of ours to send.
The filename is inside the signature, so one URL does not open the archive.

**A redeploy will not strand an upload.** Calls left mid-analysis when the
process stopped are closed at the next startup with a message saying the
recording is safe and to upload it again, rather than spinning forever.

**Request ids.** Every response carries `X-Request-Id`; a screenshot of a
browser console is enough to find the server side of the same request in the
log. A 500 returns that id and never a traceback.

**Rate limits** are per browser and per endpoint — 30 Dojo turns/min, 10
uploads/5 min, 5 reports/5 min. Counted against an opaque id the proxy stamps
rather than the address, because behind a proxy every request arrives from the
same address and the whole floor would otherwise share one allowance.

---

## Before this grows

Three things are sized for one machine. None is a reason not to ship; each is
a reason to know which one you are running.

**SQLite.** Fine for a single API process, and that is what the compose file
runs. Before a second writer:

```bash
SALIX_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/salix
```

`asyncpg` is already in the image. Tables are created on startup.

**Rate limiting is in-process.** Across replicas each counts its own, so it
becomes advisory and the real limit belongs in the proxy. Still worth leaving
on: what it actually prevents is one client's retry loop taking the site down.

**There are no user accounts.** Salix is single-tenant — one organisation, no
login, and the shared key is what stands between the internet and the data.
That is the right shape for a team deploying it for themselves, and the wrong
shape for signing up several companies to the same instance.
`api/salix/routers/deps.py` is where that seam opens.

---

## Files

| | |
|---|---|
| `docker-compose.yml` | The three services, the volume, the network isolation |
| `api/Dockerfile` | Python 3.12, `asyncpg` and `oss2` preinstalled |
| `web/Dockerfile` | Standalone Next build; takes the design key as a build secret |
| `Caddyfile` | TLS, SSE flushing, the 210MB upload ceiling |
| `web/scripts/production.mjs` | The 23 checks |
| `docs/RUNNING-IN-PRODUCTION.md` | The gate and the limits, in detail |
