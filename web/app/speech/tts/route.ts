/**
 * Network speech synthesis, for the languages the machine cannot speak.
 *
 * Why this exists at all:
 *
 *   - Windows ships no Urdu voice unless somebody installs the language pack,
 *     and on a shared sales floor nobody will.
 *   - Neither `qwen3-tts-flash` nor `qwen-audio-3.0-tts` supports Urdu, so the
 *     project's own cloud TTS cannot cover it even with a key configured.
 *
 * So the browser is given an audio URL instead of a voice. This runs on the
 * Next server rather than in the page because the upstream sends no CORS
 * headers and rejects requests without a browser user-agent — both of which
 * are fine to handle server-side and impossible to handle in a fetch from the
 * page.
 *
 * It deliberately does NOT live under /api: that prefix belongs to the proxy
 * in app/api/[...path]/route.ts, and this is a frontend concern.
 *
 * Two upstreams, tried in order:
 *
 *   1. The API's own /api/dojo/voice, which renders through Microsoft's
 *      neural voices — `ur-PK-UzmaNeural` for Urdu script, Indian English for
 *      Roman Urdu, because there is no en-PK voice and an Urdu voice handed
 *      Latin letters reads them as badly spelled English. No key, and the
 *      quality is a different category from the fallback.
 *   2. A translation endpoint's read-aloud, which is robotic but has never
 *      needed a key either.
 *
 * Both are undocumented endpoints belonging to somebody else's product. They
 * are free and they work, but either can be rate-limited or withdrawn, which
 * is exactly why there are two and why every failure path returns a status the
 * client can fall back from rather than an exception.
 */

/** Where the API lives. Same origin the /api proxy forwards to. */
const API_ORIGIN = process.env.SALIX_API_URL ?? "http://127.0.0.1:8000";

/** Attached server-side, exactly as the /api proxy does. Never sent to the page. */
const API_KEY = process.env.SALIX_API_KEY ?? "";

/**
 * A ceiling on this route specifically.
 *
 * Everything under /api is limited by the FastAPI middleware, but this route
 * is served by Next and reaches two third-party endpoints, so without a limit
 * of its own it is an open audio proxy that anyone who finds the URL can point
 * at somebody else's rate limit until it is withdrawn. A session speaks a few
 * lines a minute; 90 is generous for a person and useless for a scraper.
 */
const RATE = { requests: 90, windowMs: 60_000 };
const hits = new Map<string, number[]>();

function overRate(request: Request): boolean {
  const who =
    request.headers.get("x-forwarded-for")?.split(",")[0].trim() ?? "local";
  const now = Date.now();
  const recent = (hits.get(who) ?? []).filter((t) => now - t < RATE.windowMs);
  recent.push(now);
  hits.set(who, recent);

  // The map is per-process and would otherwise grow for the life of the
  // server; addresses that have gone quiet are dropped.
  if (hits.size > 2048) {
    for (const [key, times] of hits) {
      if (times.every((t) => now - t >= RATE.windowMs)) hits.delete(key);
    }
  }
  return recent.length > RATE.requests;
}

/** The fallback upstream caps a request at roughly 200 characters. */
const CHUNK = 180;

/** Only languages the product actually offers, so this cannot be used as an
    open audio proxy. */
const ALLOWED = new Set(["en", "ur-roman", "ur"]);

/**
 * What the older upstream should be told, when the neural voice is unreachable.
 *
 * Roman Urdu must NOT be sent as "ur" here. That upstream reads the value as
 * the script to expect, and handed Latin letters under `ur` it either refuses
 * or spells them out. English is the right fallback for the same reason
 * `en-IN-NeerjaNeural` is the right neural voice: these are Latin characters,
 * and an English engine at least pronounces them.
 */
const FALLBACK_LANG: Record<string, string> = {
  "ur-roman": "en",
  ur: "ur",
  en: "en",
};

const MAX_CHARS = 1200;

/**
 * Split on word boundaries, never mid-word.
 *
 * Urdu joins letterforms, and cutting a chunk inside a word makes the
 * synthesiser pronounce two fragments instead of one word — audibly wrong in a
 * way a Latin-script split is not.
 */
function chunk(text: string): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const out: string[] = [];
  let line = "";

  for (const word of words) {
    if ((line + " " + word).trim().length > CHUNK) {
      if (line) out.push(line.trim());
      line = word;
    } else {
      line = `${line} ${word}`;
    }
  }
  if (line.trim()) out.push(line.trim());
  return out;
}

