"use client";

/**
 * Page motion.
 *
 * Every primitive here follows the same three rules, and they are the whole
 * reason this is a file rather than a scattering of inline transitions:
 *
 *   1. Nothing animates that a reader did not ask to see. Reveals fire once on
 *      entry, never again on scroll-back -- re-animating on every pass is what
 *      makes a site feel like a demo reel rather than a document.
 *   2. Motion is damped toward a target, never snapped, and damping is
 *      frame-rate independent so a 144Hz screen feels like a 60Hz one.
 *   3. `prefers-reduced-motion` is honoured by rendering the *finished* state
 *      immediately, not by shortening the animation. A counter shows its
 *      number, split text shows its sentence, a tilt sits flat. Motion sickness
 *      is a real condition and a fast animation is still an animation.
 *
 * Pointer-driven pieces also stand down on coarse pointers: there is no cursor
 * to follow on a phone, and the listener would be pure cost.
 */

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/* --------------------------------------------------------------------------
 * Shared
 * ----------------------------------------------------------------------- */

const EASE = "cubic-bezier(0.16, 1, 0.3, 1)";

function reducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function finePointer(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(pointer: fine)").matches;
}

/**
 * True once the element has been seen. One-shot by design: the observer
 * disconnects on the first intersection.
 */
function useSeen<T extends HTMLElement>(rootMargin = "0px 0px -12% 0px") {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (typeof IntersectionObserver === "undefined" || reducedMotion()) {
      setSeen(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true);
          observer.disconnect();
        }
      },
      { rootMargin, threshold: 0.05 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [rootMargin]);

  return { ref, seen };
}

/* --------------------------------------------------------------------------
 * Smooth scroll
 * ----------------------------------------------------------------------- */

/**
 * Weighted scrolling.
 *
 * Scroll weight is one of the clearest signals separating a considered site
 * from a default one, and it is almost entirely a feel decision -- a short lerp
 * reads as sluggish, a long one as drifting. These values land a wheel notch in
 * roughly a fifth of a second with a soft stop.
 */
