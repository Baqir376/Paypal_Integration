"use client";

/**
 * A horizontal chapter run.
 *
 * The section pins and the track travels sideways under it, scrubbed by
 * vertical scroll. Used where the content is genuinely a sequence with no
 * natural stopping point — a service manifest, a set of eras — because that is
 * the only case where taking the scroll direction away from the reader buys
 * anything.
 *
 * Two things keep it honest:
 *
 *   1. The travel distance is measured from the real track width on every
 *      refresh, so adding a card lengthens the pin rather than cutting the
 *      last card off the end.
 *   2. Under reduced motion — and on a narrow screen, where a sideways pin is
 *      a fight with the browser's own gesture — it becomes a normal horizontal
 *      scroller the reader drags themselves.
 */

import { useEffect, useRef } from "react";

import { getEngine, prefersReducedMotion } from "@/lib/motion";

export function HorizontalRun({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const section = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sectionNode = section.current;
    const trackNode = track.current;
    if (!sectionNode || !trackNode) return;
    if (prefersReducedMotion() || window.innerWidth < 900) return;

    let tween: { kill: () => void; scrollTrigger?: { kill: () => void } } | null = null;
    let cancelled = false;

    getEngine().then(({ gsap }) => {
      if (cancelled) return;

      const distance = () =>
        Math.max(0, trackNode.scrollWidth - sectionNode.clientWidth);

      tween = gsap.to(trackNode, {
        x: () => -distance(),
        ease: "none",
        scrollTrigger: {
          trigger: sectionNode,
          start: "top top",
          // Pin for exactly as far as the track has to travel, so the run
          // ends the moment the last card is flush with the right edge.
          end: () => `+=${distance()}`,
          pin: true,
          scrub: 0.6,
          anticipatePin: 1,
          invalidateOnRefresh: true,
        },
      });
    });

    return () => {
      cancelled = true;
      tween?.scrollTrigger?.kill();
      tween?.kill();
    };
  }, []);

  return (
    <div ref={section} className={`sx-run${className ? ` ${className}` : ""}`}>
      {/* The overflow rule lives in CSS rather than inline, because the
          fallback -- a plain draggable scroller on a narrow screen or under
          reduced motion -- is a media query, and a media query cannot
          override an inline style. */}
      <div ref={track} className="sx-run-track">
        {children}
      </div>
    </div>
  );
}
