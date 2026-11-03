"use client";

/**
 * The app's living surroundings and its side panels.
 *
 * Everything drawn here is either decoration, marked aria-hidden, or the caller's
 * real data. Nothing invents a number to fill a space.
 */

import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useId } from "react";

import { IconCheck } from "@/components/icons";

/** Slow colour behind the whole app. Its hues come from the tab, through data-tab on the shell. */
export function StudioBackdrop() {
  return (
    <div className="studio-backdrop no-print" aria-hidden="true">
      <i className="studio-orb studio-orb-a" />
      <i className="studio-orb studio-orb-b" />
      <i className="studio-orb studio-orb-c" />
      <i className="studio-lines" />
    </div>
  );
}

export function SideCard({
  title,
  hint,
  index = 0,
  children,
}: {
  title: string;
  hint?: string;
  index?: number;
  children: React.ReactNode;
}) {
  return (
    <motion.section
      className="side-card"
      initial={{ opacity: 0, x: 26, scale: 0.97 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 220, damping: 24, delay: 0.12 + index * 0.1 }}
    >
      <header className="side-card-head">
        <h2>{title}</h2>
        {hint && <span>{hint}</span>}
      </header>
      {children}
    </motion.section>
  );
}

/** Steps with a light that walks down them, showing the order things happen in. */
export function JourneySteps({ steps }: { steps: { label: string; detail?: string }[] }) {
  return (
    <ol className="journey" style={{ "--journey-steps": steps.length } as React.CSSProperties}>
      {steps.map((step, index) => (
        <li key={step.label} style={{ "--journey-index": index } as React.CSSProperties}>
          <span className="journey-dot num" aria-hidden="true">
            {index + 1}
          </span>
          <div>
            <strong>{step.label}</strong>
            {step.detail && <small>{step.detail}</small>}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function CheckList({ items }: { items: string[] }) {
  return (
    <ul className="side-checks">
      {items.map((item, index) => (
        <motion.li
          key={item}
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.34, delay: 0.5 + index * 0.09 }}
        >
          <span aria-hidden="true">
            <IconCheck size={11} />
          </span>
          {item}
        </motion.li>
      ))}
    </ul>
  );
}

/** Labelled bars that grow in. The widths are shares of the largest value. */
export function BarList({ items }: { items: { label: string; value: number; href?: string; top?: boolean }[] }) {
  const largest = Math.max(1, ...items.map((item) => item.value));
  return (
    <ul className="bar-list">
      {items.map((item, index) => (
        <li key={item.label}>
          <div className="bar-list-row">
            {item.href ? <Link href={item.href}>{item.label}</Link> : <span>{item.label}</span>}
            <b className="num">{item.value}</b>
          </div>
          <div className="bar-list-track">
            <motion.i
              data-top={item.top || undefined}
              initial={{ width: 0 }}
              animate={{ width: `${(item.value / largest) * 100}%` }}
              transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: 0.3 + index * 0.07 }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Three small facts in a row. */
export function FactRow({ facts }: { facts: { label: string; value: React.ReactNode }[] }) {
  return (
    <dl className="fact-row">
      {facts.map((fact) => (
        <div key={fact.label}>
          <dd className="num">{fact.value}</dd>
          <dt>{fact.label}</dt>
        </div>
      ))}
    </dl>
  );
}

const CHART = { width: 280, height: 104, pad: 8 };

/**
 * The balance over time, worked backwards from today's balance through the ledger,
 * so it stays true even when the history is only the most recent entries.
 */
export function BalanceTrend({
  balance,
  history,
}: {
  balance: number;
  history: { delta: number; created_at: string }[];
}) {
  const gradient = useId();
  const reduced = useReducedMotion();
  const newestFirst = [...history].sort((a, b) => b.created_at.localeCompare(a.created_at));

  if (newestFirst.length === 0) {
    return <p className="side-empty">Your first purchase starts this line.</p>;
  }

  const levels = [balance];
  for (const entry of newestFirst) levels.push(levels[levels.length - 1] - entry.delta);
  levels.reverse();

  const top = Math.max(1, ...levels);
  const bottom = Math.min(0, ...levels);
  const span = Math.max(top - bottom, 1);
  const x = (index: number) => CHART.pad + (index / (levels.length - 1)) * (CHART.width - CHART.pad * 2);
  const y = (level: number) => CHART.height - CHART.pad - ((level - bottom) / span) * (CHART.height - CHART.pad * 2);

  // A ledger moves in steps, so the line does too.
  let line = `M ${x(0)} ${y(levels[0])}`;
  levels.slice(1).forEach((level, index) => {
    line += ` H ${x(index + 1)} V ${y(level)}`;
  });
  const area = `${line} V ${CHART.height} H ${x(0)} Z`;
  const bought = history.filter((entry) => entry.delta > 0).reduce((sum, entry) => sum + entry.delta, 0);
  const used = history.filter((entry) => entry.delta < 0).reduce((sum, entry) => sum - entry.delta, 0);

  return (
    <>
      <svg
        className="trend"
        viewBox={`0 0 ${CHART.width} ${CHART.height}`}
        role="img"
        aria-label={`Balance over the last ${newestFirst.length} changes, now ${balance}`}
      >
        <defs>
          <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--tab-a)" stopOpacity="0.45" />
            <stop offset="1" stopColor="var(--tab-a)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <motion.path
          d={area}
          fill={`url(#${gradient})`}
          initial={{ opacity: reduced ? 1 : 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.7 }}
        />
        <motion.path
          d={line}
          fill="none"
          stroke="var(--tab-line)"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: reduced ? 1 : 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.2, ease: [0.65, 0, 0.35, 1], delay: 0.25 }}
        />
        <circle className="trend-now" cx={x(levels.length - 1)} cy={y(balance)} r="4.5" fill="var(--tab-line)" />
      </svg>
      <FactRow
        facts={[
          { label: "bought", value: `+${bought}` },
          { label: "used", value: used },
          { label: "now", value: balance },
        ]}
      />
    </>
  );
}
