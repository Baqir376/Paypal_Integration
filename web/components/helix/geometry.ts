/**
 * Geometry for the Conversation Helix.
 *
 * A call is drawn as a ribbon running left to right along a time axis. Three
 * properties of the conversation drive three properties of the ribbon:
 *
 *   drift   The centre line rises when the rep holds the floor and falls when
 *           the buyer does. A call where the rep talks throughout is a ribbon
 *           pinned to the ceiling.
 *
 *   twist   The strip rotates in proportion to how often the floor changes
 *           hands. A real conversation corkscrews; a presentation is a plank.
 *
 *   width   Half-width follows speech density, so silence pinches to a thread
 *           and overlapping speech swells.
 *
 * The thing that makes this read as a designed object rather than a plotted
 * one is smoothing. The underlying buckets are near-binary -- a slice is
 * mostly rep or mostly buyer -- so drawing them raw produces a row of hard
 * spikes that self-intersect when the ribbon twists through them. Every
 * series is therefore low-pass filtered and then resampled through a
 * Catmull-Rom spline at several times the bucket resolution, which is what
 * turns the data into a curve. The information is identical; it is legible
 * only after the smoothing.
 */

import type { TalkSlice } from "@/lib/types";

export interface HelixOptions {
  length?: number;
  driftAmplitude?: number;
  maxHalfWidth?: number;
  minHalfWidth?: number;
  twistPerSwitch?: number;
  /** Points generated per input bucket. Higher is smoother. */
  resample?: number;
  /** Half-window of the moving average, in buckets. */
  smoothing?: number;
}

const DEFAULTS: Required<HelixOptions> = {
  length: 11,
  driftAmplitude: 1.0,
  maxHalfWidth: 0.5,
  minHalfWidth: 0.07,
  twistPerSwitch: 1.5,
  resample: 6,
  smoothing: 2,
};

export interface HelixBuild {
  positions: Float32Array;
  colors: Float32Array;
  normals: Float32Array;
  uvs: Float32Array;
  indices: Uint32Array;
  centers: Float32Array;
  sliceCount: number;
}

function hexToLinear(hex: string): [number, number, number] {
  const v = hex.replace("#", "");
  const full = v.length === 3 ? v.split("").map((c) => c + c).join("") : v;
  const n = parseInt(full, 16);
  const lin = (c: number) => Math.pow(c / 255, 2.2);
  return [lin((n >> 16) & 255), lin((n >> 8) & 255), lin(n & 255)];
}

/** Moving average. The first defence against a stepped series. */
function smoothSeries(values: number[], half: number): number[] {
  if (half <= 0 || values.length < 3) return values.slice();
  const out = new Array<number>(values.length);
  for (let i = 0; i < values.length; i++) {
    let sum = 0;
    let count = 0;
    for (let k = -half; k <= half; k++) {
      const j = i + k;
      if (j < 0 || j >= values.length) continue;
      // Triangular weights: closer buckets matter more, so genuine structure
      // survives while single-bucket noise does not.
      const w = half + 1 - Math.abs(k);
      sum += values[j] * w;
      count += w;
    }
    out[i] = sum / count;
  }
  return out;
}

/** Catmull-Rom through a 1-D series, evaluated at t in [0, 1]. */
function splineAt(values: number[], t: number): number {
  const n = values.length;
  if (n === 0) return 0;
  if (n === 1) return values[0];

  const x = Math.max(0, Math.min(1, t)) * (n - 1);
  const i = Math.min(n - 2, Math.floor(x));
  const f = x - i;

  const p0 = values[Math.max(0, i - 1)];
  const p1 = values[i];
  const p2 = values[i + 1];
  const p3 = values[Math.min(n - 1, i + 2)];

  const f2 = f * f;
  const f3 = f2 * f;
  return (
    0.5 *
    (2 * p1 +
      (-p0 + p2) * f +
      (2 * p0 - 5 * p1 + 4 * p2 - p3) * f2 +
      (-p0 + 3 * p1 - 3 * p2 + p3) * f3)
  );
}

