/**
 * One answer, asked once, about what this device can draw.
 *
 * Probing for WebGL costs a real GL context, and a browser only grants a
 * handful before it starts force-losing the oldest ones -- including the ones
 * the scene is actually drawing with. So the probe releases its context the
 * moment it has an answer, and the answer is cached for the life of the
 * document: capability does not change between navigations, and re-probing on
 * every mount was on its own enough to blank the ribbon after a few moves
 * around the app.
 *
 * Both the Helix and the ambient Field ask through here, so two 3D surfaces on
 * one page still cost exactly one probe.
 */

export interface Caps {
  /** WebGL is available at all. */
  webgl: boolean;
  /** Enough cores and memory to afford post-processing. */
  heavy: boolean;
}

let cached: Caps | null = null;

export function capabilities(): Caps {
  if (typeof window === "undefined") return { webgl: false, heavy: false };
  if (cached) return cached;
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
    if (!gl) return (cached = { webgl: false, heavy: false });
    // Hand the context back immediately rather than waiting for the canvas to
    // be collected; GC is far too late to matter here.
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    const cores = navigator.hardwareConcurrency ?? 4;
    const memory = (navigator as unknown as { deviceMemory?: number }).deviceMemory ?? 4;
    return (cached = { webgl: true, heavy: cores >= 4 && memory >= 4 });
  } catch {
    return (cached = { webgl: false, heavy: false });
  }
}

/** True when the reader has asked for less movement. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
