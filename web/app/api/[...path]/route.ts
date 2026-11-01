/**
 * The API proxy.
 *
 * Every /api call from the browser lands here and is forwarded to FastAPI with
 * the shared key attached. The point is that the key is attached *on the
 * server*: it lives in the Next process's environment and never reaches the
 * page, so opening devtools on a deployed instance reveals nothing that would
 * let someone call the API directly.
 *
 * This replaces the `rewrites` entry that used to do the forwarding. A rewrite
 * cannot add a header, which is the one thing needed here.
 *
 * Streaming is the reason this is written by hand rather than with a helper.
 * Two endpoints are server-sent events — the pipeline watching an upload, and
 * the Dojo turn — and both are useless if buffered: the whole point is that
 * stages and tokens arrive as they happen. `response.body` is passed straight
 * through, and the caching and buffering headers that would defeat it are set
 * explicitly.
 */

const API = process.env.SALIX_API_URL ?? "http://127.0.0.1:8000";
const KEY = process.env.SALIX_API_KEY ?? "";

/** Hop-by-hop headers, and ones the fetch layer must set for itself. */
const STRIP = new Set([
  "host",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "content-length",
  "accept-encoding",
]);

/** The cookie that tells the API's rate limiter one browser from another. */
const CLIENT_COOKIE = "salix_client";

function readClientId(request: Request): string | null {
  const jar = request.headers.get("cookie");
  if (!jar) return null;
  for (const pair of jar.split(";")) {
    const [name, ...rest] = pair.trim().split("=");
    if (name === CLIENT_COOKIE) {
      const value = rest.join("=").trim();
      // Only what this route mints: hex, bounded. Anything else is ignored
      // rather than forwarded, so the header cannot be used to inject.
      if (/^[a-f0-9]{16,32}$/.test(value)) return value;
    }
  }
  return null;
}

function forwardHeaders(request: Request, clientId: string): Headers {
  const headers = new Headers();
  request.headers.forEach((value, name) => {
    if (!STRIP.has(name.toLowerCase())) headers.set(name, value);
  });
  if (KEY) headers.set("X-API-Key", KEY);

  // Without this the API sees only this server's address and gives the whole
  // team one shared rate-limit allowance -- the second rep to open the Dojo
  // would be refused because of the first.
  headers.set("X-Salix-Client", clientId);
  return headers;
}

async function proxy(request: Request, path: string[]): Promise<Response> {
  const incoming = new URL(request.url);
  const target = `${API}/api/${path.join("/")}${incoming.search}`;

  const existing = readClientId(request);
  const clientId = existing ?? crypto.randomUUID().replace(/-/g, "").slice(0, 24);

  const init: RequestInit & { duplex?: string } = {
    method: request.method,
    headers: forwardHeaders(request, clientId),
    // Never follow a redirect on the API's behalf; the client decides.
    redirect: "manual",
    // The cookie is forwarded by hand above. Left on its default, fetch handles a 401
    // to a request with a streamed body itself, and fails with "expected non-null body
    // source": every POST from a signed-out browser became a 502 "API unreachable",
    // and a session expiring mid-upload never reached the login page.
    credentials: "omit",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    // Required by undici when streaming a request body.
    init.duplex = "half";
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    // The API is down or unreachable. The client already knows how to render
    // this shape — see lib/api.ts — so it degrades rather than blanking.
    return Response.json(
      {
        error: "api_unreachable",
        detail: "Cannot reach the Salix API. Is the backend running?",
        retryable: true,
      },
      { status: 502 },
    );
  }

  const headers = new Headers(upstream.headers);
  headers.delete("content-encoding");
  headers.delete("content-length");

  if (headers.get("content-type")?.includes("text/event-stream")) {
    // Anything that might hold bytes back defeats the stream.
    headers.set("Cache-Control", "no-cache, no-transform");
    headers.set("Connection", "keep-alive");
    headers.set("X-Accel-Buffering", "no");
  }

  if (!existing) {
    // httpOnly so the page cannot read it, and no personal data in it: this is
    // an opaque counter key, not a session or an identity.
    headers.append(
      "Set-Cookie",
      `${CLIENT_COOKIE}=${clientId}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax`,
    );
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function POST(request: Request, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function PUT(request: Request, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function PATCH(request: Request, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}
export async function DELETE(request: Request, ctx: Ctx) {
  return proxy(request, (await ctx.params).path);
}

/** SSE and uploads must not be collapsed into a cached static response. */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
