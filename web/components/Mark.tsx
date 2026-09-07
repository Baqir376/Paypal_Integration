/**
 * The Salix mark.
 *
 * A willow leaf that is also a waveform: the outline is a lens shape struck
 * through by the three strokes of a conversation. Drawn rather than picked
 * from a set, and it carries the product's one accent colour.
 */

export function Mark({
  size = 24,
  style,
}: {
  size?: number;
  style?: React.CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      style={{ flexShrink: 0, ...style }}
      aria-hidden="true"
    >
      {/* The leaf: two arcs meeting at stem and tip. */}
      <path
        d="M12 1.6c5.4 3.3 8.2 7.2 8.2 10.9 0 4.6-3.7 8.3-8.2 9.9-4.5-1.6-8.2-5.3-8.2-9.9 0-3.7 2.8-7.6 8.2-10.9Z"
        stroke="currentColor"
        strokeWidth="1.35"
        strokeLinejoin="round"
      />
      {/* The conversation inside it. */}
      <path
        d="M8.5 12.4v-2.6M12 15.4V7.2M15.5 13.1v-3.4"
        stroke="var(--willow)"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}
