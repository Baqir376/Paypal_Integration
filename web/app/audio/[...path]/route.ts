/**
 * Recordings, proxied.
 *
 * This was a `rewrite` in next.config.ts, and rewrites are the wrong tool for
 * it twice over.
 *
 * The first reason is a landmine. Next evaluates `rewrites()` at BUILD time
 * and writes the result into the routes manifest, so `SALIX_API_URL` is
 * frozen at whatever it was when `next build` ran. In a container that is the
 * build stage, where it is unset — so the shipped image proxied audio to
 * `127.0.0.1:8000` inside the web container, where nothing listens. It fails
 * silently: the page loads, and the audio is simply never there.
 *
 * The second is that a rewrite cannot attach a header, and `/audio` now
 * requires the shared key or a signed URL — the recordings being the most
 * confidential thing in the system and, until recently, the only thing served
 * without a credential.
 *
 * Range requests are forwarded intact. An <audio> element seeks by asking for
 * byte ranges, and a proxy that answers every request with the whole file
 * turns scrubbing through an hour-long call into an hour-long download.
 */

const API = process.env.SALIX_API_URL ?? "http://127.0.0.1:8000";
const KEY = process.env.SALIX_API_KEY ?? "";

async function proxy(request: Request, path: string[], method: "GET" | "HEAD") {
  const incoming = new URL(request.url);
  const target = `${API}/audio/${path.map(encodeURIComponent).join("/")}${incoming.search}`;

  const headers = new Headers();
  if (KEY) headers.set("X-API-Key", KEY);
  // Seeking. Without this every scrub refetches the file from the beginning.
  const range = request.headers.get("range");
  if (range) headers.set("Range", range);
  // With accounts on, who is asking decides whether they get this recording.
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("Cookie", cookie);

  let upstream: Response;
  try {
    upstream = await fetch(target, { method, headers, redirect: "manual" });
  } catch {
    return new Response("Cannot reach the Salix API.", { status: 502 });
  }

  const out = new Headers(upstream.headers);
  out.delete("content-encoding");
  // Recordings are private; a shared cache must not keep one.
  out.set("Cache-Control", "private, max-age=3600");

  return new Response(method === "HEAD" ? null : upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: out,
  });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, ctx: Ctx) {
  return proxy(request, (await ctx.params).path, "GET");
}
export async function HEAD(request: Request, ctx: Ctx) {
  return proxy(request, (await ctx.params).path, "HEAD");
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
