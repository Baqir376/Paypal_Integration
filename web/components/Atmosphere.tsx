"use client";

/**
 * The page's atmosphere.
 *
 * A flat fill is the single clearest tell of an undesigned dark interface.
 * Three fixed layers sit behind everything and cost nothing to scroll:
 *
 *   1. Two very wide, very dim radial washes. They give the void a light
 *      source and stop large empty regions reading as dead pixels.
 *   2. A blueprint grid at ~2% opacity, masked to fade out toward the edges
 *      so it never draws a hard boundary.
 *   3. Film grain from an SVG turbulence filter. This is the cheapest large
 *      gain in perceived quality there is -- it breaks up banding in the
 *      gradients and gives flat panels a surface.
 *
 * All three are `pointer-events: none` and sit at z-index 0, so nothing here
 * can intercept a click. Grain is dropped under `prefers-reduced-transparency`
 * and the whole thing is hidden in print.
 */

export function Atmosphere() {
  return (
    <div aria-hidden className="atmosphere no-print">
      <div className="atmosphere-wash" />
      <div className="atmosphere-grid" />
      <svg
        className="atmosphere-grain"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        focusable="false"
      >
        <filter id="salix-grain">
          {/* Fine, high-frequency noise. numOctaves=1 keeps it as grain
              rather than clouds. */}
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.82"
            numOctaves="1"
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#salix-grain)" />
      </svg>
    </div>
  );
}