/** The API's neural voice. Same host as everything else, proxied by Next. */
function neuralUpstream(text: string, lang: string): string {
  const q = new URLSearchParams({ text, lang });
  return `${API_ORIGIN}/api/dojo/voice?${q}`;
}

function upstream(text: string, lang: string): string {
  const q = new URLSearchParams({
    ie: "UTF-8",
    client: "tw-ob",
    tl: lang,
    q: text,
  });
  return `https://translate.google.com/translate_tts?${q}`;
}

/**
 * One chunk, with one retry.
 *
 * An undocumented endpoint refuses the occasional request for no stated
 * reason — observed once during a cross-browser run, where a single blip left
 * the buyer silent for that line. A retry after a short pause turns that into
 * a barely perceptible delay instead. Two attempts, not five: if it is
 * genuinely down, the caller needs to hear about it quickly so it can fall
 * back to saying nothing.
 */
async function fetchChunk(part: string, lang: string): Promise<ArrayBuffer> {
  let last = "";
  for (let attempt = 0; attempt < 2; attempt++) {
    if (attempt) await new Promise((r) => setTimeout(r, 350));
    try {
      const response = await fetch(upstream(part, lang), {
        headers: {
          // Without a browser agent the upstream answers 404.
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
          "Accept-Language": `${lang},en;q=0.5`,
        },
        signal: AbortSignal.timeout(12000),
      });
      if (response.ok) return await response.arrayBuffer();
      last = `upstream ${response.status}`;
    } catch (cause) {
      last = cause instanceof Error ? cause.name : "unreachable";
    }
  }
  throw new Error(last);
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const text = (url.searchParams.get("text") ?? "").trim();
  // Kept whole. Splitting on "-" turned "ur-roman" into "ur", which is the
  // one value it must never become: it routes Latin-script Urdu to an Urdu
  // engine.
  const lang = (url.searchParams.get("lang") ?? "en").trim().toLowerCase();

  if (!text) {
    return new Response("missing text", { status: 400 });
  }
  if (text.length > MAX_CHARS) {
    return new Response("text too long", { status: 413 });
  }
  if (!ALLOWED.has(lang)) {
    return new Response(`unsupported language ${lang}`, { status: 400 });
  }
  if (overRate(request)) {
    return new Response("too many requests", {
      status: 429,
      headers: { "Retry-After": "30" },
    });
  }

  // The neural voice takes the whole line at once and sounds far better, so
  // it is tried first and unchunked. Only if it is unreachable does the older
  // path -- which must be split at 180 characters -- get used.
  try {
    const neural = await fetch(neuralUpstream(text, lang), {
      headers: API_KEY ? { "X-API-Key": API_KEY } : undefined,
      signal: AbortSignal.timeout(20000),
    });
    if (neural.ok) {
      const audio = new Uint8Array(await neural.arrayBuffer());
      if (audio.length > 0) {
        return new Response(audio, {
          status: 200,
          headers: {
            "Content-Type": "audio/mpeg",
            "Content-Length": String(audio.length),
            "Cache-Control": "public, max-age=86400, immutable",
            "X-Salix-Voice": "neural",
          },
        });
      }
    }
  } catch {
    /* fall through to the older upstream */
  }

  const fallbackLang = FALLBACK_LANG[lang] ?? "en";
  const parts = chunk(text);

  try {
    // Sequential rather than parallel: the upstream rate-limits bursts from
    // one address, and a session speaks one line at a time anyway.
    const buffers: Uint8Array[] = [];
    for (const part of parts) {
      buffers.push(new Uint8Array(await fetchChunk(part, fallbackLang)));
    }

    // The chunks come back as bare MPEG frames -- same bitrate, same sample
    // rate, no ID3 -- so joining them end to end produces one playable stream.
    // Verified: 64kbps / 24kHz / mono in, 64kbps / 24kHz / mono out.
    const total = buffers.reduce((n, b) => n + b.length, 0);
    const audio = new Uint8Array(total);
    let offset = 0;
    for (const b of buffers) {
      audio.set(b, offset);
      offset += b.length;
    }

    return new Response(audio, {
      status: 200,
      headers: {
        "Content-Type": "audio/mpeg",
        "Content-Length": String(total),
        // The same line is replayed when a rep scrolls back through a session,
        // and the text is the cache key by construction.
        "Cache-Control": "public, max-age=86400, immutable",
        "X-Salix-Voice": "fallback",
      },
    });
  } catch (cause) {
    // Offline, blocked, or timed out. The client treats any non-200 as "no
    // voice available" and says so rather than failing silently.
    return new Response(
      cause instanceof Error ? cause.name : "upstream unreachable",
      { status: 502 },
    );
  }
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
