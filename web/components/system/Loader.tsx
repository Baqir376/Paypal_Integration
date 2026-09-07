"use client";

/**
 * The master preloader.
 *
 * A numeric counter to 100 behind a dual curtain that parts from the middle.
 * Two rules keep it from being a tax on the reader:
 *
 *   1. It never blocks. `pointer-events: none` throughout, and the page
 *      underneath is live and scrollable the entire time — if someone starts
 *      reading before it lifts, nothing stops them.
 *   2. It is shown once per session, not once per navigation. A curtain on
 *      every route change is a loading screen wearing a costume.
 *
 * The count is eased rather than linear, so it hesitates in the nineties the
 * way a real progress figure does instead of sweeping at a constant rate.
 */

import { useEffect, useState } from "react";

import { prefersReducedMotion } from "@/lib/motion";

const SEEN_KEY = "salix-intro-seen";

export function Loader() {
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(true);

  useEffect(() => {
    let seen = true;
    try {
      seen = sessionStorage.getItem(SEEN_KEY) === "1";
    } catch {
      /* private mode; treat as seen and skip rather than repeat every load */
    }
    if (seen || prefersReducedMotion()) return;

    setDone(false);
    try {
      sessionStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* nothing to do; the curtain simply plays again next time */
    }

    const DURATION = 1600;
    const start = performance.now();
    let frame = 0;

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION);
      const eased = 1 - Math.pow(1 - t, 3);
      setCount(Math.round(eased * 100));
      if (t < 1) {
        frame = requestAnimationFrame(tick);
      } else {
        setOpen(true);
        // Matches the curtain transition, so the node leaves the tree the
        // frame after it finishes rather than lingering over the page.
        window.setTimeout(() => setDone(true), 1250);
      }
    };
    frame = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(frame);
  }, []);

  if (done) return null;

  return (
    <div className={`sx-loader no-print${open ? " is-open" : ""}`} aria-hidden="true">
      <div className="sx-loader-half sx-loader-half-top" />
      <div className="sx-loader-half sx-loader-half-bottom" />

      <div className="sx-loader-center">
        <div className="sx-tag sx-tag-gold">[ SALIX · CONVERSATION INTELLIGENCE ]</div>
        <div className="sx-loader-count">
          {String(count).padStart(3, "0")}
          <sup>%</sup>
        </div>
        <div className="sx-loader-track">
          <i style={{ scale: `${count / 100} 1` }} />
        </div>
        <div className="sx-tag">
          {count < 40
            ? "MOUNTING METRICS ENGINE"
            : count < 78
              ? "HYDRATING CITATIONS"
              : "INDEXING MOMENTS"}
        </div>
      </div>
    </div>
  );
}
