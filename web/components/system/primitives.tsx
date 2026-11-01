"use client";

/**
 * Scroll-driven primitives.
 *
 * Everything here obeys the same three rules as the rest of the motion in the
 * app: reveals fire once and never re-run on scroll-back, damping is
 * frame-rate independent, and `prefers-reduced-motion` renders the *finished*
 * state rather than a faster animation.
 *
 * Where GSAP is genuinely needed — pinning, scrubbing, velocity — it is used.
 * Where a CSS class toggled by an IntersectionObserver does the same job, that
 * is used instead, because it composites on the GPU and costs no JavaScript
 * per frame.
 */

import { useEffect, useId, useRef, useState } from "react";

import { getEngine, prefersReducedMotion, splitWords } from "@/lib/motion";

/* --------------------------------------------------------------------------
 * Word reveal
 * ----------------------------------------------------------------------- */

/**
 * A headline that assembles itself word by word, out of a line mask.
 *
 * The stagger is scrubbed by scroll velocity. Arrive at a headline slowly and
 * the words are dealt out with air between them; hit it at speed and they
 * land almost together. Without this, a fast scroll leaves the reader looking
 * at a headline that is still assembling half a second after they stopped —
 * the animation stops describing the page and starts holding it up.
 */
export function RevealWords({
  text,
  as: Tag = "span",
  className,
  delay = 0,
  style,
}: {
  text: string;
  as?: "h1" | "h2" | "h3" | "p" | "span" | "div";
  className?: string;
  delay?: number;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLElement>(null);
  const words = splitWords(text);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const targets = Array.from(node.querySelectorAll<HTMLElement>(".reveal-word"));
    if (prefersReducedMotion()) {
      targets.forEach((word) => word.classList.add("is-in"));
      return;
    }

    let trigger: { kill: () => void } | null = null;
    let cancelled = false;
    const timers: number[] = [];

    getEngine().then(({ ScrollTrigger }) => {
      if (cancelled) return;

      trigger = ScrollTrigger.create({
        trigger: node,
        start: "top 88%",
        once: true,
        onEnter: (self) => {
          // getVelocity is px/second and signed. A slow read is a few hundred;
          // a flung trackpad is several thousand. Compressing the stagger
          // toward zero across that range is the whole effect.
          const speed = Math.abs(self.getVelocity());
          const step = Math.max(14, 62 - speed / 42);

          targets.forEach((word, index) => {
            timers.push(
              window.setTimeout(
                () => word.classList.add("is-in"),
                delay + index * step,
              ),
            );
          });
        },
      });
    });

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
      trigger?.kill();
    };
  }, [text, delay]);

  return (
    <Tag
      ref={ref as React.Ref<never>}
      className={className}
      style={style}
      aria-label={text}
      // A plain span or div may not carry a label on its own.
      role={Tag === "span" || Tag === "div" || Tag === "p" ? "group" : undefined}
    >
      {/* The words are hidden from assistive technology and the whole string
          is announced once from the wrapper, so a screen reader hears a
          sentence rather than a list of words. */}
      <span className="reveal-line" aria-hidden="true">
        {words.map((word, index) => (
          <span className="reveal-word" key={`${word}-${index}`}>
            {word}
            {index < words.length - 1 ? " " : ""}
          </span>
        ))}
      </span>
    </Tag>
  );
}

/**
 * A paragraph whose words come up from dim to full as it crosses the viewport.
 *
 * Scrubbed rather than triggered: the reader controls the pace, which is what
 * makes the statement feel read rather than played. No lift — a paragraph that
 * moves while you are trying to read it is a paragraph you read twice.
 */
export function FadeWords({
  text,
  className,
  style,
}: {
  text: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLParagraphElement>(null);
  const words = splitWords(text);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const targets = Array.from(node.querySelectorAll<HTMLElement>(".fade-word"));
    if (prefersReducedMotion()) {
      targets.forEach((word) => word.classList.add("is-in"));
      return;
    }

    let trigger: { kill: () => void } | null = null;
    let cancelled = false;

    getEngine().then(({ ScrollTrigger }) => {
      if (cancelled) return;
      trigger = ScrollTrigger.create({
        trigger: node,
        start: "top 78%",
        end: "bottom 58%",
        onUpdate: (self) => {
          // One extra word's worth of lead, so the last word is lit before the
          // section leaves rather than exactly as it does.
          const lit = Math.round(self.progress * (targets.length + 2));
          targets.forEach((word, index) =>
            word.classList.toggle("is-in", index < lit),
          );
        },
      });
    });

    return () => {
      cancelled = true;
      trigger?.kill();
    };
  }, [text]);

  return (
    <p ref={ref} className={className} style={style} aria-label={text} role="group">
      <span aria-hidden="true">
        {words.map((word, index) => (
          <span className="fade-word" key={`${word}-${index}`}>
            {word}
            {index < words.length - 1 ? " " : ""}
          </span>
        ))}
      </span>
    </p>
  );
}

