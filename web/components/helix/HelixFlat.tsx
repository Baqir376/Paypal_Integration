"use client";

/**
 * The Helix, flattened to SVG.
 *
 * This is not a degraded placeholder -- it draws the same three signals from
 * the same data: the band rises with the rep's share of the floor, its
 * thickness follows speech density, and its colour says who is speaking. It
 * stands in wherever WebGL is unavailable or a context is lost, and it is what
 * prints.
 */

import { clock } from "@/lib/format";
import { token } from "@/lib/tokens";

import type { CallMetrics } from "@/lib/types";

import type { HelixMarker } from "./Helix";

const REP = "#3fb8ad";
const BUYER = "#c07bb8";

const MARKER_COLOR: Record<HelixMarker["kind"], string> = {
  objection: "#e0a163",
  play: token("--willow"),
  monologue: "#d99aa6",
  next_step: "#82b894",
};

interface Props {
  metrics: CallMetrics;
  markers: HelixMarker[];
  positionMs?: number;
  onSeek?: (ms: number) => void;
  height?: number | string;
}

export function HelixFlat({
  metrics,
  markers,
  positionMs = 0,
  onSeek,
  height = 320,
}: Props) {
  const slices = metrics.timeline;
  const W = 1000;
  const H = 260;
  const MID = H / 2;

  if (slices.length < 2) {
    return (
      <div
        style={{
          height,
          display: "grid",
          placeItems: "center",
          color: "var(--ink-3)",
          fontSize: 13,
        }}
      >
        No timeline for this call.
      </div>
    );
  }

  const step = W / (slices.length - 1);

  // Two edge paths around a drifting centre line, filled as one band.
  const top: string[] = [];
  const bottom: string[] = [];

  slices.forEach((slice, i) => {
    const x = i * step;
    const drift = (slice.rep_share - 0.5) * 2 * (H * 0.32);
    const halfWidth = 3 + Math.sqrt(slice.energy) * (H * 0.17);
    top.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)},${(MID - drift - halfWidth).toFixed(1)}`);
    bottom.push(`L${x.toFixed(1)},${(MID - drift + halfWidth).toFixed(1)}`);
  });

  const band = `${top.join("")}${bottom.reverse().join("")}Z`;
  const playhead =
    metrics.duration_ms > 0 ? (positionMs / metrics.duration_ms) * W : 0;

  function seek(event: React.MouseEvent<SVGSVGElement>) {
    if (!onSeek) return;
    const box = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - box.left) / box.width;
    onSeek(Math.max(0, Math.min(1, ratio)) * metrics.duration_ms);
  }

  return (
    <div style={{ height }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        style={{ width: "100%", height: "100%", cursor: onSeek ? "pointer" : "default" }}
        onClick={seek}
        role="img"
        aria-label={`Conversation shape: rep held ${Math.round(
          metrics.talk_ratio_rep * 100,
        )} percent of the floor across ${clock(metrics.duration_ms)}`}
      >
        <defs>
          <linearGradient id="helix-flat" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={REP} stopOpacity="0.92" />
            <stop offset="50%" stopColor={REP} stopOpacity="0.55" />
            <stop offset="50%" stopColor={BUYER} stopOpacity="0.55" />
            <stop offset="100%" stopColor={BUYER} stopOpacity="0.92" />
          </linearGradient>
        </defs>

        {/* The balance line: the ribbon sitting on it means an even call. */}
        <line
          x1="0"
          y1={MID}
          x2={W}
          y2={MID}
          stroke="var(--rule-strong)"
          strokeWidth="1"
          strokeDasharray="3 5"
          vectorEffect="non-scaling-stroke"
        />

        <path d={band} fill="url(#helix-flat)" />

        {markers.map((marker, index) => {
          const x = (marker.ms / Math.max(1, metrics.duration_ms)) * W;
          return (
            <g key={`${marker.kind}-${index}`}>
              <line
                x1={x}
                y1={MID - H * 0.44}
                x2={x}
                y2={MID + H * 0.44}
                stroke={MARKER_COLOR[marker.kind]}
                strokeWidth="1"
                strokeOpacity="0.4"
                vectorEffect="non-scaling-stroke"
              />
              <circle cx={x} cy={MID - H * 0.44} r="4" fill={MARKER_COLOR[marker.kind]}>
                <title>{`${marker.label}${marker.detail ? ` -- ${marker.detail}` : ""}`}</title>
              </circle>
            </g>
          );
        })}

        <line
          x1={playhead}
          y1="0"
          x2={playhead}
          y2={H}
          stroke="var(--ink)"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 6,
        }}
      >
        <span className="eyebrow">rep above · buyer below</span>
        <span className="num" style={{ fontSize: 11, color: "var(--ink-3)" }}>
          {clock(metrics.duration_ms)}
        </span>
      </div>
    </div>
  );
}
