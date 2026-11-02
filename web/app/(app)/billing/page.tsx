"use client";

/**
 * Credits: what you have, what you can buy, where they went.
 *
 * Choosing a pack leaves for PayPal and comes back through /billing/return. An
 * order that never made it back -- approved, then the tab closed -- is caught up
 * on when this page loads, so nobody pays and sees nothing.
 */

import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { Burst, InfoTip, PageNote, popToast } from "@/components/Pop";
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

/** PayPal's wordmark colours on its usual gold. */
function PayPalLabel({ children }: { children?: React.ReactNode }) {
  return (
    <>
      {children}
      <span className="paypal-word">
        <b>Pay</b>
        <b>Pal</b>
      </span>
    </>
  );
}

function BillingPage() {
  const cancelled = useSearchParams().get("cancelled") === "1";
  const [state, setState] = useState<BillingState | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [buying, setBuying] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  /** The pack being paid for through Braintree's form, once it is open. */
  const [paying, setPaying] = useState<string | null>(null);
  const [added, setAdded] = useState<number | null>(null);
  /** The pack in the checkout pop-up, before leaving for PayPal. */
  const [checkout, setCheckout] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement | null>(null);
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

  useEffect(() => {
    if (checkout) dialog.current?.showModal();
    else dialog.current?.close();
  }, [checkout]);

  useEffect(() => {
    if (added !== null) popToast(`${added} credits added`);
  }, [added]);

  async function buy(packId: string) {
    if (state?.provider === "braintree") return openBraintree(packId);
    setCheckout(packId);
  }

  async function goToPayPal(packId: string) {
    setBuying(packId);
    setFailure(null);
    try {
      const { approve_url } = await api.checkout(packId);
      window.location.assign(approve_url);
    } catch (e) {
      setFailure((e as ApiError).detail);
      setBuying(null);
      setCheckout(null);
    }
  }

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!state) return <LoadingState />;

  const chosen = state.packs.find((pack) => pack.id === checkout);
  const unitPrice = (pack: { price: string; credits: number }) => Number(pack.price) / pack.credits;
  const bestValue = state.packs.reduce((best, pack) => (unitPrice(pack) < unitPrice(best) ? pack : best), state.packs[0]);
  const viaPayPal = state.provider !== "braintree";

  return (
    <div className="page" data-status="CREDITS" style={{ maxWidth: 940 }}>
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            Credits
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            <motion.span
              key={state.balance}
              className="num"
              style={{ display: "inline-block" }}
              initial={{ scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", stiffness: 320, damping: 16 }}
            >
              {state.balance}
            </motion.span>{" "}
            {state.balance === 1 ? "credit" : "credits"} left
          </h1>
          <PageNote>
            {state.enforced
              ? `Each recording uses ${state.call_cost} credit, and comes with a score and a coaching plan. If an analysis fails, the credit is returned.`
              : "Uploads are free on this deployment, so credits are not being used."}
          </PageNote>
        </div>
      </header>

      {viaPayPal && state.can_purchase && (
        <div className="pay-status" data-simulated={state.simulated}>
          <span className="pay-status-dot" aria-hidden="true" />
          <strong>
            {state.simulated ? "Simulated payments" : state.environment === "sandbox" ? "PayPal sandbox" : "PayPal"}
          </strong>
          {(state.simulated || state.environment === "sandbox") && <span>No real money moves</span>}
          <InfoTip label="About these payments" align="end">
            {state.simulated ? (
              <>
                <strong>Integrated through APIMatic.</strong> Orders go through APIMatic&apos;s PayPal Server SDK, but
                they are answered on this machine, so they do not reach PayPal and the credits are free. Add PayPal
                sandbox keys and the same code talks to PayPal.
              </>
            ) : (
              <>
                <strong>Integrated through APIMatic.</strong> Orders are created and captured with APIMatic&apos;s PayPal
                Server SDK. {state.environment === "sandbox" && "Use a sandbox buyer account."}
              </>
            )}
          </InfoTip>
        </div>
      )}

      {cancelled && <Notice>You cancelled at PayPal, so nothing was charged.</Notice>}
      {failure && <Notice tone="var(--rose)">{failure}</Notice>}
      {!state.can_purchase && (
        <Notice tone="var(--rose)">
          Credits cannot be bought here yet: PayPal is not configured on this
          server.
        </Notice>
      )}
      {!state.can_buy && <Notice>Only your team owner can buy credits.</Notice>}
      {added !== null && <Notice tone="var(--sage)">{added} credits added.</Notice>}
      {state.provider === "braintree" && state.environment === "sandbox" && (
        <Notice>
          Braintree sandbox, PayPal&apos;s payment gateway. No real money moves. Use test
          card 4111 1111 1111 1111 with any future expiry.
        </Notice>
      )}

      <div className="packs">
        {state.packs.map((pack, index) => (
          <motion.section
            key={pack.id}
            className="pack panel"
            data-best={pack.id === bestValue.id}
            initial={{ opacity: 0, y: 24, scale: 0.94 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            whileHover={{ y: -5 }}
            transition={{ type: "spring", stiffness: 300, damping: 22, delay: index * 0.06 }}
          >
            {pack.id === bestValue.id && <span className="pack-best">Best value</span>}
            <div className="eyebrow">{pack.label}</div>
            <div className="pack-credits num">
              {pack.credits}
              <small>credits</small>
            </div>
            <div className="pack-price num">
              {pack.currency} {pack.price}
              <small>{unitPrice(pack).toFixed(2)} each</small>
            </div>
            <motion.button
              className={viaPayPal ? "paypal-button" : "btn btn-primary"}
              style={viaPayPal ? undefined : { width: "100%", justifyContent: "center" }}
              disabled={!state.can_purchase || !state.can_buy || buying !== null}
              onClick={() => buy(pack.id)}
              whileTap={{ scale: 0.97 }}
              aria-label={viaPayPal ? `Pay with PayPal: ${pack.label}` : undefined}
            >
              {viaPayPal ? <PayPalLabel>Pay with</PayPalLabel> : buying === pack.id ? "Opening checkout…" : "Buy with Braintree"}
            </motion.button>
          </motion.section>
        ))}
      </div>

      <dialog
        ref={dialog}
        className="pay-pop"
        aria-label="Checkout"
        onClose={() => setCheckout(null)}
        onClick={(event) => {
          if (event.target === dialog.current && buying === null) setCheckout(null);
        }}
      >
        {chosen && (
          <motion.div
            key={chosen.id}
            className="pay-pop-body"
            initial={{ opacity: 0, scale: 0.8, y: 24 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 340, damping: 22 }}
          >
            <div className="eyebrow">{chosen.label}</div>
            <div className="pay-pop-credits num">{chosen.credits} credits</div>
            <div className="pay-pop-price num">
              {chosen.currency} {chosen.price}
            </div>
            <ol className="pay-steps" aria-label="What happens next">
              <li>Order</li>
              <li>Approve</li>
              <li>Credits</li>
            </ol>
            {state.simulated && <p className="pay-pop-sim">Simulated checkout. No real money moves.</p>}
            <motion.button
              autoFocus
              className="paypal-button"
              disabled={buying !== null}
              onClick={() => goToPayPal(chosen.id)}
              whileTap={{ scale: 0.97 }}
            >
              {buying === chosen.id ? (
                "Creating your order…"
              ) : state.simulated ? (
                "Continue to simulated checkout"
              ) : (
                <PayPalLabel>Continue to</PayPalLabel>
              )}
            </motion.button>
            <button className="btn btn-ghost pay-pop-cancel" disabled={buying !== null} onClick={() => setCheckout(null)}>
              Not now
            </button>
            <div className="pay-pop-sdk">PayPal Server SDK by APIMatic</div>
          </motion.div>
        )}
      </dialog>

      {added !== null && <div className="burst-anchor" key={added}><Burst /></div>}

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
