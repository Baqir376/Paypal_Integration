/**
 * The single door to the backend.
 *
 * Everything goes through `request`, which turns a failure into a typed
 * `ApiError` rather than letting a rejected promise surface as a blank screen.
 * Requests are same-origin because Next proxies /api to FastAPI (see
 * app/api/[...path]/route.ts), which keeps SSE and uploads free of CORS
 * preflight -- and, once a key is configured, is where that key is attached.
 * Nothing here knows the key exists; that is the point.
 */

import type {
  CallDetailResponse,
  CallSummary,
  CoachingPlan,
  CycleReport,
  DealWithTrajectory,
  DojoSession,
  DojoStartResponse,
  Health,
  Overview,
  PipelineEvent,
  PlayDetail,
  PlayWithInstance,
  RepProfile,
  RepSnapshot,
  SearchHit,
  UploadResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly retryable = false,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * How many times a read is retried before it is reported as a failure.
 *
 * A single dropped request used to latch the UI into "API unreachable" with no
 * way back, which is precisely the failure a live demo cannot afford: the dev
 * server compiling a route, or a cold connection, is enough to cause it. Reads
 * are idempotent, so retrying them is free.
 */
const READ_RETRIES = 2;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const idempotent = method === "GET" || method === "HEAD";
  const attempts = idempotent ? READ_RETRIES + 1 : 1;

  let response: Response | null = null;
  let networkFailure: unknown = null;

  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      response = await fetch(path, {
        ...init,
        headers: {
          ...(init?.body instanceof FormData
            ? {}
            : { "Content-Type": "application/json" }),
          ...init?.headers,
        },
      });
      networkFailure = null;
      // A 5xx on a read is worth one more try; a 4xx never is.
      if (response.ok || response.status < 500 || attempt === attempts - 1) break;
    } catch (cause) {
      networkFailure = cause;
      if (attempt === attempts - 1) break;
    }
    await sleep(220 * (attempt + 1));
  }

  if (!response) {
    // Network-level failure: the API is not running, or the browser is offline.
    throw new ApiError(0, "Cannot reach the Salix API. Is the backend running?", true);
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    let retryable = response.status >= 500;
    try {
      const body = await response.json();
      detail = body.detail ?? body.error ?? detail;
      if (typeof body.retryable === "boolean") retryable = body.retryable;
    } catch {
      /* a non-JSON error body is fine; the status line is enough */
    }
    throw new ApiError(response.status, detail, retryable);
  }

  if (response.status === 204) return undefined as T;

  // A 200 with an empty or truncated body would otherwise surface as a raw
  // "Unexpected end of JSON input" from deep inside a component. Turn it into
  // the same typed error every other failure produces.
  const text = await response.text();
  if (!text) {
    throw new ApiError(response.status, "The API returned an empty response.", true);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError(
      response.status,
      "The API returned a malformed response.",
      true,
    );
  }
}

