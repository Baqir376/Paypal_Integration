"use client";

/**
 * Charts, drawn by hand in SVG.
 *
 * No charting library. Every library has a look, and the look is recognisable
 * -- which defeats the point of art-directing everything else. These are small
 * enough to own: a radar, a sparkline, a distribution bar, a ring.
 *
 * Shared rules: one accent colour, tabular figures, no gridlines unless they
 * carry information, and a real `<title>` on anything a screen reader would
 * otherwise skip.
 */

import { Counter, Tilt } from "@/components/Motion";
import { AXIS_LABELS, AXIS_ORDER, cx, scoreTone } from "@/lib/format";
import type { SkillAxis } from "@/lib/types";

/* -------------------------------------------------------------------------
 * Skill radar
 * ---------------------------------------------------------------------- */

export function SkillRadar({
  values,
  benchmark,
  size = 250,
  label = "Skill profile",
  benchmarkLabel = "Team ceiling",
}: {
  values: Partial<Record<SkillAxis, number>>;
  benchmark?: Partial<Record<SkillAxis, number>>;
  size?: number;
  label?: string;
  benchmarkLabel?: string;
}) {
  const cx0 = size / 2;
  const cy0 = size / 2;
  const radius = size * 0.31;
  const axes = AXIS_ORDER;
  // The longest label ("Storytelling") overruns a square viewBox, so the box
  // is widened horizontally rather than shrinking the chart to fit it.
  const padX = 34;

  const point = (index: number, value: number) => {
    // Start at twelve o'clock and go clockwise, which is how people read a
    // radial chart without being told.
    const angle = (Math.PI * 2 * index) / axes.length - Math.PI / 2;
    const r = (Math.max(0, Math.min(100, value)) / 100) * radius;
    return [cx0 + Math.cos(angle) * r, cy0 + Math.sin(angle) * r] as const;
  };

  const polygon = (source: Partial<Record<SkillAxis, number>>) =>
    axes
      .map((axis, index) => point(index, source[axis] ?? 0).join(","))
      .join(" ");

  return (
    <svg
      width={size + padX * 2}
      height={size}
      viewBox={`${-padX} 0 ${size + padX * 2} ${size}`}
      // Intrinsic size above, but never wider than the column it sits in --
      // at its natural 318px this was the widest thing on a rep's page and
      // took the whole document sideways on a phone.
      style={{ maxWidth: "100%", height: "auto" }}
      role="img"
      aria-label={label}
    >
      <title>{label}</title>

      {/* Rings at 25/50/75/100, unlabelled: they give scale without clutter. */}
      {[0.25, 0.5, 0.75, 1].map((step) => (
        <polygon
          key={step}
          points={axes
            .map((_, index) => point(index, step * 100).join(","))
            .join(" ")}
          fill="none"
          stroke="var(--rule)"
          strokeWidth="1"
        />
      ))}

      {axes.map((_, index) => {
        const [x, y] = point(index, 100);
        return (
          <line
            key={index}
            x1={cx0}
            y1={cy0}
            x2={x}
            y2={y}
            stroke="var(--rule)"
            strokeWidth="1"
          />
        );
      })}

      {benchmark && (
        <polygon
          points={polygon(benchmark)}
          fill="none"
          stroke="var(--ink-4)"
          strokeWidth="1.4"
          strokeDasharray="4 3"
        >
          <title>{benchmarkLabel}</title>
        </polygon>
      )}

      <polygon
        points={polygon(values)}
        fill="color-mix(in oklab, var(--willow) 20%, transparent)"
        stroke="var(--willow)"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />

      {axes.map((axis, index) => {
        const [x, y] = point(index, 100);
        const value = values[axis] ?? 0;
        return (
          <circle key={axis} cx={x} cy={y} r="2.5" fill="var(--willow)" opacity={value / 100} />
        );
      })}

      {axes.map((axis, index) => {
        const angle = (Math.PI * 2 * index) / axes.length - Math.PI / 2;
        const x = cx0 + Math.cos(angle) * (radius + 30);
        const y = cy0 + Math.sin(angle) * (radius + 24);
        return (
          <text
            key={axis}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            style={{
              fontSize: 9.5,
              fill: "var(--ink-3)",
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            {AXIS_LABELS[axis]}
          </text>
        );
      })}
    </svg>
  );
}

/* -------------------------------------------------------------------------
 * Sparkline
 * ---------------------------------------------------------------------- */

export function Sparkline({
  values,
  width = 96,
  height = 26,
  label,
}: {
  values: number[];
  width?: number;
  height?: number;
  label?: string;
}) {
  if (values.length < 2) {
    return (
      <span className="eyebrow" style={{ color: "var(--ink-4)" }}>
        no trend yet
      </span>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat series should render flat and centred, not as a divide-by-zero.
  const span = max - min || 1;
  const pad = 3;

  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * (width - pad * 2) + pad;
    const y = height - pad - ((value - min) / span) * (height - pad * 2);
    return [x, y] as const;
  });

  const path = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
  const rising = values[values.length - 1] >= values[0];
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg width={width} height={height} role="img" aria-label={label ?? "Trend"}>
      <path
        d={path}
        fill="none"
        stroke={rising ? "var(--sage)" : "var(--rose)"}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r="2.2" fill={rising ? "var(--sage)" : "var(--rose)"} />
    </svg>
  );
}

/* -------------------------------------------------------------------------
 * Talk-ratio bar
 * ---------------------------------------------------------------------- */

/**
 * The rep's share of the floor, with the 43% benchmark marked.
 *
 * The benchmark tick is the whole point: a bare percentage means nothing to
 * someone who has not memorised what good looks like.
 */
export function TalkRatioBar({
  ratio,
  height = 8,
  showBenchmark = true,
}: {
  ratio: number;
  height?: number;
  showBenchmark?: boolean;
}) {
  const pct = Math.max(0, Math.min(1, ratio)) * 100;
  const off = Math.abs(pct - 43);
  const tone =
    off <= 7 ? "var(--sage)" : off <= 17 ? "var(--ember)" : "var(--rose)";

  return (
    <div
      style={{ position: "relative", width: "100%" }}
      title={`Rep ${Math.round(pct)}% · buyer ${Math.round(100 - pct)}% · benchmark 43%`}
    >
      <div
        style={{
          height,
          borderRadius: 999,
          background: "var(--buyer-soft)",
          overflow: "hidden",
        }}
      >
        <div style={{ width: `${pct}%`, height: "100%", background: tone }} />
      </div>
      {showBenchmark && (
        <span
          aria-hidden
          style={{
            position: "absolute",
            left: "43%",
            top: -2,
            bottom: -2,
            width: 1.5,
            background: "var(--ink-2)",
            opacity: 0.55,
          }}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------
 * Score ring
 * ---------------------------------------------------------------------- */

export function ScoreRing({
  score,
  size = 62,
  thickness = 4,
  caption,
}: {
  score: number | null | undefined;
  size?: number;
  thickness?: number;
  caption?: string;
}) {
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const value = score ?? 0;
  const tone = scoreTone(score);

  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      {/* Decorative: the ring only restates the number rendered over it, so a
          screen reader should read the score once, not twice. */}
      <svg
        width={size}
        height={size}
        style={{ transform: "rotate(-90deg)" }}
        aria-hidden="true"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--paper-3)"
          strokeWidth={thickness}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={tone}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - value / 100)}
          style={{ transition: "stroke-dashoffset 700ms cubic-bezier(0.16,1,0.3,1)" }}
        />
      </svg>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 2,
          lineHeight: 1,
        }}
      >
        <span
          className="num"
          style={{ fontSize: size * 0.29, fontWeight: 500, color: tone }}
        >
          {score == null ? "--" : Math.round(score)}
        </span>
        {caption && (
          <span className="eyebrow" style={{ fontSize: 7.5, letterSpacing: "0.08em" }}>
            {caption}
          </span>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------
 * Stat tile
 * ---------------------------------------------------------------------- */

/**
 * A headline number.
 *
 * Pass `count` with the raw number and `format` with the function that shapes
 * it, and the figure counts up the first time it is seen -- through the same
 * formatter, so it animates as a percentage or an abbreviated sum rather than
 * as a bare integer that snaps into shape at the end. Pass `value` instead for
 * anything that is not a number to begin with.
 *
 * The tile tips very slightly toward the pointer. It is a couple of degrees on
 * purpose: this is a surface someone reads figures off, and anything more
 * starts shearing the type.
 */
export function Stat({
  label,
  value,
  count,
  format,
  hint,
  tone,
  className,
}: {
  label: string;
  value?: React.ReactNode;
  count?: number;
  format?: (value: number) => string;
  hint?: React.ReactNode;
  tone?: string;
  className?: string;
}) {
  return (
    <Tilt className={cx("panel", "tilt", className)} max={2.6} style={{ padding: "15px 17px" }}>
      <div className="eyebrow" style={{ marginBottom: 9 }}>
        {label}
      </div>
      <div className="num stat" style={{ color: tone ?? "var(--ink)" }}>
        {count != null ? <Counter value={count} format={format} /> : value}
      </div>
      {hint && (
        <div style={{ marginTop: 7, fontSize: 12, color: "var(--ink-3)" }}>{hint}</div>
      )}
    </Tilt>
  );
}

/* -------------------------------------------------------------------------
 * Deal trajectory line
 * ---------------------------------------------------------------------- */

export function TrajectoryLine({
  points,
  width = 420,
  height = 90,
}: {
  points: { score: number; buyer_engagement: number; title: string }[];
  width?: number;
  height?: number;
}) {
  if (points.length === 0) {
    return (
      <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
        No analysed calls on this deal yet.
      </div>
    );
  }

  const pad = 10;
  const step =
    points.length > 1 ? (width - pad * 2) / (points.length - 1) : 0;
  const y = (value: number) => height - pad - (value / 100) * (height - pad * 2);

  const line = (accessor: (p: (typeof points)[0]) => number) =>
    points
      .map((p, i) => `${i === 0 ? "M" : "L"}${pad + i * step},${y(accessor(p))}`)
      .join("");

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Deal trajectory">
      <line
        x1={pad}
        y1={y(50)}
        x2={width - pad}
        y2={y(50)}
        stroke="var(--rule)"
        strokeDasharray="3 4"
      />
      {/* Buyer engagement is the leading indicator, so it is drawn first and
          quieter -- the call score is what the reader is scanning for. */}
      <path
        d={line((p) => p.buyer_engagement * 100)}
        fill="none"
        stroke="var(--buyer)"
        strokeWidth="1.5"
        strokeDasharray="3 3"
        opacity="0.75"
      />
      <path
        d={line((p) => p.score)}
        fill="none"
        stroke="var(--willow)"
        strokeWidth="2"
        strokeLinecap="round"
      />
      {points.map((p, i) => (
        <circle key={i} cx={pad + i * step} cy={y(p.score)} r="3.2" fill="var(--willow)">
          <title>{`${p.title}: score ${Math.round(p.score)}, engagement ${Math.round(
            p.buyer_engagement * 100,
          )}%`}</title>
        </circle>
      ))}
    </svg>
  );
}