export function SmoothScroll() {
  useEffect(() => {
    if (reducedMotion()) return;

    let lenis: { raf: (t: number) => void; destroy: () => void } | null = null;
    let frame = 0;
    let cancelled = false;

    // Imported lazily so the scroll library never lands in the critical path
    // for a page that may not scroll at all.
    import("lenis").then(({ default: Lenis }) => {
      if (cancelled) return;
      lenis = new Lenis({
        duration: 1.05,
        // Exponential ease-out: fast pickup, long settle.
        easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        wheelMultiplier: 0.95,
        touchMultiplier: 1.6,
        // Touch devices already have momentum scrolling that feels right;
        // layering ours on top makes them fight.
        syncTouch: false,
      });

      const raf = (time: number) => {
        lenis?.raf(time);
        frame = requestAnimationFrame(raf);
      };
      frame = requestAnimationFrame(raf);
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      lenis?.destroy();
    };
  }, []);

  return null;
}

/* --------------------------------------------------------------------------
 * Reveal
 * ----------------------------------------------------------------------- */

export type RevealVariant = "rise" | "fade" | "scale" | "blur" | "left" | "right";

const HIDDEN: Record<RevealVariant, string> = {
  rise: "translateY(var(--reveal-y))",
  fade: "none",
  scale: "scale(0.965)",
  blur: "translateY(calc(var(--reveal-y) * 0.6))",
  left: "translateX(-22px)",
  right: "translateX(22px)",
};

/** Reveal children once they enter the viewport. */
export function Reveal({
  children,
  delay = 0,
  y = 14,
  variant = "rise",
  duration = 720,
  className,
  style,
}: {
  children: React.ReactNode;
  delay?: number;
  y?: number;
  variant?: RevealVariant;
  duration?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  const { ref, seen } = useSeen<HTMLDivElement>();

  return (
    <div
      ref={ref}
      className={className}
      style={
        {
          "--reveal-y": `${y}px`,
          opacity: seen ? 1 : 0,
          transform: seen ? "none" : HIDDEN[variant],
          filter: variant === "blur" && !seen ? "blur(9px)" : undefined,
          transition: `opacity ${duration}ms ${EASE} ${delay}ms, transform ${duration}ms ${EASE} ${delay}ms, filter ${duration}ms ${EASE} ${delay}ms`,
          willChange: seen ? undefined : "opacity, transform",
          ...style,
        } as React.CSSProperties
      }
    >
      {children}
    </div>
  );
}

/**
 * Reveal a list of children one after another.
 *
 * The stagger is what turns a grid appearing into a grid being dealt out, and
 * it costs one extra wrapper per child.
 */
export function Stagger({
  children,
  step = 70,
  initialDelay = 0,
  variant = "rise",
  y = 16,
  className,
  style,
}: {
  children: React.ReactNode;
  step?: number;
  initialDelay?: number;
  variant?: RevealVariant;
  y?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  const items = Array.isArray(children) ? children : [children];
  return (
    <div className={className} style={style}>
      {items.map((child, i) => (
        <Reveal key={i} delay={initialDelay + i * step} variant={variant} y={y}>
          {child}
        </Reveal>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Split text
 * ----------------------------------------------------------------------- */

/**
 * A line of type that assembles itself word by word.
 *
 * Split on words rather than characters: a character stagger on a headline is
 * the single most overused effect on the web, and at display sizes it reads as
 * a slot machine. Words rising out of a mask read as typesetting.
 *
 * The pieces are hidden from assistive technology and the whole string is
 * announced once from the wrapper, so a screen reader hears a sentence rather
 * than a list of words.
 */
export function SplitText({
  text,
  delay = 0,
  step = 42,
  className,
  style,
  as: Tag = "span",
}: {
  text: string;
  delay?: number;
  step?: number;
  className?: string;
  style?: React.CSSProperties;
  as?: "span" | "h1" | "h2" | "p";
}) {
  const { ref, seen } = useSeen<HTMLElement>("0px 0px -5% 0px");
  const words = text.split(" ");

  return (
    <Tag
      ref={ref as React.Ref<never>}
      className={className}
      style={style}
      aria-label={text}
    >
      {words.map((word, i) => (
        <span
          key={i}
          aria-hidden="true"
          // The mask is what makes it a reveal rather than a fade: each word
          // rises out of a clipped box the height of its own line.
          style={{
            display: "inline-block",
            overflow: "hidden",
            verticalAlign: "top",
            // A descender clipped by an exact line box looks like a rendering
            // fault, so the mask is a shade taller than the text.
            paddingBottom: "0.14em",
            marginBottom: "-0.14em",
          }}
        >
          <span
            style={{
              display: "inline-block",
              transform: seen ? "none" : "translateY(105%)",
              opacity: seen ? 1 : 0,
              transition: `transform 900ms ${EASE} ${delay + i * step}ms, opacity 700ms ${EASE} ${delay + i * step}ms`,
              willChange: seen ? undefined : "transform",
            }}
          >
            {word}
          </span>
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </Tag>
  );
}

/* --------------------------------------------------------------------------
 * Counter
 * ----------------------------------------------------------------------- */

/**
 * A number that counts up the first time it is seen.
 *
 * `format` runs on every frame so the value animates in whatever shape it is
 * finally read in -- currency, a percentage, a duration. Under reduced motion,
 * or before the element has been seen, the final value is what renders: the
 * number is the content, and content does not wait on an effect.
 */
export function Counter({
  value,
  duration = 1150,
  format = (v: number) => String(Math.round(v)),
  className,
  style,
}: {
  value: number;
  duration?: number;
  format?: (value: number) => string;
  className?: string;
  style?: React.CSSProperties;
}) {
  const { ref, seen } = useSeen<HTMLSpanElement>("0px 0px -8% 0px");
  const [shown, setShown] = useState(value);
  const started = useRef(false);

  useEffect(() => {
    if (!seen || started.current) return;
    if (reducedMotion()) {
      setShown(value);
      return;
    }
    started.current = true;

    let frame = 0;
    const from = 0;
    const start = performance.now();

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      // Same ease-out as everything else, so a number lands like a panel does.
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(from + (value - from) * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [seen, value, duration]);

  return (
    <span ref={ref} className={className} style={style}>
      {format(seen ? shown : value)}
    </span>
  );
}

/* --------------------------------------------------------------------------
 * Pointer-driven
 * ----------------------------------------------------------------------- */

/**
 * A control that leans toward the cursor as it approaches.
 *
 * The pull is small on purpose. A button that chases the pointer across the
 * page is a toy; a button that shifts three pixels as you arrive at it feels
 * like the interface noticed you.
 */
export function Magnetic({
  children,
  strength = 0.28,
  radius = 90,
  className,
  style,
}: {
  children: React.ReactNode;
  strength?: number;
  radius?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || reducedMotion() || !finePointer()) return;

    let frame = 0;
    let target = { x: 0, y: 0 };
    const current = { x: 0, y: 0 };
    let running = false;

    const animate = () => {
      current.x += (target.x - current.x) * 0.16;
      current.y += (target.y - current.y) * 0.16;
      node.style.transform = `translate3d(${current.x.toFixed(2)}px, ${current.y.toFixed(2)}px, 0)`;
      // Stop the loop once it has effectively arrived rather than burning a
      // frame forever on a button nobody is near.
      if (Math.abs(target.x - current.x) < 0.05 && Math.abs(target.y - current.y) < 0.05) {
        node.style.transform = `translate3d(${target.x.toFixed(2)}px, ${target.y.toFixed(2)}px, 0)`;
        running = false;
        return;
      }
      frame = requestAnimationFrame(animate);
    };

    const kick = () => {
      if (running) return;
      running = true;
      frame = requestAnimationFrame(animate);
    };

    const onMove = (event: PointerEvent) => {
      const box = node.getBoundingClientRect();
      const dx = event.clientX - (box.left + box.width / 2);
      const dy = event.clientY - (box.top + box.height / 2);
      const distance = Math.hypot(dx, dy);
      if (distance < radius + Math.max(box.width, box.height) / 2) {
        target = { x: dx * strength, y: dy * strength };
      } else {
        target = { x: 0, y: 0 };
      }
      kick();
    };

    const onLeave = () => {
      target = { x: 0, y: 0 };
      kick();
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerleave", onLeave, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerleave", onLeave);
      cancelAnimationFrame(frame);
    };
  }, [strength, radius]);

  return (
    <span ref={ref} className={className} style={{ display: "inline-flex", ...style }}>
      {children}
    </span>
  );
}

/**
 * A surface that tips toward the cursor.
 *
 * Kept under four degrees. Past that the text on the panel starts to shear
 * visibly and the effect stops being depth and starts being a gimmick -- and
 * this sits under data people are trying to read.
 */
export function Tilt({
  children,
  max = 3.4,
  lift = 0,
  className,
  style,
}: {
  children: React.ReactNode;
  max?: number;
  lift?: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || reducedMotion() || !finePointer()) return;

    let frame = 0;
    const target = { rx: 0, ry: 0, z: 0 };
    const current = { rx: 0, ry: 0, z: 0 };
    let running = false;

    const animate = () => {
      current.rx += (target.rx - current.rx) * 0.14;
      current.ry += (target.ry - current.ry) * 0.14;
      current.z += (target.z - current.z) * 0.14;
      node.style.transform = `perspective(900px) rotateX(${current.rx.toFixed(3)}deg) rotateY(${current.ry.toFixed(3)}deg) translateZ(${current.z.toFixed(2)}px)`;
      const settled =
        Math.abs(target.rx - current.rx) < 0.004 &&
        Math.abs(target.ry - current.ry) < 0.004 &&
        Math.abs(target.z - current.z) < 0.02;
      if (settled) {
        running = false;
        if (target.rx === 0 && target.ry === 0 && target.z === 0) node.style.transform = "";
        return;
      }
      frame = requestAnimationFrame(animate);
    };

    const kick = () => {
      if (running) return;
      running = true;
      frame = requestAnimationFrame(animate);
    };

    const onMove = (event: PointerEvent) => {
      const box = node.getBoundingClientRect();
      const px = (event.clientX - box.left) / box.width - 0.5;
      const py = (event.clientY - box.top) / box.height - 0.5;
      target.ry = px * max * 2;
      target.rx = -py * max * 2;
      target.z = lift;
      kick();
    };

    const onLeave = () => {
      target.rx = 0;
      target.ry = 0;
      target.z = 0;
      kick();
    };

    node.addEventListener("pointermove", onMove, { passive: true });
    node.addEventListener("pointerleave", onLeave, { passive: true });
    return () => {
      node.removeEventListener("pointermove", onMove);
      node.removeEventListener("pointerleave", onLeave);
      cancelAnimationFrame(frame);
    };
  }, [max, lift]);

  return (
    <div ref={ref} className={className} style={{ transformStyle: "preserve-3d", ...style }}>
      {children}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Scroll progress
 * ----------------------------------------------------------------------- */

/**
 * How far a element has travelled through the viewport, 0 to 1.
 *
 * Written to a CSS custom property on the node rather than into React state:
 * this updates on every scroll frame, and re-rendering a subtree that often to
 * move one element is the difference between a page that glides and one that
 * stutters. Read it in CSS as `var(--progress)`.
 */
export function useScrollProgress<T extends HTMLElement>() {
  const ref = useRef<T>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (reducedMotion()) {
      node.style.setProperty("--progress", "0");
      return;
    }

    let frame = 0;
    const update = () => {
      frame = 0;
      const box = node.getBoundingClientRect();
      const span = box.height + window.innerHeight;
      const travelled = window.innerHeight - box.top;
      const progress = Math.max(0, Math.min(1, travelled / span));
      node.style.setProperty("--progress", progress.toFixed(4));
    };
    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(frame);
    };
  }, []);

  return ref;
}

/* --------------------------------------------------------------------------
 * Route transitions
 * ----------------------------------------------------------------------- */

/**
 * Settles new page content into place on a route change.
 *
 * Entrance only. An exit animation means holding the old page on screen while
 * the new one is already available, which is a delay dressed up as a
 * transition; this costs nothing and still marks the change.
 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (reducedMotion()) {
      setShown(true);
      return;
    }
    setShown(false);
    // Two frames: one to commit the hidden state, one to animate out of it.
    const frame = requestAnimationFrame(() => requestAnimationFrame(() => setShown(true)));
    return () => cancelAnimationFrame(frame);
  }, [pathname]);

  return (
    <div
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? "none" : "translateY(10px)",
        transition: `opacity 460ms ${EASE}, transform 560ms ${EASE}`,
      }}
    >
      {children}
    </div>
  );
}
