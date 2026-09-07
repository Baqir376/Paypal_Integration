"use client";

/**
 * Reading design tokens at runtime.
 *
 * The canvas and WebGL layers cannot use CSS: they need real colour strings to
 * hand to a shader or a 2D context. Historically that meant the palette was
 * duplicated as hex literals in those files — which put the design in the
 * repository twice, once where it belongs and once where it could not be
 * protected.
 *
 * These read the value from the stylesheet instead, so the palette is defined
 * in exactly one place and the visualisations follow it automatically,
 * including through a theme change.
 */

/** Neutral stand-ins, used before hydration and if a token is missing. */
const NEUTRAL: Record<string, string> = {
  "--willow": "#888888",
  "--rep": "#777777",
  "--buyer": "#999999",
  "--ink": "#18181b",
  "--ink-3": "#71717a",
  "--paper": "#ffffff",
  "--rule": "#e4e4e7",
  "--accent-signal": "#888888",
  "--accent-gold": "#999999",
};

/**
 * The computed value of a CSS custom property.
 *
 * Returns a neutral grey rather than throwing when the token is absent: a
 * visualisation that renders in the wrong colour is a cosmetic problem, and one
 * that throws is a blank screen.
 */
export function token(name: string, fallback?: string): string {
  if (typeof window === "undefined") {
    return fallback ?? NEUTRAL[name] ?? "#888888";
  }
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback || NEUTRAL[name] || "#888888";
}

/** Several at once, for a palette object built at render time. */
export function tokens<K extends string>(
  map: Record<K, string>,
): Record<K, string> {
  const out = {} as Record<K, string>;
  for (const key of Object.keys(map) as K[]) {
    out[key] = token(map[key]);
  }
  return out;
}
