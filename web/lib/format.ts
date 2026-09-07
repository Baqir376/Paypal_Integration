/** Formatting helpers, kept in one place so numbers read identically everywhere. */

import type { Severity, SkillAxis } from "./types";

/** Milliseconds to `m:ss`, the form used on every timestamp in the product. */
export function clock(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** A duration in prose: "3m 40s", "42s". */
export function duration(ms: number): string {
  const total = Math.round(ms / 1000);
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value == null) return "--";
  return `${(value * 100).toFixed(digits)}%`;
}

export function money(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });
}

export function longDate(iso: string | null | undefined): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export const AXIS_LABELS: Record<SkillAxis, string> = {
  listening: "Listening",
  discovery: "Discovery",
  storytelling: "Storytelling",
  objection_handling: "Objections",
  pace_and_presence: "Pace",
  closing: "Closing",
};

export const AXIS_ORDER: SkillAxis[] = [
  "listening",
  "discovery",
  "storytelling",
  "objection_handling",
  "pace_and_presence",
  "closing",
];

export const SEVERITY_CHIP: Record<Severity, string> = {
  low: "chip-neutral",
  medium: "chip-ember",
  high: "chip-rose",
  critical: "chip-rose",
};

export function outcomeChip(outcome: string): string {
  if (outcome === "won") return "chip-sage";
  if (outcome === "lost") return "chip-rose";
  return "chip-slate";
}

/**
 * Colour a 0-100 score.
 *
 * Deliberately three bands rather than a gradient: a rep should be able to
 * tell at a glance whether a number is fine, soft, or a problem, and a
 * continuous ramp makes 61 and 64 look meaningfully different when they are not.
 */
export function scoreTone(score: number | null | undefined): string {
  if (score == null) return "var(--ink-4)";
  if (score >= 72) return "var(--sage)";
  if (score >= 55) return "var(--ember)";
  return "var(--rose)";
}

/** How far a talk ratio sits from the 43% benchmark, as prose. */
export function talkRatioVerdict(ratio: number | null | undefined): string {
  if (ratio == null) return "";
  const pct = Math.round(ratio * 100);
  if (pct > 62) return `${pct}% -- dominating`;
  if (pct > 50) return `${pct}% -- talking too much`;
  if (pct < 30) return `${pct}% -- very quiet`;
  return `${pct}% -- on benchmark`;
}

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
