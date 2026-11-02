"use client";

/**
 * A new team's first screen.
 *
 * A dashboard of zeros tells somebody nothing and looks broken. Until there is a call
 * to measure, this says what to do first, and ticks itself off as it happens.
 */

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";

import { IconArrow, IconCheck } from "@/components/icons";
import { api } from "@/lib/api";
import type { BillingState } from "@/lib/types";

const EASE = [0.16, 1, 0.3, 1] as const;

export function FirstRun({ teamSize }: { teamSize: number }) {
  const [billing, setBilling] = useState<BillingState | null>(null);
  /** Only one step's explanation shows at a time: the current one, until another is chosen. */
  const [opened, setOpened] = useState<number | null>(null);

  useEffect(() => {
    api.billing().then(setBilling).catch(() => setBilling(null));
  }, []);

  const needsCredits = !!billing?.enforced;
  const hasCredits = !!billing && billing.balance > 0;

  const steps = [
    ...(needsCredits
      ? [
          {
            title: "Add credits",
            body: "Each recording uses one, and a failed analysis gives it back.",
            href: "/billing",
            action: "Buy credits",
            done: hasCredits,
          },
        ]
      : []),
    {
      title: "Upload your first call",
      body: "Type whose call it is and drop the file. The language is detected for you.",
      href: "/upload",
      action: "Analyse a call",
      done: false,
    },
    {
      title: "Read the coaching plan",
      body: "If the deal score is low, a plan is written about that call's weakest skills.",
      done: false,
    },
    {
      title: "Test yourself",
      body: "Roleplay against a buyer who only commits once you have shown those skills.",
      done: false,
    },
  ];
  const current = steps.findIndex((step) => !step.done);
  const showing = opened ?? current;

  return (
    <section className="first-run">
      {steps.map((step, index) => (
        <motion.div
          key={step.title}
          className="first-run-step"
          data-state={step.done ? "done" : index === current ? "current" : "later"}
          initial={{ opacity: 0, y: 18, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 320, damping: 24, delay: 0.07 * index }}
          onClick={() => setOpened(index)}
        >
          <span className="first-run-marker" aria-hidden="true">
            {step.done ? <IconCheck size={13} /> : index + 1}
          </span>
          <div className="first-run-text">
            <strong>{step.title}</strong>
            <AnimatePresence initial={false}>
              {showing === index && (
                <motion.p
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.3, ease: EASE }}
                  style={{ overflow: "hidden" }}
                >
                  {step.body}
                </motion.p>
              )}
            </AnimatePresence>
          </div>
          {step.href && !step.done && (
            <Link href={step.href} className={index === current ? "btn btn-primary btn-sm" : "btn btn-sm"}>
              {step.action}
              <IconArrow size={11} />
            </Link>
          )}
        </motion.div>
      ))}
      {teamSize === 0 && (
        <p className="first-run-note">
          Salespeople are added as you upload, or you can{" "}
          <Link href="/team">add your team now</Link>.
        </p>
      )}
    </section>
  );
}
