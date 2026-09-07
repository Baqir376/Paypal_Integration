# syntax=docker/dockerfile:1.7
#
# The Salix web server, and the only container the internet reaches.
#
# It holds SALIX_API_KEY and attaches it to every /api call on the way to
# FastAPI, which is why the API container is never published.

# --------------------------------------------------------------------------
# 1. Dependencies
# --------------------------------------------------------------------------
FROM node:22-slim AS deps
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci

# --------------------------------------------------------------------------
# 2. Build
#
# The design vault is the reason this stage takes a secret. The protected
# stylesheets and set pieces are committed encrypted; without SALIX_DESIGN_KEY
# the build succeeds and ships the neutral fallbacks instead -- a working
# application that looks nothing like the real one. Pass the key with
#
#     docker build --secret id=design_key,env=SALIX_DESIGN_KEY ...
#
# so it is mounted for one RUN and never written to a layer. Baking it into an
# ENV or an ARG would put it in the image history for anyone who pulls it.
# --------------------------------------------------------------------------
FROM node:22-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY web/ ./

ENV NEXT_TELEMETRY_DISABLED=1 \
    SALIX_STANDALONE=1

RUN --mount=type=secret,id=design_key,required=false \
    SALIX_DESIGN_KEY="$(cat /run/secrets/design_key 2>/dev/null || true)" \
    npm run build \
    && if [ -s /run/secrets/design_key ]; then \
         echo "build: design vault unlocked"; \
       else \
         echo "build: WARNING no SALIX_DESIGN_KEY -- shipping neutral fallbacks"; \
       fi

# --------------------------------------------------------------------------
# 3. Runtime
# --------------------------------------------------------------------------
FROM node:22-slim AS runtime
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Standalone output: the server plus only the modules it actually traced.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
# There is no web/public: every asset in this build is inlined or generated,
# and Next omits the directory from standalone output when it does not exist.
# Add a COPY for it here if one is ever introduced.

# Not root. Nothing here needs to write to its own filesystem.
RUN useradd --system --uid 1001 salix && chown -R salix:salix /app
USER salix

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/ >/dev/null || exit 1

CMD ["node", "server.js"]
