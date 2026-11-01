"use client";

/**
 * The scroll engine.
 *
 * One rule decides the whole file: there is exactly one clock. Lenis is
 * driven from `gsap.ticker` rather than from its own `requestAnimationFrame`,
 * and `ScrollTrigger` is told not to run its own lag smoothing. Two rAF loops
 * reading and writing the same scroll position is how a site ends up with
 * pinned sections that shimmer by a pixel on every frame — the two loops are
 * never quite in phase, and the eye reads the difference as jitter.
 *
 * Everything is imported dynamically. GSAP with ScrollTrigger is ~70KB and a
 * reader on a phone with reduced motion enabled never needs a byte of it.
 */

import type Lenis from "lenis";

type GsapModule = typeof import("gsap")["gsap"];
type ScrollTriggerModule = typeof import("gsap/ScrollTrigger")["ScrollTrigger"];

export type Engine = {
  gsap: GsapModule;
  ScrollTrigger: ScrollTriggerModule;
  lenis: Lenis | null;
};

let enginePromise: Promise<Engine> | null = null;

/**
 * Should this wheel or touch event be left to the browser?
 *
 * Lenis listens on the window and moves the document, so without this every
 * scrollable box inside the page froze under the mouse while the page behind it
 * moved instead. It decides by looking, not from a list of known boxes, so one
 * added next month works without anyone remembering to mark it.
 *
 * Anything inside a modal is always left alone: the page behind it is locked, and
 * must not move whatever the pointer is over.
 */
export function letBrowserScroll(node: HTMLElement): boolean {
  for (let el: HTMLElement | null = node; el && el !== document.body; el = el.parentElement) {
    if (el.getAttribute("role") === "dialog" || el.hasAttribute("data-lenis-prevent")) return true;
    if (el.scrollHeight > el.clientHeight + 1) {
      const { overflowY } = getComputedStyle(el);
      if (overflowY === "auto" || overflowY === "scroll") return true;
    }
  }
  return false;
}

/** Freeze the page behind a modal, for both the browser and Lenis. */
export function lockPageScroll(locked: boolean): void {
  document.documentElement.classList.toggle("scroll-locked", locked);
  const lenis = (window as unknown as { __lenis?: Lenis }).__lenis;
  if (locked) lenis?.stop();
  else lenis?.start();
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function finePointer(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(pointer: fine)").matches;
}

/**
 * Boot the engine, once per document.
 *
 * Idempotent by design: every component that needs scroll-driven motion calls
 * this, and they all get the same promise. Nothing here is torn down on route
 * change — Lenis is document-scoped and re-creating it between pages is what
 * produces the half-second of native scrolling after a navigation.
 */
export function getEngine(): Promise<Engine> {
  if (enginePromise) return enginePromise;

  enginePromise = (async () => {
    const [{ gsap }, { ScrollTrigger }, { CustomEase }] = await Promise.all([
      import("gsap"),
      import("gsap/ScrollTrigger"),
      import("gsap/CustomEase"),
    ]);

    gsap.registerPlugin(ScrollTrigger, CustomEase);

    /* The house curve. Symmetric, hard in and hard out: it accelerates away
       from rest faster than an ease-in-out and arrives more decisively, which
       is what makes a curtain read as mechanical rather than as a fade. */
    CustomEase.create("luxury", "0.75, 0, 0.25, 1");
    CustomEase.create("expo", "0.16, 1, 0.3, 1");

    gsap.defaults({ ease: "luxury", duration: 1 });

    if (prefersReducedMotion()) {
      return { gsap, ScrollTrigger, lenis: null };
    }

    const { default: Lenis } = await import("lenis");

    const lenis = new Lenis({
      duration: 1.12,
      // Exponential ease-out. A short lerp reads as sluggish and a long one as
      // drifting; this lands a wheel notch in about a fifth of a second and
      // settles without a bounce.
      easing: (t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      wheelMultiplier: 0.92,
      touchMultiplier: 1.6,
      // Touch devices already have momentum that feels right. Layering ours on
      // top makes the two fight and the page feels greasy.
      syncTouch: false,
      prevent: letBrowserScroll,
    });

    lenis.on("scroll", ScrollTrigger.update);

    gsap.ticker.add((time: number) => {
      // gsap.ticker reports seconds; Lenis wants milliseconds.
      lenis.raf(time * 1000);
    });

    // ScrollTrigger's own lag smoothing fights Lenis's interpolation.
    gsap.ticker.lagSmoothing(0);

    // Expose the instance so an anchor or a "back to top" anywhere in the app
    // can scroll through the same interpolation rather than jumping.
    (window as unknown as { __lenis?: Lenis }).__lenis = lenis;

    return { gsap, ScrollTrigger, lenis };
  })();

  return enginePromise;
}

/** Scroll to a target through the smooth engine, falling back to native. */
export function scrollTo(target: string | number | HTMLElement, offset = -80) {
  const lenis = (window as unknown as { __lenis?: Lenis }).__lenis;
  if (lenis) {
    lenis.scrollTo(target as never, { offset, duration: 1.4 });
    return;
  }
  const node =
    typeof target === "string" ? document.querySelector(target) : target;
  if (node instanceof HTMLElement) {
    window.scrollTo({ top: node.offsetTop + offset, behavior: "smooth" });
  } else if (typeof target === "number") {
    window.scrollTo({ top: target, behavior: "smooth" });
  }
}

/**
 * Split a string into word spans, each wrapped in its own line mask.
 *
 * Returned as data rather than as markup so the caller decides the element:
 * the same split serves an `h1` on the hero and a `p` in the manifesto.
 *
 * Words, never characters. A per-character stagger on a display headline is
 * the single most overused effect on the web and at 12vw it reads as a slot
 * machine; words rising out of a mask read as typesetting.
 */
export function splitWords(text: string): string[] {
  return text.split(/\s+/).filter(Boolean);
}
