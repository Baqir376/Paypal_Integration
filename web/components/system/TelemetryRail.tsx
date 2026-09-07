"use client";

/**
 * The CRT telemetry rail.
 *
 * A fixed vertical readout down the left edge, alternating a live bit stream
 * with the wordmark. It is decoration with a job: it establishes, before a
 * single word of copy is read, that this is an instrument that measures things
 * — which is the entire claim the product makes.
 *
 * The stream is genuinely regenerated rather than looped through a fixed
 * string, so no two glances at it are identical. It updates on a timer at a
 * deliberately unhurried cadence: a counter spinning at 60fps in peripheral
 * vision is an irritant, and this sits beside body copy people are reading.
 */

import { useEffect, useState } from "react";

import { prefersReducedMotion } from "@/lib/motion";

/** Spaced-out letters, the way a readout renders a label. */
const WORDMARK = "S A L I X   E N G I N E";

function bits(length: number): string {
  let out = "";
  for (let i = 0; i < length; i++) out += Math.random() < 0.5 ? "0" : "1";
  return out;
}

export function TelemetryRail() {
  /* Seeded deterministically. The server and the first client render must
     agree character for character, and Math.random() on both sides of a
     hydration boundary is a guaranteed mismatch -- the stream only starts
     moving once the effect below has run, which is client-only by definition. */
  const [frame, setFrame] = useState(`1010 ${WORDMARK}`);

  useEffect(() => {
    if (prefersReducedMotion()) return;

    let alternate = false;
    const timer = setInterval(() => {
      alternate = !alternate;
      setFrame(
        alternate
          ? `${bits(4)} ${WORDMARK} ${bits(4)}`
          : `${bits(8)} ${WORDMARK}`,
      );
    }, 900);

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="sx-rail no-print" aria-hidden="true">
      <span className="sx-rail-cap sx-rail-cap-top" />
      <div className="sx-rail-stream">[ {frame} ]</div>
      <span className="sx-rail-cap sx-rail-cap-bottom" />
    </div>
  );
}
