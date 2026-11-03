"use client";

/**
 * Credits: what you have, what you can buy, where they went.
 *
 * Choosing a pack leaves for PayPal and comes back through /billing/return. An
 * order that never made it back -- approved, then the tab closed -- is caught up
 * on when this page loads, so nobody pays and sees nothing.
 */

import { useSearchParams } from "next/navigation";
import { motion, useMotionValue, useReducedMotion, useSpring } from "framer-motion";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { IconCheck, IconCoin } from "@/components/icons";
import { PaymentSuccess } from "@/components/PaymentSuccess";
import { NoteWindow, PageNote, useCountUp } from "@/components/Pop";
import { BalanceTrend, CheckList, JourneySteps, SideCard } from "@/components/Studio";
import { ErrorState, LoadingState, SectionHead } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { shortDate } from "@/lib/format";
import type { BillingState, OrderResult } from "@/lib/types";

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
  purchase: "Credits bought",
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

type Pack = BillingState["packs"][number];

/** One pack, leaning towards the pointer with a light that follows it. */
function PackCard({
  pack,
  index,
  best,
  save,
  callCost,
  children,
}: {
  pack: Pack;
  index: number;
  best: boolean;
  /** Percent cheaper per credit than the dearest pack. */
  save: number;
  callCost: number;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  const shown = useCountUp(pack.credits, { delay: 0.15 + index * 0.08 });
  const springy = { stiffness: 220, damping: 20 };
  const rotateX = useSpring(useMotionValue(0), springy);
  const rotateY = useSpring(useMotionValue(0), springy);
  const recordings = Math.floor(pack.credits / callCost);

  function lean(event: React.PointerEvent<HTMLElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - box.left;
    const y = event.clientY - box.top;
    event.currentTarget.style.setProperty("--x", `${x}px`);
    event.currentTarget.style.setProperty("--y", `${y}px`);
    if (reduced || event.pointerType !== "mouse") return;
    rotateY.set((x / box.width - 0.5) * 9);
    rotateX.set((0.5 - y / box.height) * 9);
  }

  return (
    <motion.section
      className="pack panel"
      data-best={best}
      style={{ rotateX, rotateY }}
      initial={{ opacity: 0, y: 34, scale: 0.92 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      whileHover={{ y: -6 }}
      transition={{ type: "spring", stiffness: 280, damping: 22, delay: index * 0.08 }}
      onPointerMove={lean}
      onPointerLeave={() => {
        rotateX.set(0);
        rotateY.set(0);
      }}
    >
      <span className="pack-shine" aria-hidden="true" />
      {best && <span className="pack-ring" aria-hidden="true" />}
      {best && <span className="pack-best">Best value</span>}
      <div className="eyebrow">
        {pack.label}
        {save > 0 && <span className="pack-save">Save {save}%</span>}
      </div>
      <div className="pack-credits num">
        {shown}
        <small>credits</small>
      </div>
      <div className="pack-price num">
        {pack.currency} {pack.price}
        <small>{(Number(pack.price) / pack.credits).toFixed(2)} each</small>
      </div>
      <ul className="pack-perks">
        <li>
          <IconCheck size={13} />
          {recordings} {recordings === 1 ? "recording" : "recordings"} analysed
        </li>
        <li>
          <IconCheck size={13} />
          Score and coaching plan on each
        </li>
        <li>
          <IconCheck size={13} />
          Credit back if an analysis fails
        </li>
      </ul>
      {children}
    </motion.section>
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
  /** A Braintree payment that just completed, for the success window. */
  const [paid, setPaid] = useState<OrderResult | null>(null);
  const [celebrating, setCelebrating] = useState(false);
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
    const pack = state?.packs.find((candidate) => candidate.id === packId);
    try {
      await dropIn.current?.teardown();
      dropIn.current = null;
      const [{ client_token }, library] = await Promise.all([api.braintreeToken(), loadDropIn()]);
      setPaying(packId);
      // The box below renders with this state, which can take more than a frame.
      for (let frame = 0; !dropInBox.current && frame < 120; frame++) {
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      dropIn.current = await library.create({
        authorization: client_token,
        container: dropInBox.current,
        // PayPal as a wallet inside Braintree's form, for this pack's server-set price.
        ...(state?.paypal_wallet && pack
          ? { paypal: { flow: "checkout", amount: pack.price, currency: pack.currency } }
          : {}),
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
        setPaid(result);
        setCelebrating(true);
        // The balance in the rail is the Shell's, and this page did not navigate.
        window.dispatchEvent(new Event("salix:credits"));
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
  const dearest = Math.max(...state.packs.map(unitPrice));
  const recordingsLeft = Math.floor(state.balance / state.call_cost);

  return (
    <div className="page" data-status="CREDITS" style={{ maxWidth: 1320 }}>
      <motion.header
        className="credit-hero"
        initial={{ opacity: 0, y: 22, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 240, damping: 24 }}
      >
        <div className="credit-hero-glow" aria-hidden="true" />
        <div className="credit-hero-main">
          <div className="eyebrow">Your credits</div>
          <h1 className="credit-hero-number">
            <Balance value={state.balance} />
            {state.balance === 1 ? "credit" : "credits"} left
          </h1>
          <p className="credit-hero-sub" data-empty={state.enforced && recordingsLeft === 0}>
            {!state.enforced
              ? "Uploads are free on this deployment."
              : recordingsLeft === 0
                ? "You are out of credits. Pick a pack to analyse your next call."
                : `Enough for ${recordingsLeft} more ${recordingsLeft === 1 ? "recording" : "recordings"}.`}
          </p>
          <div className="credit-hero-row">
            <PageNote>
              {state.enforced
                ? `Each recording uses ${state.call_cost} credit, and comes with a score and a coaching plan. If an analysis fails, the credit is returned.`
                : "Uploads are free on this deployment, so credits are not being used."}
            </PageNote>
            {viaPayPal && state.can_purchase && (
              <NoteWindow
                title={state.simulated ? "Simulated payments" : state.environment === "sandbox" ? "PayPal sandbox" : "PayPal"}
                eyebrow="About these payments"
                triggerProps={{
                  className: "pay-status pay-status-button",
                  "data-simulated": state.simulated,
                  "aria-label": "About these payments",
                }}
                trigger={
                  <>
                    <span className="pay-status-dot" aria-hidden="true" />
                    <strong>
                      {state.simulated ? "Simulated payments" : state.environment === "sandbox" ? "PayPal sandbox" : "PayPal"}
                    </strong>
                    {(state.simulated || state.environment === "sandbox") && <span>No real money moves</span>}
                    <span className="info-dot" aria-hidden="true">
                      i
                    </span>
                  </>
                }
              >
                {state.simulated ? (
                  <p>
                    <strong>Integrated through APIMatic.</strong> Orders go through APIMatic&apos;s PayPal Server SDK, but
                    they are answered on this machine, so they do not reach PayPal and the credits are free. Add PayPal
                    sandbox keys and the same code talks to PayPal.
                  </p>
                ) : (
                  <p>
                    <strong>Integrated through APIMatic.</strong> Orders are created and captured with APIMatic&apos;s PayPal
                    Server SDK.
                    {state.environment === "sandbox" && " This is PayPal's test environment, so no real money moves. Pay with a sandbox buyer account, not your own PayPal login."}
                  </p>
                )}
                <JourneySteps
                  steps={[
                    { label: "Salix creates the order" },
                    { label: state.simulated ? "You approve the simulated checkout" : "You approve it on PayPal" },
                    { label: "Salix captures it and adds your credits" },
                  ]}
                />
              </NoteWindow>
            )}
          </div>
        </div>
        <div className="credit-orbit" aria-hidden="true">
          <i />
          <i />
          <span className="credit-coin">
            <IconCoin size={28} />
          </span>
        </div>
      </motion.header>

      <div className="split">
      <div style={{ minWidth: 0 }}>
      {cancelled && <Notice>You cancelled at PayPal, so nothing was charged.</Notice>}
      {failure && <Notice tone="var(--rose)">{failure}</Notice>}
      {!state.can_purchase && (
        <Notice tone="var(--rose)">
          Credits cannot be bought here yet: PayPal is not configured on this
          server.
        </Notice>
      )}
      {!state.can_buy && <Notice>Only your team owner can buy credits.</Notice>}
      {state.provider === "braintree" && state.environment === "sandbox" && (
        <Notice>
          Braintree sandbox, PayPal&apos;s payment gateway. No real money moves. Use test
          card 4111 1111 1111 1111 with any future expiry
          {state.paypal_wallet ? ", or choose PayPal, which Braintree mocks in its sandbox." : "."}
        </Notice>
      )}

      <div className="packs">
        {state.packs.map((pack, index) => (
          <PackCard
            key={pack.id}
            pack={pack}
            index={index}
            best={pack.id === bestValue.id}
            save={Math.round((1 - unitPrice(pack) / dearest) * 100)}
            callCost={state.call_cost}
          >
            <motion.button
              className={viaPayPal ? "paypal-button" : "btn btn-primary"}
              style={viaPayPal ? undefined : { width: "100%", justifyContent: "center" }}
              disabled={!state.can_purchase || !state.can_buy || buying !== null}
              onClick={() => buy(pack.id)}
              whileTap={{ scale: 0.97 }}
              aria-label={viaPayPal ? `Pay with PayPal: ${pack.label}` : undefined}
            >
              {viaPayPal ? <PayPalLabel>Pay with</PayPalLabel> : buying === pack.id ? "Opening checkout…" : state.paypal_wallet ? "Buy with PayPal or card" : "Buy with Braintree"}
            </motion.button>
          </PackCard>
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

      {paid && (
        <PaymentSuccess
          open={celebrating}
          onClose={() => setCelebrating(false)}
          credits={paid.credits}
          balance={paid.balance}
          orderId={paid.order_id}
          amount={paid.amount}
          currency={paid.currency}
          method={state.environment === "sandbox" ? "Braintree sandbox, test money" : "Braintree"}
        />
      )}

      {paying && (
        <section className="panel" style={{ padding: "18px 19px", marginBottom: 22 }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            Paying for {state.packs.find((p) => p.id === paying)?.label}
          </div>
          <div ref={dropInBox} className="dropin-box" />
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
                {state.history.map((entry, index) => (
                  <motion.tr
                    key={entry.id}
                    initial={{ opacity: 0, x: -14 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.32, delay: 0.25 + Math.min(index, 8) * 0.05 }}
                  >
                    <td>{REASONS[entry.reason] ?? entry.reason}</td>
                    <td style={{ color: "var(--ink-3)" }}>{shortDate(entry.created_at)}</td>
                    <td className="num" style={{ textAlign: "right" }}>
                      <span className="ledger-delta" data-up={entry.delta > 0}>
                        {entry.delta > 0 ? `+${entry.delta}` : entry.delta}
                      </span>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      </div>

      <aside className="split-side">
        <SideCard title="Your balance" hint={state.history.length ? `last ${state.history.length} ${state.history.length === 1 ? "change" : "changes"}` : undefined}>
          <BalanceTrend balance={state.balance} history={state.history} />
        </SideCard>
        <SideCard title="What one credit does" index={1}>
          <JourneySteps
            steps={[
              { label: "You upload a recording" },
              { label: "Salix scores the call" },
              { label: "You get a coaching plan" },
              { label: "If it fails, the credit comes back" },
            ]}
          />
        </SideCard>
        <SideCard title="Paying safely" index={2}>
          <CheckList
            items={[
              "Prices come from our server, never the browser",
              "A payment can only add its credits once",
              viaPayPal ? "Your payment details stay with PayPal" : "Your card details stay with Braintree",
            ]}
          />
        </SideCard>
      </aside>
      </div>
    </div>
  );
}

/** Counts up from where it last stood, so a new balance visibly lands. */
function Balance({ value }: { value: number }) {
  const before = useRef(0);
  const shown = useCountUp(value, { from: before.current });
  useEffect(() => {
    before.current = value;
  }, [value]);
  return <span className="num">{shown}</span>;
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
