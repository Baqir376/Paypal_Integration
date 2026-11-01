"use client";

/**
 * Where PayPal sends the buyer back to, with the order id as `token`.
 *
 * Reaching this page proves nothing about payment: anybody can type the URL. It
 * only asks the server to capture, and the server decides. Reloading it is safe,
 * because a capture can only land once.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { IconArrow, IconCheck, IconWarning } from "@/components/icons";
import { LoadingState } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { OrderResult } from "@/lib/types";

function ReturnPage() {
  const token = useSearchParams().get("token");
  const [result, setResult] = useState<OrderResult | null>(null);
  const [failure, setFailure] = useState<string | null>(
    token ? null : "This link has no PayPal order on it, so nothing was charged.",
  );
  // Strict mode runs effects twice in development. Harmless to the money, but
  // the second answer would briefly replace the first on screen.
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    api
      .captureOrder(token)
      .then(setResult)
      .catch((e: ApiError) => setFailure(e.detail));
  }, [token]);

  const paid = result?.status === "completed";

  return (
    <div className="page" data-status="PAYMENT" style={{ maxWidth: 620 }}>
      <div className="panel" style={{ padding: "26px 28px" }}>
        {!result && !failure && (
          <>
            <div className="eyebrow" style={{ marginBottom: 10 }}>
              PayPal
            </div>
            <h1 className="display d3" style={{ margin: 0 }}>
              Confirming your payment…
            </h1>
            <p className="lede" style={{ marginTop: 12, marginBottom: 0 }}>
              Please keep this page open for a moment.
            </p>
          </>
        )}

        {paid && (
          <>
            <IconCheck size={22} style={{ color: "var(--sage)", marginBottom: 12 }} />
            <h1 className="display d3" style={{ margin: 0 }}>
              <span className="num">{result.credits}</span> credits added
            </h1>
            <p className="lede" style={{ marginTop: 12 }}>
              You now have <span className="num">{result.balance}</span> credits.
            </p>
            <Link href="/upload" className="btn btn-primary">
              Analyse a call
              <IconArrow size={13} />
            </Link>
          </>
        )}

        {result && !paid && (
          <>
            <h1 className="display d3" style={{ margin: 0 }}>
              No credits added yet
            </h1>
            <p className="lede" style={{ marginTop: 12 }}>
              {result.detail}
            </p>
            <div className="num" style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 16 }}>
              Order {result.order_id}
            </div>
            <Link href="/billing" className="btn">
              Back to credits
            </Link>
          </>
        )}

        {failure && (
          <>
            <IconWarning size={20} style={{ color: "var(--rose)", marginBottom: 12 }} />
            <h1 className="display d3" style={{ margin: 0 }}>
              Payment not completed
            </h1>
            <p className="lede" style={{ marginTop: 12 }}>
              {failure}
            </p>
            <Link href="/billing" className="btn">
              Back to credits
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<LoadingState />}>
      <ReturnPage />
    </Suspense>
  );
}