/* --------------------------------------------------------------------------
 * Parallax
 * ----------------------------------------------------------------------- */

/**
 * Drift an element against the scroll.
 *
 * Applied to background plates only. Parallax on content is a readability tax:
 * the text is moving at a different speed to the thing the reader is using to
 * track their place on the page.
 */
export function useParallax<T extends HTMLElement>(distance = 120) {
  const ref = useRef<T>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || prefersReducedMotion()) return;

    let tween: { kill: () => void } | null = null;
    let cancelled = false;

    getEngine().then(({ gsap }) => {
      if (cancelled) return;
      tween = gsap.fromTo(
        node,
        { yPercent: -distance / 20 },
        {
          yPercent: distance / 20,
          ease: "none",
          scrollTrigger: {
            trigger: node.parentElement ?? node,
            start: "top bottom",
            end: "bottom top",
            scrub: true,
          },
        },
      );
    });

    return () => {
      cancelled = true;
      tween?.kill();
    };
  }, [distance]);

  return ref;
}

export function Parallax({
  distance = 120,
  className,
  style,
}: {
  distance?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  const ref = useParallax<HTMLDivElement>(distance);
  return <div ref={ref} className={className} style={style} aria-hidden="true" />;
}

/* --------------------------------------------------------------------------
 * Progress
 * ----------------------------------------------------------------------- */

/**
 * Writes an element's travel through the viewport to `--progress`.
 *
 * A custom property rather than React state: this updates on every scroll
 * frame, and re-rendering a subtree that often to move one hairline is the
 * difference between a page that glides and one that stutters.
 */
export function useProgress<T extends HTMLElement>() {
  const ref = useRef<T>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (prefersReducedMotion()) {
      node.style.setProperty("--progress", "1");
      return;
    }

    let trigger: { kill: () => void } | null = null;
    let cancelled = false;

    getEngine().then(({ ScrollTrigger }) => {
      if (cancelled) return;
      trigger = ScrollTrigger.create({
        trigger: node,
        start: "top 70%",
        end: "bottom 70%",
        onUpdate: (self) =>
          node.style.setProperty("--progress", self.progress.toFixed(4)),
      });
    });

    return () => {
      cancelled = true;
      trigger?.kill();
    };
  }, []);

  return ref;
}

/* --------------------------------------------------------------------------
 * Counter
 * ----------------------------------------------------------------------- */

/**
 * A figure that counts up the first time it is seen.
 *
 * `format` runs every frame, so the number animates in the shape it is finally
 * read in — a percentage, a duration, a count. Before it has been seen, and
 * always under reduced motion, the final value is what renders: the number is
 * the content, and content does not wait on an effect.
 */
export function Count({
  value,
  duration = 1400,
  format = (v: number) => String(Math.round(v)),
  className,
}: {
  value: number;
  duration?: number;
  format?: (value: number) => string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);
  const started = useRef(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || started.current) return;
    if (prefersReducedMotion() || typeof IntersectionObserver === "undefined") {
      setShown(value);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || started.current) return;
        started.current = true;
        observer.disconnect();

        let frame = 0;
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min(1, (now - start) / duration);
          // The same ease-out as everything else, so a number lands the way a
          // panel does.
          setShown(value * (1 - Math.pow(1 - t, 3)));
          if (t < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
        cleanup = () => cancelAnimationFrame(frame);
      },
      { threshold: 0.2 },
    );

    let cleanup = () => {};
    observer.observe(node);
    return () => {
      observer.disconnect();
      cleanup();
    };
  }, [value, duration]);

  return (
    <span ref={ref} className={className}>
      {format(shown)}
    </span>
  );
}

/* --------------------------------------------------------------------------
 * The seal
 * ----------------------------------------------------------------------- */

/**
 * A rotating circular seal set on an SVG textPath.
 *
 * Used at most once per page. It is a maker's mark, and a second one on the
 * same screen turns it into decoration.
 */
export function Seal({
  text = "SALIX · MEASURED NOT INFERRED · EVERY CLAIM CITED · ",
  size = 116,
}: {
  text?: string;
  size?: number;
}) {
  // useId rather than a random string: the server and the client have to agree
  // on the fragment the textPath points at, and Math.random() cannot.
  const pathId = `seal-${useId().replace(/:/g, "")}`;

  return (
    <svg
      className="sx-seal"
      width={size}
      height={size}
      viewBox="0 0 120 120"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <path
          id={pathId}
          fill="none"
          d="M60,60 m-44,0 a44,44 0 1,1 88,0 a44,44 0 1,1 -88,0"
        />
      </defs>
      <circle cx="60" cy="60" r="52" fill="none" stroke="var(--line)" />
      <circle cx="60" cy="60" r="30" fill="none" stroke="var(--accent-gold-dim)" opacity="0.5" />
      <text>
        <textPath href={`#${pathId}`}>{text}</textPath>
      </text>
    </svg>
  );
}