export function buildHelix(
  slices: TalkSlice[],
  repHex: string,
  buyerHex: string,
  options: HelixOptions = {},
): HelixBuild {
  const o = { ...DEFAULTS, ...options };
  const source = slices.length;

  if (source < 2) {
    return {
      positions: new Float32Array(0),
      colors: new Float32Array(0),
      normals: new Float32Array(0),
      uvs: new Float32Array(0),
      indices: new Uint32Array(0),
      centers: new Float32Array(0),
      sliceCount: 0,
    };
  }

  const rep = hexToLinear(repHex);
  const buyer = hexToLinear(buyerHex);

  // --- Smooth the three driving series -------------------------------
  const shareRaw = slices.map((s) => s.rep_share);
  const energyRaw = slices.map((s) => s.energy);
  const share = smoothSeries(shareRaw, o.smoothing);
  const energy = smoothSeries(energyRaw, o.smoothing);

  // Twist is cumulative, so it is integrated from the *smoothed* handover
  // magnitude. Integrating the raw series makes the ribbon spin so fast it
  // folds through itself.
  const twistRaw: number[] = [0];
  for (let i = 1; i < source; i++) {
    const handover = Math.abs(share[i] - share[i - 1]) * energy[i];
    twistRaw.push(twistRaw[i - 1] + handover * o.twistPerSwitch);
  }
  const twist = smoothSeries(twistRaw, o.smoothing);

  // --- Resample through the spline ------------------------------------
  const n = Math.max(24, Math.min(900, Math.round(source * o.resample)));

  const positions = new Float32Array(n * 2 * 3);
  const colors = new Float32Array(n * 2 * 3);
  const normals = new Float32Array(n * 2 * 3);
  const uvs = new Float32Array(n * 2 * 2);
  const centers = new Float32Array(n * 3);

  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    const x = (t - 0.5) * o.length;

    const sh = Math.max(0, Math.min(1, splineAt(share, t)));
    const en = Math.max(0, Math.min(1, splineAt(energy, t)));
    const tw = splineAt(twist, t);

    const y = (sh - 0.5) * 2 * o.driftAmplitude;
    const halfWidth =
      o.minHalfWidth + (o.maxHalfWidth - o.minHalfWidth) * Math.sqrt(en);

    // Ribbon edges perpendicular to the path, rotated by the accumulated twist.
    const dy = Math.cos(tw) * halfWidth;
    const dz = Math.sin(tw) * halfWidth;

    const a = i * 6;
    positions[a] = x;
    positions[a + 1] = y + dy;
    positions[a + 2] = dz;
    positions[a + 3] = x;
    positions[a + 4] = y - dy;
    positions[a + 5] = -dz;

    centers[i * 3] = x;
    centers[i * 3 + 1] = y;
    centers[i * 3 + 2] = 0;

    const nx = 0;
    const ny = -Math.sin(tw);
    const nz = Math.cos(tw);
    normals[a] = nx;
    normals[a + 1] = ny;
    normals[a + 2] = nz;
    normals[a + 3] = nx;
    normals[a + 4] = ny;
    normals[a + 5] = nz;

    const u = i * 4;
    uvs[u] = t;
    uvs[u + 1] = 0;
    uvs[u + 2] = t;
    uvs[u + 3] = 1;

    // Colour by who holds the floor. Energy lifts the value so quiet stretches
    // recede rather than reading as a third colour.
    const lift = 0.62 + 0.38 * en;
    for (let e = 0; e < 2; e++) {
      const c = a + e * 3;
      colors[c] = (buyer[0] + (rep[0] - buyer[0]) * sh) * lift;
      colors[c + 1] = (buyer[1] + (rep[1] - buyer[1]) * sh) * lift;
      colors[c + 2] = (buyer[2] + (rep[2] - buyer[2]) * sh) * lift;
    }
  }

  const indices = new Uint32Array((n - 1) * 6);
  for (let i = 0; i < n - 1; i++) {
    const base = i * 2;
    const q = i * 6;
    indices[q] = base;
    indices[q + 1] = base + 1;
    indices[q + 2] = base + 2;
    indices[q + 3] = base + 1;
    indices[q + 4] = base + 3;
    indices[q + 5] = base + 2;
  }

  return { positions, colors, normals, uvs, indices, centers, sliceCount: n };
}

export function timeToX(ms: number, durationMs: number, length = DEFAULTS.length) {
  if (durationMs <= 0) return -length / 2;
  return (Math.max(0, Math.min(1, ms / durationMs)) - 0.5) * length;
}

export function pointAt(
  build: HelixBuild,
  ms: number,
  durationMs: number,
): [number, number, number] {
  const { centers, sliceCount } = build;
  if (sliceCount === 0) return [0, 0, 0];
  const t = durationMs > 0 ? Math.max(0, Math.min(1, ms / durationMs)) : 0;
  const exact = t * (sliceCount - 1);
  const i = Math.min(sliceCount - 2, Math.floor(exact));
  const f = exact - i;
  const a = i * 3;
  const b = (i + 1) * 3;
  return [
    centers[a] + (centers[b] - centers[a]) * f,
    centers[a + 1] + (centers[b + 1] - centers[a + 1]) * f,
    centers[a + 2] + (centers[b + 2] - centers[a + 2]) * f,
  ];
}
