"use client";

/**
 * The moment a payment lands: a glass window with a drawn tick, a burst, and the
 * receipt. Only ever opened for an order the server says completed.
 */

import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";

import { IconArrow } from "@/components/icons";
import { Burst, GlassDialog, useCountUp } from "@/components/Pop";

const DRAW = [0.65, 0, 0.35, 1] as const;

function Row({ label, value, index }: { label: string; value: React.ReactNode; index: number }) {
  return (
    <motion.div
      className="receipt-row"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.72 + index * 0.08, duration: 0.34 }}
    >
      <dt>{label}</dt>
      <dd className="num">{value}</dd>
    </motion.div>
  );
}

/** The order number is what support asks for, so it should take one click to keep. */
function CopyOrder({ value }: { value: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const timer = setTimeout(() => setState("idle"), 1800);
    return () => clearTimeout(timer);
  }, [state]);

  return (
    <button
      type="button"
      className="receipt-copy"
      data-state={state}
      onClick={() =>
        navigator.clipboard
          .writeText(value)
          .then(() => setState("copied"))
          .catch(() => setState("failed"))
      }
    >
      {value}
      <small>{state === "copied" ? "Copied" : state === "failed" ? "Could not copy" : "Copy"}</small>
    </button>
  );
}

export function PaymentSuccess({
  open,
  onClose,
  credits,
  balance,
  orderId,
  amount,
  currency,
  method,
  footnote,
}: {
  open: boolean;
  onClose: () => void;
  credits: number;
  balance: number;
  orderId: string;
  amount?: string;
  currency?: string;
  /** How it was paid, in words: "PayPal sandbox, test money". */
  method: string;
  footnote?: string;
}) {
  const reduced = useReducedMotion();
  const shownCredits = useCountUp(credits, { delay: 0.45 });
  const shownBalance = useCountUp(balance, { from: Math.max(balance - credits, 0), delay: 0.6 });

  return (
    <GlassDialog open={open} onClose={onClose} label="Payment successful" className="paid-card">
      <motion.div
        className="paid-badge"
        role="status"
        initial={{ opacity: 0, y: 18, scale: 0.6 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 380, damping: 17, delay: 0.5 }}
      >
        <span aria-hidden="true" className="paid-badge-dot" />
        Payment successful
      </motion.div>

      <div className="paid-mark" aria-hidden="true">
        {!reduced && (
          <>
            <i className="paid-ripple" />
            <i className="paid-ripple" style={{ animationDelay: "0.75s" }} />
          </>
        )}
        <svg viewBox="0 0 96 96" width="96" height="96" fill="none">
          <motion.circle
            cx="48"
            cy="48"
            r="42"
            stroke="currentColor"
            strokeWidth="5"
            strokeLinecap="round"
            initial={{ pathLength: reduced ? 1 : 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.6, ease: DRAW }}
          />
          <motion.path
            d="M30 50 L43 63 L67 36"
            stroke="currentColor"
            strokeWidth="7"
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={{ pathLength: reduced ? 1 : 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.34, ease: "easeOut", delay: 0.48 }}
          />
        </svg>
      </div>
      <div className="paid-burst" aria-hidden="true">
        <Burst />
      </div>

      <h2 className="paid-title">
        <span className="num">+{shownCredits}</span> credits
      </h2>
      <p className="paid-balance">
        You now have <strong className="num">{shownBalance}</strong> {balance === 1 ? "credit" : "credits"}.
      </p>

      <dl className="receipt">
        {amount && <Row index={0} label="Paid" value={`${currency ?? ""} ${amount}`.trim()} />}
        <Row index={1} label="Method" value={method} />
        <Row index={2} label="Order" value={<CopyOrder value={orderId} />} />
      </dl>

      <motion.div
        className="paid-actions"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1, duration: 0.34 }}
      >
        <Link href="/upload" className="btn btn-primary">
          Analyse a call
          <IconArrow size={13} />
        </Link>
        <Link href="/billing" className="btn btn-ghost" onClick={onClose}>
          See my credits
        </Link>
      </motion.div>
      {footnote && <div className="paid-footnote">{footnote}</div>}
    </GlassDialog>
  );
}
