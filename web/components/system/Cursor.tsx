"use client";

/**
 * The cursor.
 *
 * A single ring that lags the pointer, and no system arrow at all. The lag is
 * the whole effect: a ring locked to the pointer is just a bigger pointer,
 * whereas one that arrives a beat late reads as mass — and mass is what makes
 * a cursor feel like an instrument rather than a decoration.
 *
 * Hiding the native arrow is the risky half, so it is done defensively. The
 * `cursor: none` rule is scoped to a class this component adds to <html> after
 * it has mounted and confirmed it will actually run. If the JavaScript fails,
 * never loads, or the pointer turns out to be a touchscreen, the class is
 * never added and the ordinary arrow is exactly where it always was. A page
 * with no pointer and no replacement is unusable, and that must not be one
 * bad deploy away.
 *
 * What the ring is over is read off the DOM rather than pushed from each
 * component, so any link added anywhere is picked up without knowing this file
 * exists.
 */

import { useEffect, useRef } from "react";

import { finePointer, prefersReducedMotion } from "@/lib/motion";

export function Cursor() {
  const ring = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Both conditions must hold before the system cursor is taken away.
    if (!finePointer() || prefersReducedMotion()) return;

    const node = ring.current;
    if (!node) return;

    const root = document.documentElement;
    root.classList.add("sx-has-cursor");

    const pointer = { x: innerWidth / 2, y: innerHeight / 2 };
    const trail = { ...pointer };
    let frame = 0;
    let shown = false;

    const render = () => {
      // Frame-rate independent damping. Without the exponent a 144Hz screen
      // catches up more than twice as fast as a 60Hz one, and the ring feels
      // like a different weight on different machines.
      const lag = 1 - Math.pow(0.0016, 1 / 60);
      trail.x += (pointer.x - trail.x) * lag * 9;
      trail.y += (pointer.y - trail.y) * lag * 9;
      node.style.transform = `translate3d(${trail.x}px, ${trail.y}px, 0)`;
      frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);

    /** What is under the pointer, in the ring's own vocabulary. */
    function resolve(target: EventTarget | null): string {
      if (!(target instanceof Element)) return "default";
      const declared = target.closest<HTMLElement>("[data-cursor]");
      if (declared) return declared.dataset.cursor ?? "default";
      if (target.closest("a, button, [role='button'], summary, label, select")) {
        return "link";
      }
      if (target.closest("input, textarea, [contenteditable='true']")) {
        return "text";
      }
      return "default";
    }

    const onMove = (event: PointerEvent) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      if (!shown) {
        shown = true;
        node.style.opacity = "1";
      }
      const state = resolve(event.target);
      if (node.dataset.state !== state) node.dataset.state = state;
    };

    // Leaving the window or losing focus ends the session; without this the
    // ring parks at the last known point and sits there.
    const onLeave = () => {
      shown = false;
      node.style.opacity = "0";
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    window.addEventListener("blur", onLeave);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      window.removeEventListener("blur", onLeave);
      // Give the arrow back on the way out, so a hot reload or an unmount
      // never leaves the page with no pointer at all.
      root.classList.remove("sx-has-cursor");
    };
  }, []);

  return (
    <div
      ref={ring}
      className="sx-cursor no-print"
      aria-hidden="true"
      data-state="default"
      style={{ opacity: 0 }}
    />
  );
}
