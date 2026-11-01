"use client";

/**
 * Credits: what you have, what you can buy, where they went.
 *
 * Choosing a pack leaves for PayPal and comes back through /billing/return. An
 * order that never made it back -- approved, then the tab closed -- is caught up
 * on when this page loads, so nobody pays and sees nothing.
 */

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { ErrorState, LoadingState, SectionHead } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { shortDate } from "@/lib/format";
import type { BillingState } from "@/lib/types";

/** Braintree's hosted payment form. Card details stay between the buyer and Braintree. */
const DROP_IN = "https://js.braintreegateway.com/web/dropin/1.44.1/js/dropin.min.js";

type DropIn = {
  requestPaymentMethod: () => Promise<{ nonce: string }>;
  teardown: () => Promise<void>;
};

function loadDropIn(): Promise<{ create: (options: object) => Promise<DropIn> }> {
  const w = window as unknown as { braintree?: { dropin: { create: (options: object) => Promise<DropIn> } } };
  if (w.braintree?.dropin) return Promise.resolve(w.braintree.dropin);
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = DROP_IN;
    script.onload = () => resolve(w.braintree!.dropin);
    script.onerror = () => reject(new Error("Braintree's payment form could not be loaded."));
    document.head.appendChild(script);
  });
}

const REASONS: Record<string, string> = {
  purchase: "Bought on PayPal",
  call_analysis: "Recording analysed",
  call_refund: "Refunded: analysis failed",
  paypal_refund: "Refunded on PayPal",
};

