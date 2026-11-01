"use client";

/**
 * Sign in. There is one way to do it, and the server does all the work: the link
 * below is a plain navigation to the API, which goes to Google and comes back with
 * a session cookie this page's code can never read.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Mark } from "@/components/Mark";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

const ERRORS: Record<string, string> = {
  cancelled: "Sign-in was cancelled. Nothing was changed.",
  expired: "That sign-in took too long or was opened in another browser. Please try again.",
  failed: "Google could not confirm your account. Please try again.",
  not_configured: "Google sign-in is not set up on this server yet.",
};

function Login() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get("next") ?? "/console";
  const error = search.get("error");
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api
      .me()
      .then((state) => {
        setMe(state);
        if (state.user || !state.auth_required) router.replace(next);
      })
      .catch(() => setMe(null));
  }, [router, next]);

  const unavailable = me !== null && !me.google_enabled;

  return (
    <main
      style={{
        minHeight: "100svh",
        display: "grid",
        placeItems: "center",
        padding: "24px 16px",
        background: "var(--paper)",
      }}
    >
      <div className="panel" style={{ width: "100%", maxWidth: 420, padding: "32px 30px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 26 }}>
          <Mark size={24} />
          <span className="display" style={{ fontSize: 27, letterSpacing: "-0.02em" }}>
            Salix
          </span>
        </div>

        <h1 className="display d3" style={{ margin: "0 0 8px" }}>
          Sign in to your team
        </h1>
        <p style={{ fontSize: 13.5, color: "var(--ink-3)", margin: "0 0 22px", lineHeight: 1.55 }}>
          New here? Signing in creates your team. If a colleague invited you, use
          the address they invited and you will join theirs.
        </p>

        {error && (
          <div
            role="alert"
            style={{
              padding: "10px 13px",
              marginBottom: 16,
              border: "1px solid var(--rose)",
              borderRadius: "var(--r)",
              color: "var(--rose)",
              fontSize: 13,
            }}
          >
            {ERRORS[error] ?? ERRORS.failed}
          </div>
        )}

        {unavailable ? (
          <p role="alert" style={{ fontSize: 13, color: "var(--rose)", margin: 0 }}>
            {ERRORS.not_configured}
          </p>
        ) : (
          <a
            className="btn btn-primary"
            href={`/api/auth/google/start?next=${encodeURIComponent(next)}`}
            style={{ width: "100%", justifyContent: "center", height: 42, fontSize: 14 }}
          >
            Continue with Google
          </a>
        )}
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <Login />
    </Suspense>
  );
}
