"use client";

/**
 * Pinned chapter slides.
 *
 * A track as tall as its slide count, with a viewport-height stage pinned
 * inside it. As the reader scrolls the track, the stage stays put and the
 * slides cross over; each plate drifts against the movement so the depth is
 * real rather than implied.
 *
 * Pinning is the one effect on the site that takes the scroll away from the
 * reader, so it is bounded: the pin is exactly as long as the content it is
 * holding, `anticipatePin` stops the one-frame jump at the moment of capture,
 * and under reduced motion the whole thing unpins into a plain stack of
 * sections. Nothing is hidden behind the gesture.
 */

import { useEffect, useRef, useState } from "react";

import { getEngine, prefersReducedMotion } from "@/lib/motion";

export type Slide = {
  chapter: string;
  eyebrow: string;
  title: string;
  body: string;
  bullets: string[];
  plate: string;
};

export function ChapterSlides({ slides }: { slides: Slide[] }) {
  const track = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);

  /**
   * With the pin disabled there is nothing to advance the active index, so
   * every slide has to count as active or three quarters of the section stays
   * at `opacity: 0` forever. The CSS cannot fix this on its own -- `active`
   * drives inline styles, and inline styles beat a media query.
   */
  const [allActive, setAllActive] = useState(false);

  useEffect(() => {
    const trackNode = track.current;
    const stageNode = stage.current;
    if (!trackNode || !stageNode) return;
    if (prefersReducedMotion()) {
      setAllActive(true);
      return;
    }

    let trigger: { kill: () => void } | null = null;
    let cancelled = false;

    getEngine().then(({ ScrollTrigger }) => {
      if (cancelled) return;

      trigger = ScrollTrigger.create({
        trigger: trackNode,
        start: "top top",
        end: () => `+=${slides.length * 90}%`,
        pin: stageNode,
        pinSpacing: true,
        // Without this the pin engages one frame late at speed and the stage
        // visibly hops as it is captured.
        anticipatePin: 1,
        onUpdate: (self) => {
          const index = Math.min(
            slides.length - 1,
            Math.floor(self.progress * slides.length),
          );
          setActive((current) => (current === index ? current : index));
        },
      });
    });

    return () => {
      cancelled = true;
      trigger?.kill();
    };
  }, [slides.length]);

  return (
    <div className="sx-pin-track" ref={track}>
      <div className="sx-pin-stage" ref={stage}>
        {slides.map((slide, index) => (
          <SlidePanel
            key={slide.chapter}
            slide={slide}
            active={allActive || index === active}
          />
        ))}

        {/* The counter and the progress bar describe a position within a pin.
            Unpinned, they describe nothing. */}
        {!allActive && (
          <>
            <div className="sx-pin-counter" aria-hidden="true">
              <span className="sx-pin-counter-now">
                {String(active + 1).padStart(2, "0")}
              </span>
              <span className="sx-pin-counter-all">
                / {String(slides.length).padStart(2, "0")}
              </span>
            </div>

            <div className="sx-pin-bar" aria-hidden="true">
              <i style={{ scale: `${(active + 1) / slides.length} 1` }} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function SlidePanel({ slide, active }: { slide: Slide; active: boolean }) {
  const plate = useRef<HTMLDivElement>(null);

  // The plate drifts while its slide is the active one. Driven from a class
  // rather than a tween because it is a loop, not a scrub, and a CSS
  // animation on a composited property costs nothing per frame.
  return (
    <section
      className="sx-slide"
      data-active={active}
      aria-hidden={!active}
      style={{
        transition: "opacity 900ms var(--ease-luxury)",
      }}
    >
      <div
        ref={plate}
        className="sx-slide-plate"
        style={{
          backgroundImage: `var(${slide.plate})`,
          transform: active ? "scale(1.04)" : "scale(1.14)",
          transition: "transform 2400ms var(--ease-luxury)",
        }}
        aria-hidden="true"
      />

      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 22 }}>
          <span className="sx-bracket">{slide.chapter}</span>
          <span className="sx-tag sx-tag-gold">{slide.eyebrow}</span>
        </div>

        <h3
          className="sx-display sx-d2"
          style={{
            translate: active ? "none" : "0 18px",
            opacity: active ? 1 : 0,
            transition:
              "translate 900ms var(--ease-luxury) 90ms, opacity 700ms var(--ease-luxury) 90ms",
          }}
        >
          {slide.title}
        </h3>

        <p className="sx-lede" style={{ marginTop: 20, maxWidth: "44ch" }}>
          {slide.body}
        </p>
      </div>

      <div className="sx-slide-figure">
        <ul className="sx-slide-bullets">
          {slide.bullets.map((bullet, index) => (
            <li
              key={bullet}
              style={{
                translate: active ? "none" : "0 14px",
                opacity: active ? 1 : 0,
                transition: `translate 760ms var(--ease-luxury) ${160 + index * 70}ms, opacity 620ms var(--ease-luxury) ${160 + index * 70}ms`,
              }}
            >
              {bullet}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
