# Deploying Salix on Alibaba Cloud

Salix runs locally with no cloud account at all. This is the path to a real
deployment on Alibaba Cloud with live Qwen inference.

---

## 1. Model Studio

Create an API key in the [Model Studio console](https://modelstudio.alibabacloud.com/).

```bash
DASHSCOPE_API_KEY=sk-...
DASHSCOPE_WORKSPACE_ID=llm-xxxxxxxx      # optional
SALIX_DASHSCOPE_REGION=ap-southeast-1
```

With a workspace id, requests go to your workspace-scoped host
(`https://{workspace}.{region}.maas.aliyuncs.com`). Without one they use the
shared international endpoint, which works with a plain key.

Confirm the key before deploying anything:

```bash
cd api
.venv/Scripts/python -c "
import asyncio
from salix.config import get_settings
from salix.providers import build_providers
p = build_providers(get_settings())
print('mode:', p.mode)
print(asyncio.run(p.llm.complete(system='Reply with OK.', user='ping')))
"
```

It should print `mode: live`.

---

## 2. Object Storage (required for real audio)

This is the step that is easy to miss. **Model Studio fetches the audio
itself**, so a local file path will never work in production — the service
needs a URL it can reach. Salix fails fast with that exact message rather than
letting you discover it through an opaque upstream 400.

Create a **private** OSS bucket in the same region as your Model Studio
workspace, then:

```bash
pip install oss2

SALIX_OSS_BUCKET=salix-recordings
SALIX_OSS_ENDPOINT=oss-ap-southeast-1.aliyuncs.com
SALIX_OSS_ACCESS_KEY_ID=...
SALIX_OSS_ACCESS_KEY_SECRET=...
SALIX_OSS_PREFIX=salix/audio
```

Uploads then go to OSS and the transcriber receives a **time-limited signed
URL**, so recordings are never world-readable. Keep the bucket private; Salix
does not need it public.

Use a RAM user scoped to `oss:PutObject` and `oss:GetObject` on that bucket
rather than an account-level key.

If you are only testing from a laptop, `SALIX_PUBLIC_BASE_URL` pointed at a
tunnel is an alternative — Salix will then hand out `{base}/audio/{file}` URLs
served by the API itself.

---

## 3. Database

SQLite is the default and is genuinely fine for a single-node deployment.

For ApsaraDB RDS for PostgreSQL:

```bash
pip install asyncpg
SALIX_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/salix
```

Tables are created on startup. To use pgvector for the moment index rather than
numpy, enable the extension and swap the implementation in
`salix/store/vectors.py` — that module is the seam, and nothing else changes:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE moments ALTER COLUMN embedding TYPE vector(1024);
CREATE INDEX ON moments USING hnsw (embedding vector_cosine_ops);
```

At the scale this product operates on (tens of thousands of moments) the numpy
path is not the bottleneck, so treat this as an optimisation rather than a
prerequisite.

---

## 4. Compute

### Option A — ECS (simplest, recommended)

One instance runs both processes behind nginx. `ecs.g7.large` (2 vCPU, 8 GB) is
comfortable; the workload is I/O-bound on model calls, not CPU-bound.

```bash
sudo apt update && sudo apt install -y python3.12-venv nodejs npm nginx

git clone <your-repo> /opt/salix && cd /opt/salix

# API
cd api
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd ..

# Frontend
cd web && npm ci && npm run build && cd ..

# Seed
api/.venv/bin/python -m seed.build --reset --report
```

`/etc/systemd/system/salix-api.service`:

```ini
[Unit]
Description=Salix API
After=network.target

[Service]
WorkingDirectory=/opt/salix/api
EnvironmentFile=/opt/salix/.env
ExecStart=/opt/salix/api/.venv/bin/uvicorn salix.app:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/salix-web.service`:

```ini
[Unit]
Description=Salix web
After=salix-api.service

[Service]
WorkingDirectory=/opt/salix/web
Environment=NODE_ENV=production
Environment=SALIX_API_URL=http://127.0.0.1:8000
ExecStart=/usr/bin/npm run start
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now salix-api salix-web
```

nginx. Two things here are load-bearing.

**Everything goes to Next, including `/api`.** It is tempting to send `/api/`
straight to FastAPI, and that was the earlier advice, but it is now wrong: the
shared key is attached by `web/app/api/[...path]/route.ts`, so a request that
skips Next arrives without one and the whole application answers 401. FastAPI
is not exposed to nginx at all.

**SSE must not be buffered**, or the live pipeline graph appears to hang and
then arrives all at once.

```nginx
server {
    listen 80;
    server_name salix.example.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Server-sent events: no buffering, no early close. The Dojo turn and
        # the upload pipeline are both streams.
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        chunked_transfer_encoding off;

        # A recording is large and slow to arrive on a sales floor's upstream.
        client_max_body_size 210M;
    }
}
```

Security group: open 80/443 only. Both application ports stay on localhost,
and only Next is reachable even from nginx.

**TLS is not optional here.** The Dojo uses the microphone through the Web
Speech API, and browsers refuse `getUserMedia` and `SpeechRecognition` on a
plain-HTTP origin that is not localhost. Deployed without a certificate, the
app loads and the voice half silently does nothing. `certbot --nginx` is
enough; `docs/DEPLOY.md` uses Caddy, which obtains one by itself.

### Option B — Function Compute

The API is a stateless ASGI app and deploys cleanly with Serverless Devs. Two
caveats specific to this workload:

- **File transcription is long-running.** A 40-minute recording can take
  minutes to transcribe. Either raise the function timeout or move
  `run_in_background` onto a queue rather than a background task.
- **SSE needs a streaming-capable trigger.** Without one, fall back to polling
  `GET /api/calls/{id}/timeline`, which returns the same events and is already
  implemented for exactly this reason.

The frontend builds to static output plus server components; hosting it on OSS
+ CDN with the API on Function Compute is a reasonable split.

---

## 5. Verify the deployment

```bash
curl https://salix.example.com/api/health
```

Expect `"provider_mode": "live"` and non-zero `calls`, `plays`, `moments`.

Then walk the path end to end:

1. Open `/upload`, drop a real recording in, and watch the DAG stream.
2. Open the resulting call: transcript, Helix, metrics, cited findings.
3. Open a struggling rep and generate a coaching plan; click a script line
   through to the colleague's call it came from.
4. Run a Dojo session and end it to get scored.
5. Generate the cycle report and print it.

---

## Cost

Rough per-call cost for a 30-minute two-speaker recording, live on Qwen:

| Stage | Model | Approx. |
|---|---|---|
| Transcription | `qwen-audio-3.0-asr-flash-filetrans` | per audio-minute |
| Anatomy | `qwen3.8-max` | ~8k in / ~3k out |
| Play extraction | `qwen3.8-max` | ~8k in / ~2k out |
| Moment embeddings | `text-embedding-v4` | ~5 short vectors |
| Coaching (per rep, not per call) | `qwen3.8-max` | ~6k in / ~4k out |

Two economies are built in: the deterministic metrics engine costs nothing at
all, and `qwen-plus` handles the cheaper passes. To cut further, point
`SALIX_MODEL_DEEP` at `qwen-plus` — the citation-enforcement loop means quality
degrades visibly (lower citation coverage) rather than silently.