export const api = {
  health: () => request<Health>("/api/health"),
  overview: () => request<Overview>("/api/overview"),

  calls: (params: { rep_id?: string; deal_id?: string; limit?: number } = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).flatMap(([k, v]) => (v == null ? [] : [[k, String(v)]])),
    );
    return request<CallSummary[]>(`/api/calls?${query}`);
  },
  call: (id: string) => request<CallDetailResponse>(`/api/calls/${id}`),
  callTimeline: (id: string) => request<PipelineEvent[]>(`/api/calls/${id}/timeline`),

  reps: () => request<RepSnapshot[]>("/api/reps"),
  rep: (id: string) => request<RepProfile>(`/api/reps/${id}`),
  coach: (id: string) =>
    request<CoachingPlan>(`/api/reps/${id}/coach`, { method: "POST" }),

  plays: () => request<PlayWithInstance[]>("/api/plays"),
  play: (id: string) => request<PlayDetail>(`/api/plays/${id}`),

  deals: () => request<DealWithTrajectory[]>("/api/deals"),
  deal: (id: string) => request<DealWithTrajectory>(`/api/deals/${id}`),

  reports: () => request<CycleReport[]>("/api/reports"),
  latestReport: () => request<CycleReport | null>("/api/reports/latest"),
  generateReport: (label = "") =>
    request<CycleReport>(
      `/api/reports/generate?cycle_label=${encodeURIComponent(label)}`,
      { method: "POST" },
    ),

  search: (q: string, opts: { kind?: string; outcome?: string; k?: number } = {}) => {
    const query = new URLSearchParams({ q, ...(opts as Record<string, string>) });
    return request<SearchHit[]>(`/api/search?${query}`);
  },

  upload: (form: FormData) =>
    request<UploadResponse>("/api/calls/upload", { method: "POST", body: form }),

  dojo: {
    start: (rep_id: string, difficulty = 2, scenario = "", language = "en") =>
      request<DojoStartResponse>("/api/dojo/start", {
        method: "POST",
        body: JSON.stringify({ rep_id, difficulty, scenario, language }),
      }),
    end: (session: DojoSession) =>
      request<DojoSession>("/api/dojo/end", {
        method: "POST",
        body: JSON.stringify({ session }),
      }),
    sessions: (rep_id?: string) =>
      request<DojoSession[]>(
        `/api/dojo/sessions${rep_id ? `?rep_id=${rep_id}` : ""}`,
      ),
  },
};

/* -------------------------------------------------------------------------
 * Server-sent events
 * ---------------------------------------------------------------------- */

/**
 * Subscribe to a call's pipeline stream.
 *
 * Returns an unsubscribe function. The caller owns the lifetime, because a
 * component that unmounts mid-analysis must not leave a socket draining into
 * a dead setState.
 */
export function subscribeToPipeline(
  callId: string,
  onEvent: (event: PipelineEvent) => void,
  onDone?: () => void,
): () => void {
  const source = new EventSource(`/api/calls/${callId}/events`);

  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as PipelineEvent;
      onEvent(event);
      if (event.stage === "done") {
        source.close();
        onDone?.();
      }
    } catch {
      /* a malformed frame should never take down the stream */
    }
  };

  source.addEventListener("close", () => {
    source.close();
    onDone?.();
  });

  source.onerror = () => {
    // EventSource retries on its own; only give up once it has closed.
    if (source.readyState === EventSource.CLOSED) onDone?.();
  };

  return () => source.close();
}

/**
 * Post one Dojo turn and stream the buyer's reply.
 *
 * A single SSE response carries three event types -- `delta` while the buyer
 * speaks, then any `nudge`s, then the authoritative `session` -- so a turn
 * costs one request instead of three.
 */
export async function streamDojoTurn(
  session: DojoSession,
  text: string,
  timing: { start_ms?: number; end_ms?: number },
  handlers: {
    onDelta: (chunk: string) => void;
    onNudge?: (nudge: unknown) => void;
    onSession: (session: DojoSession) => void;
    /** The model refused on a rate limit rather than the buyer being stuck. */
    onThrottled?: (detail: string) => void;
  },
): Promise<void> {
  const response = await fetch("/api/dojo/turn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session, text, ...timing }),
  });

  if (!response.ok || !response.body) {
    throw new ApiError(response.status, "The buyer could not respond.", true);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line; hold a partial frame back.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const eventLine = frame.match(/^event: (.+)$/m);
      const dataLine = frame.match(/^data: (.+)$/m);
      if (!dataLine) continue;

      let payload: any;
      try {
        payload = JSON.parse(dataLine[1]);
      } catch {
        continue;
      }

      switch (eventLine?.[1]) {
        case "delta":
          handlers.onDelta(payload.text);
          break;
        case "nudge":
          handlers.onNudge?.(payload);
          break;
        case "throttled":
          // Its own event so the interface can say what actually happened.
          // Folded into a delta it became the buyer saying "sorry, could you
          // say that again?" on every turn, which reads as a broken product
          // rather than a quota that clears in a minute.
          handlers.onThrottled?.(payload.detail ?? "The model is rate limited.");
          break;
        case "session":
          handlers.onSession(payload as DojoSession);
          break;
      }
    }
  }
}
