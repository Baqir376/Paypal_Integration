/**
 * Hand-drawn iconography.
 *
 * No icon library and no emoji. A stock icon set is one of the clearest tells
 * of an interface nobody art-directed, and these are drawn on a consistent
 * 16-unit grid with a single 1.4 stroke weight so they sit together.
 */

interface IconProps {
  size?: number;
  style?: React.CSSProperties;
  className?: string;
}

function Svg({
  size = 16,
  style,
  className,
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0, ...style }}
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/** Command centre: a gauge sweeping past its mark. */
export const IconGauge = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2.4 11.5a6.2 6.2 0 1 1 11.2 0" />
    <path d="M8 11.2 11 6.6" />
    <circle cx="8" cy="11.5" r="0.9" fill="currentColor" stroke="none" />
  </Svg>
);

/** Calls: a waveform, the actual subject of the product. */
export const IconWave = (p: IconProps) => (
  <Svg {...p}>
    <path d="M1.6 8h1.2M5 4.6v6.8M8 2.6v10.8M11 5.4v5.2M14.4 7.2v1.6" />
  </Svg>
);

/** Playbook: a bound volume. */
export const IconBook = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2.6 2.8h6.2a2 2 0 0 1 2 2v8.4H4.6a2 2 0 0 1-2-2z" />
    <path d="M10.8 4.8h2.6v8.4h-2.6" />
    <path d="M4.8 5.8h3.4M4.8 8h3.4" />
  </Svg>
);

/** Deals: a pipeline narrowing toward a close. */
export const IconDeal = (p: IconProps) => (
  <Svg {...p}>
    <path d="M1.8 3.4h12.4L9.6 8.4v4.6L6.4 11.6V8.4z" />
  </Svg>
);

/** The Dojo: two opposed arcs, a conversation held in tension. */
export const IconDojo = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5.4 2.6a6 6 0 0 0 0 10.8" />
    <path d="M10.6 13.4a6 6 0 0 0 0-10.8" />
    <circle cx="8" cy="8" r="1.5" />
  </Svg>
);

/** Report: a page with a rising trend. */
export const IconReport = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3.4 1.8h6l3.2 3.2v9.2H3.4z" />
    <path d="M9.2 1.8v3.4h3.4" />
    <path d="M5.6 11.4 7.4 9.2l1.6 1.4 2-2.8" />
  </Svg>
);

export const IconUpload = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 10.8V2.6M5.2 5.4 8 2.6l2.8 2.8" />
    <path d="M2.6 10.6v1.8a1.6 1.6 0 0 0 1.6 1.6h7.6a1.6 1.6 0 0 0 1.6-1.6v-1.8" />
  </Svg>
);

export const IconSearch = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="7.2" cy="7.2" r="4.6" />
    <path d="m10.6 10.6 3 3" />
  </Svg>
);

export const IconArrow = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2.8 8h10.4M9.4 4.2 13.2 8l-3.8 3.8" />
  </Svg>
);

export const IconQuote = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 4.4C4 5.2 3 6.8 3 9v2.6h3.6V8H5.2c0-1.4.3-2.4 1.4-3zM13 4.4c-2 .8-3 2.4-3 4.6v2.6h3.6V8h-1.4c0-1.4.3-2.4 1.4-3z" />
  </Svg>
);

export const IconWarning = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 2.4 14.4 13H1.6z" />
    <path d="M8 6.6v3M8 11.4v.1" />
  </Svg>
);

export const IconCheck = (p: IconProps) => (
  <Svg {...p}>
    <path d="m3 8.4 3.2 3.2L13 4.8" />
  </Svg>
);

export const IconSpark = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 1.8 9.5 6 13.8 7.5 9.5 9 8 13.2 6.5 9 2.2 7.5 6.5 6z" />
  </Svg>
);

export const IconMic = (p: IconProps) => (
  <Svg {...p}>
    <rect x="6" y="1.8" width="4" height="7.6" rx="2" />
    <path d="M3.4 7.6a4.6 4.6 0 0 0 9.2 0M8 12.2v2" />
  </Svg>
);

export const IconStop = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3.6" y="3.6" width="8.8" height="8.8" rx="1.6" />
  </Svg>
);

export const IconPlay = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4.6 2.8 12.6 8l-8 5.2z" />
  </Svg>
);

export const IconPause = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5.6 3v10M10.4 3v10" />
  </Svg>
);

export const IconLink = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6.6 9.4a2.6 2.6 0 0 0 3.8 0l2.2-2.2a2.7 2.7 0 0 0-3.8-3.8L7.6 4.6" />
    <path d="M9.4 6.6a2.6 2.6 0 0 0-3.8 0L3.4 8.8a2.7 2.7 0 0 0 3.8 3.8l1.2-1.2" />
  </Svg>
);
