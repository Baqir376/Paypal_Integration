# Running Salix in front of real people

Salix on a laptop and Salix on a sales floor are not the same deployment. This
is the difference, and how to check you have actually made it.

---

## The one thing that matters

**The API has no gate unless you give it one.** Without `SALIX_API_KEY`, every
recorded call, transcript, scorecard and coaching plan in the database is
readable by anyone who can reach the port. That is deliberate — a fresh clone
has to run with no setup — and it is why the process says so in its startup
log, once, at the top:

```
WARNING  No SALIX_API_KEY set: every call in this database is readable by
         anyone who can reach this port.
```

If you see that line and the port is not on your own machine, stop.

---

## Setting it

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set the result as `SALIX_API_KEY` in **both** environments — the API's and
Next's — and restart both. It is read once, at startup.

The browser never sees it. The page calls `/api` on its own origin;
`web/app/api/[...path]/route.ts` forwards each request to FastAPI and attaches
the key on the way through. That file exists because a `rewrite` cannot add a
header, which is the single thing needed here.

A healthy setup looks like this:

```
INFO  Salix API ready | providers=LIVE | db=postgresql | auth=key required | rate-limit=on
```

If the two halves disagree about the key, the app says so precisely — "the API
is running, but it rejected this request", with the variable to fix — rather
than telling you to restart a server that is working.

---

## What else is on

| | |
|---|---|
| `X-API-Key` / `Authorization: Bearer` | Constant-time compare. `/api/health`, `/api/ready`, `/docs` stay public. |
| Rate limits | 30 Dojo turns/min, 60 voice/min, 10 uploads/5min, 5 reports/5min, 600 default. Per browser and per endpoint. |
| `X-Request-Id` | On every response; echoed if supplied, so a trace started at the edge stays one trace. |
| 500 handler | `{"error", "detail", "request_id"}`. Never a traceback. |
| Upload ceiling | `SALIX_MAX_UPLOAD_MB` (200). An oversized upload is refused from its `Content-Length`, before the bytes are read. |
| Headers | `nosniff`, `DENY`, `no-referrer` from the API; those plus a `Permissions-Policy` allowing only the microphone from Next. |
| Recordings | `/audio` needs the key, or a signed URL that expires. See below. |
| Interrupted analysis | Calls left mid-pipeline by a restart are closed at startup instead of spinning forever. |

### Recordings

`/audio` is not under `/api`, so for a long time the shared key did not apply
to it: the most confidential thing in the system — somebody's actual sales
call — was the one thing served with no credential at all. Anyone holding a
filename could fetch it.

It could not simply be made to require the header. In live mode **Model Studio
fetches the audio itself**, from its own servers, with nothing of ours to
present; requiring a header would have closed the hole and broken
transcription in the same change.

So a recording is reachable two ways, and no others:

- **With the key.** Which is what the app does — the page requests `/audio/...`
  on its own origin and the proxy attaches it, exactly as with `/api`.
- **With a signed URL that expires.** `{base}/audio/{file}?expires=…&sig=…`,
  HMAC over the filename and the deadline, keyed by `SALIX_API_KEY`, good for
  24 hours. This is what gets handed to the transcriber. The filename is
  inside the signed message, so one URL is not a skeleton key for the archive,
  and moving the deadline invalidates the signature.

This is the same shape the OSS path already had, which hands out a
time-limited signed URL and keeps the bucket private.

Without a configured key there is nothing to sign with and `/audio` stays
open — consistent with the rest of the policy, and the startup log says so.

### Interrupted analysis

The pipeline runs as a background task inside the API process. When that
process goes away mid-run — a redeploy, an OOM, a power cut — nothing is left
to finish the call and nothing will ever set its status again. It stayed in
`transcribing` forever and the page showed a spinner that never resolved.

Shipping during working hours is a routine event, so this was not an edge
case; it happened every time. At startup, anything the database still believes
is in flight cannot be, because nothing has started yet: those calls are closed
with a message aimed at the person who will read it — the recording is safe,
upload it again — and the count is logged.

### Why rate limits are counted per browser

Next sits in front of the API, so by the time a request arrives the peer
address is always the proxy. Counting by it would give the whole sales floor
one shared allowance, and the second rep to open the Dojo would be refused
because of the first. The proxy stamps an opaque per-browser id
(`salix_client`, httpOnly, no personal data in it) and the limiter counts
against that.

All of it is spoofable, and that is fine: these are courtesy limits that stop
a stuck retry loop and an impatient finger. The key is what does access
control.

---

## Checking it, rather than hoping

```bash
cd web && npm run build
SALIX_API_KEY=<key> npx next start

# another terminal
SALIX_API_KEY=<key> npm run check:production
```

It must be the **production build**. Dev mode hides the three things this check
exists to catch: a key leaking into a client bundle, a route that only works
because of dev's forgiving proxy, and a hydration mismatch that dev logs as a
warning and production renders wrongly.

Twenty-three checks in two halves. That everything works — every page, both
languages, both neural voices, the streaming Dojo turn, no console error, no
failed request, the key absent from every byte the browser is sent, and a
recording not fetchable without a credential. Then that everything *fails*
well: API down, key mismatch, rate limited. Each is asserted not to be handled
but to say something true.

And the backend:

```bash
cd api && .venv/Scripts/python -m pytest -q     # 1439 tests
```

---

## Before more than one of anything

Two notices the startup log gives you, and what to do about them:

**SQLite.** Fine for one process. Set `SALIX_DATABASE_URL` to Postgres before a
second writer:

```
postgresql+asyncpg://user:pass@host:5432/salix
```

**Rate limiting is in-process.** Behind several replicas it becomes advisory,
because each replica counts its own. It is still worth leaving on — what it
actually prevents is one client's retry loop taking the demo down — but the
real limit belongs in the proxy at that point.

Neither is a reason not to ship. Both are a reason to know which one you are
running.

---

## The pieces

| | |
|---|---|
| `api/salix/middleware.py` | Auth, rate limiting, request ids, security headers |
| `api/salix/signing.py` | Signed, expiring URLs for recordings |
| `api/tests/test_production.py` | 51 tests over exactly that |
| `web/app/api/[...path]/route.ts` | The proxy that holds the key |
| `web/scripts/production.mjs` | The 23 checks above |
| `web/next.config.ts` | Headers, and the `/audio` rewrite that stays a rewrite |