function BillingPage() {
  const cancelled = useSearchParams().get("cancelled") === "1";
  const [state, setState] = useState<BillingState | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [buying, setBuying] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  /** The pack being paid for through Braintree's form, once it is open. */
  const [paying, setPaying] = useState<string | null>(null);
  const [added, setAdded] = useState<number | null>(null);
  const dropIn = useRef<DropIn | null>(null);
  const dropInBox = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      setState(await api.billing());
    } catch (e) {
      setError(e as ApiError);
    }
  }, []);

  useEffect(() => {
    load();
    // Separate, and allowed to fail: PayPal being slow or unreachable must not
    // stop anyone seeing the balance they already have.
    api
      .reconcileBilling()
      .then((r) => {
        if (r.checked > 0) load();
      })
      .catch(() => {});
  }, [load]);

  async function openBraintree(packId: string) {
    setBuying(packId);
    setFailure(null);
    setAdded(null);
    try {
      await dropIn.current?.teardown();
      dropIn.current = null;
      const [{ client_token }, library] = await Promise.all([api.braintreeToken(), loadDropIn()]);
      setPaying(packId);
      // After the box below has rendered.
      await new Promise((resolve) => requestAnimationFrame(resolve));
      dropIn.current = await library.create({
        authorization: client_token,
        container: dropInBox.current,
      });
    } catch (e) {
      setPaying(null);
      setFailure((e as ApiError).detail ?? (e as Error).message);
    } finally {
      setBuying(null);
    }
  }

  async function payBraintree() {
    if (!dropIn.current || !paying) return;
    setBuying(paying);
    setFailure(null);
    try {
      const { nonce } = await dropIn.current.requestPaymentMethod();
      const result = await api.braintreePay(paying, nonce);
      if (result.status === "completed") {
        setAdded(result.credits);
        setPaying(null);
        await dropIn.current.teardown();
        dropIn.current = null;
      } else {
        setFailure(result.detail || "That payment did not complete.");
      }
      await load();
    } catch (e) {
      setFailure((e as ApiError).detail ?? (e as Error).message);
    } finally {
      setBuying(null);
    }
  }

  async function buy(packId: string) {
    if (state?.provider === "braintree") return openBraintree(packId);
    setBuying(packId);
    setFailure(null);
    try {
      const { approve_url } = await api.checkout(packId);
      window.location.assign(approve_url);
    } catch (e) {
      setFailure((e as ApiError).detail);
      setBuying(null);
    }
  }

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!state) return <LoadingState />;

  return (
    <div className="page" data-status="CREDITS" style={{ maxWidth: 940 }}>
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            Credits
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            <span className="num">{state.balance}</span>{" "}
            {state.balance === 1 ? "credit" : "credits"} left
          </h1>
          <p className="lede" style={{ marginTop: 12, marginBottom: 0 }}>
            {state.enforced
              ? `Each recording uses ${state.call_cost} credit, and comes with a score and a coaching plan. If an analysis fails, the credit is returned.`
              : "Uploads are free on this deployment, so credits are not being used."}
          </p>
        </div>
      </header>

      {cancelled && (
        <Notice>You cancelled at PayPal, so nothing was charged.</Notice>
      )}
      {failure && <Notice tone="var(--rose)">{failure}</Notice>}
      {!state.can_purchase && (
        <Notice tone="var(--rose)">
          Credits cannot be bought here yet: PayPal is not configured on this
          server.
        </Notice>
      )}
      {!state.can_buy && <Notice>Only your team owner can buy credits.</Notice>}
      {state.simulated && (
        <Notice tone="var(--ember)">
          <strong style={{ fontWeight: 550 }}>Simulated payments.</strong> This does not
          reach PayPal, no money moves, and the credits are free. It uses the same
          APIMatic SDK code as a real sandbox purchase, and real PayPal keys replace it.
        </Notice>
      )}
      {added !== null && <Notice tone="var(--sage)">{added} credits added.</Notice>}
      {state.provider === "braintree" && state.environment === "sandbox" && (
        <Notice>
          Braintree sandbox, PayPal&apos;s payment gateway. No real money moves. Use test
          card 4111 1111 1111 1111 with any future expiry.
        </Notice>
      )}
      {state.provider === "paypal" && state.environment === "sandbox" && (
        <Notice>
          PayPal sandbox: use a sandbox buyer account. No real money moves.
        </Notice>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
          gap: 14,
          marginBottom: 22,
        }}
      >
        {state.packs.map((pack) => (
          <section key={pack.id} className="panel" style={{ padding: "18px 19px" }}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>
              {pack.label}
            </div>
            <div className="display d3 num" style={{ margin: "0 0 2px" }}>
              {pack.credits} credits
            </div>
            <div style={{ fontSize: 13, color: "var(--ink-3)", marginBottom: 16 }}>
              <span className="num">
                {pack.currency} {pack.price}
              </span>{" "}
              ·{" "}
              <span className="num">
                {(Number(pack.price) / pack.credits).toFixed(2)}
              </span>{" "}
              per recording
            </div>
            <button
              className="btn btn-primary"
              style={{ width: "100%", justifyContent: "center" }}
              disabled={!state.can_purchase || !state.can_buy || buying !== null}
              onClick={() => buy(pack.id)}
            >
              {buying === pack.id
                ? "Opening checkout…"
                : state.simulated
                  ? "Simulated PayPal checkout"
                  : state.provider === "braintree"
                    ? "Buy with Braintree"
                    : "Pay with PayPal"}
            </button>
          </section>
        ))}
      </div>

      {paying && (
        <section className="panel" style={{ padding: "18px 19px", marginBottom: 22 }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            Paying for {state.packs.find((p) => p.id === paying)?.label}
          </div>
          <div ref={dropInBox} />
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="btn btn-primary" onClick={payBraintree} disabled={buying !== null}>
              {buying ? "Paying…" : "Pay now"}
            </button>
            <button className="btn btn-ghost" onClick={() => setPaying(null)} disabled={buying !== null}>
              Cancel
            </button>
          </div>
        </section>
      )}

      <section className="panel panel-flush">
        <SectionHead title="History" />
        {state.history.length === 0 ? (
          <p style={{ padding: "22px 18px", margin: 0, fontSize: 13.5, color: "var(--ink-3)" }}>
            Nothing yet.
          </p>
        ) : (
          <div className="scroll-x">
            <table className="table">
              <tbody>
                {state.history.map((entry) => (
                  <tr key={entry.id}>
                    <td>{REASONS[entry.reason] ?? entry.reason}</td>
                    <td style={{ color: "var(--ink-3)" }}>{shortDate(entry.created_at)}</td>
                    <td
                      className="num"
                      style={{
                        textAlign: "right",
                        color: entry.delta > 0 ? "var(--sage)" : "var(--ink-2)",
                      }}
                    >
                      {entry.delta > 0 ? `+${entry.delta}` : entry.delta}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Notice({
  children,
  tone = "var(--rule-strong)",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <div
      role="status"
      className="panel"
      style={{ padding: "12px 15px", marginBottom: 16, borderColor: tone, fontSize: 13 }}
    >
      {children}
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<LoadingState />}>
      <BillingPage />
    </Suspense>
  );
}
