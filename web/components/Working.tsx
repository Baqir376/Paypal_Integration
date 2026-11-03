"use client";

/**
 * What someone watches while Salix is working, so a long wait feels like work
 * being done and not like a frozen page.
 *
 * WorkingScene is for requests that report nothing until they finish. Its steps say
 * what the work involves and move on a clock, so nothing here may claim a step is
 * done, and there is no percentage: the only measured thing on it is the timer.
 *
 * PipelineProgress is for the upload, where the server reports each stage, so its
 * bar is the real count.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

import { Mark } from "@/components/Mark";

/** Fixed heights from a formula, so the server and the browser draw the same wave. */
const BARS = Array.from({ length: 32 }, (_, i) => {
  const voice = Math.abs(Math.sin(i * 0.61) * Math.cos(i * 0.23) + 0.45 * Math.sin(i * 1.3));
  return Math.round(18 + Math.min(voice, 1) * 82);
});

const STEP_SECONDS = 4.5;
const LONG_WAIT_SECONDS = 30;

function useElapsed() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);
  return elapsed;
}

function clock(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function Voice() {
  return (
    <div className="working-voice" aria-hidden="true">
      {BARS.map((height, index) => (
        <i key={index} style={{ height: `${height}%`, animationDelay: `${-(index * 0.11).toFixed(2)}s` }} />
      ))}
    </div>
  );
}

export function WorkingScene({ title, steps }: { title: string; steps: string[] }) {
  const reduced = useReducedMotion();
  const elapsed = useElapsed();
  // Holds on the last step rather than looping, which would look like starting over.
  const current = Math.min(Math.floor(elapsed / STEP_SECONDS), steps.length - 1);

  return (
    <motion.div
      className="working no-print"
      role="status"
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 240, damping: 24 }}
    >
      <div className="working-mark" aria-hidden="true">
        <i className="working-ring" />
        <i className="working-ring working-ring-b" />
        <Mark size={26} />
      </div>
      <div className="working-title">{title}</div>
      <Voice />
      <div className="working-now">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={current}
            initial={reduced ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduced ? undefined : { opacity: 0, y: -12 }}
            transition={{ duration: 0.28 }}
          >
            {steps[current]}
          </motion.div>
        </AnimatePresence>
      </div>
      <ol className="working-steps" aria-hidden="true">
        {steps.map((step, index) => (
          <li key={step} data-state={index === current ? "now" : index < current ? "past" : "next"} />
        ))}
      </ol>
      <div className="working-foot num">
        {clock(elapsed)}
        {elapsed >= LONG_WAIT_SECONDS && <span> · still working, thanks for waiting</span>}
      </div>
    </motion.div>
  );
}

/** The real count of finished stages, from the server's own events. */
export function PipelineProgress({
  finished,
  total,
  current,
  agent,
  active,
  totalMs,
}: {
  finished: number;
  total: number;
  /** The stage running now, if one is. */
  current?: string;
  agent?: string;
  /** Whether the run is still going. */
  active: boolean;
  /** How long the finished run took, as the server measured it. */
  totalMs?: number;
}) {
  const elapsed = useElapsed();
  return (
    <div className="pipe" role="status">
      <div className="pipe-row">
        <div className="pipe-now">
          <AnimatePresence mode="wait" initial={false}>
            <motion.strong
              key={current ?? (active ? "starting" : "finished")}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.22 }}
            >
              {current ?? (active ? "Getting started" : "Finished")}
            </motion.strong>
          </AnimatePresence>
          {agent && current && <small>{agent}</small>}
        </div>
        <div className="pipe-count num">
          {finished} of {total}
          {active && <span> · {clock(elapsed)}</span>}
          {!active && !!totalMs && <span> · {Math.round(totalMs / 1000)}s in all</span>}
        </div>
      </div>
      <div className="pipe-track">
        <motion.i
          initial={{ width: 0 }}
          animate={{ width: `${(finished / total) * 100}%` }}
          transition={{ type: "spring", stiffness: 90, damping: 20 }}
        />
      </div>
      {active && <Voice />}
    </div>
  );
}
