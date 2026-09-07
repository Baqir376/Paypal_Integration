/**
 * Shared page furniture.
 *
 * These live here rather than beside a page because a Next.js route file may
 * only export `default` and a handful of reserved names -- exporting a
 * component from `page.tsx` and importing it elsewhere fails the build.
 */

import { initials } from "@/lib/format";

/** The heading strip at the top of every panel. */
export function SectionHead({ title, hint }: { title: string; hint?: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        gap: 14,
        padding: "15px 17px 12px",
        borderBottom: "1px solid var(--rule)",
      }}
    >
      <h2 className="display" style={{ fontSize: 20, margin: 0 }}>
        {title}
      </h2>
      {hint && (
        <span style={{ fontSize: 12, color: "var(--ink-3)", textAlign: "right" }}>
          {hint}
        </span>
      )}
    </div>
  );
}

export function Avatar({ name, top }: { name: string; top?: boolean }) {
  return (
    <span
      title={top ? `${name} — top performer` : name}
      className="num"
      style={{
        display: "grid",
        placeItems: "center",
        width: 28,
        height: 28,
        borderRadius: 999,
        fontSize: 10.5,
        fontWeight: 500,
        flexShrink: 0,
        background: top ? "var(--willow-wash)" : "var(--paper-3)",
        color: top ? "var(--willow)" : "var(--ink-3)",
        border: `1px solid ${
          top ? "color-mix(in oklab, var(--willow) 35%, transparent)" : "var(--rule)"
        }`,
      }}
    >
      {initials(name)}
    </span>
  );
}

/**
 * Skeletons rather than a spinner: the page keeps its shape while it loads, so
 * nothing jumps when the data lands.
 */
export function LoadingState() {
  return (
    <div className="page">
      <div className="skeleton" style={{ height: 42, width: "44%", marginBottom: 14 }} />
      <div className="skeleton" style={{ height: 20, width: "62%", marginBottom: 32 }} />
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(198px, 1fr))",
          gap: 12,
          marginBottom: 24,
        }}
      >
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton" style={{ height: 106 }} />
        ))}
      </div>
      <div className="skeleton" style={{ height: 320 }} />
    </div>
  );
}

/**
 * A failure the reader can act on.
 *
 * The whole value of this component is that the instruction matches the
 * cause. A single "start the API" screen for every failure is worse than no
 * screen at all: shown for a stale link it sends someone to re-seed a healthy
 * database, and shown for a key mismatch it sends them to restart an API that
 * is already running and answering. Each branch below is a distinct diagnosis.
 */
export function ErrorState({ message, status }: { message: string; status?: number }) {
  // The API answered, and refused. So it is up, reachable, and the two halves
  // of the deployment disagree about the key -- which restarting fixes only
  // by accident, and only if the environment changed in between.
  if (status === 401 || status === 403) {
    return (
      <div className="page">
        <div className="panel" style={{ padding: 28, maxWidth: 620 }}>
          <div className="eyebrow" style={{ color: "var(--rose)", marginBottom: 10 }}>
            Refused by the API
          </div>
          <h1 className="display d3" style={{ margin: "0 0 14px" }}>
            The API is running, but it rejected this request
          </h1>
          <p className="prose-body" style={{ fontSize: 13.5, marginBottom: 10 }}>
            The backend has <code className="num">SALIX_API_KEY</code> set, and
            the web server is sending a different one or none at all. Both
            processes need the same value.
          </p>
          <pre
            className="num"
            style={{
              fontSize: 12,
              background: "var(--paper)",
              border: "1px solid var(--rule)",
              borderRadius: "var(--r)",
              padding: "9px 12px",
              margin: "0 0 12px",
              overflowX: "auto",
            }}
          >
            SALIX_API_KEY=&lt;the same value&gt;   # for both api/ and web/
          </pre>
          <p className="prose-body" style={{ fontSize: 13.5, margin: 0 }}>
            Restart the web server after changing it — the key is read once, at
            startup, on the server side. Nothing needs to change in the browser.
          </p>
        </div>
      </div>
    );
  }

  // Not broken, just early. Saying so keeps somebody from restarting a system
  // that is working exactly as configured.
  if (status === 429) {
    return (
      <div className="page">
        <div className="panel" style={{ padding: 28, maxWidth: 580 }}>
          <div className="eyebrow" style={{ color: "var(--amber, var(--rose))", marginBottom: 10 }}>
            Slow down
          </div>
          <h1 className="display d3" style={{ margin: "0 0 14px" }}>
            {message}
          </h1>
          <p className="prose-body" style={{ fontSize: 13.5, marginBottom: 18 }}>
            Nothing is broken and nothing was lost. This endpoint has a ceiling
            so one busy tab cannot slow the floor down; it clears on its own.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => window.location.reload()}
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (status === 404) {
    return (
      <div className="page">
        <div className="panel" style={{ padding: 28, maxWidth: 580 }}>
          <div className="eyebrow" style={{ color: "var(--ink-3)", marginBottom: 10 }}>
            Not found
          </div>
          <h1 className="display d3" style={{ margin: "0 0 14px" }}>
            {message}
          </h1>
          <p className="prose-body" style={{ fontSize: 13.5, margin: "0 0 18px" }}>
            The link may be out of date, or the record was removed. Everything
            else is working normally.
          </p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <a href="/console" className="btn btn-primary">
              Back to the command centre
            </a>
            <a href="/calls" className="btn">
              Browse every call
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="panel" style={{ padding: 28, maxWidth: 580 }}>
        <div className="eyebrow" style={{ color: "var(--rose)", marginBottom: 10 }}>
          Cannot load
        </div>
        <h1 className="display d3" style={{ margin: "0 0 14px" }}>
          {message}
        </h1>
        <p className="prose-body" style={{ fontSize: 13.5, marginBottom: 10 }}>
          Start the API from <code className="num">api/</code>:
        </p>
        <pre
          className="num"
          style={{
            fontSize: 12,
            background: "var(--paper)",
            border: "1px solid var(--rule)",
            borderRadius: "var(--r)",
            padding: "9px 12px",
            margin: "0 0 12px",
            overflowX: "auto",
          }}
        >
          .venv/Scripts/python -m uvicorn salix.app:app --reload
        </pre>
        <p className="prose-body" style={{ fontSize: 13.5, marginBottom: 10 }}>
          Then seed it from the repository root:
        </p>
        <pre
          className="num"
          style={{
            fontSize: 12,
            background: "var(--paper)",
            border: "1px solid var(--rule)",
            borderRadius: "var(--r)",
            padding: "9px 12px",
            margin: 0,
            overflowX: "auto",
          }}
        >
          api/.venv/Scripts/python -m seed.build --reset --report
        </pre>
      </div>
    </div>
  );
}
