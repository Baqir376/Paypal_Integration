"use client";

/**
 * Console instruments.
 *
 * The orb, the waveform and the diagnostics panel. All three are meters, not
 * ornaments — they are wired to the same amplitude the microphone is actually
 * producing, and when there is no microphone they say so rather than faking a
 * signal. An animated waveform over a dead input is the interface lying about
 * what it knows, and that is precisely the failure this product exists to
 * catch in other people.
 */

import { useEffect, useRef, useState } from "react";

/* --------------------------------------------------------------------------
 * Live amplitude
 * ----------------------------------------------------------------------- */

export type Amplitude = {
  /** 0–1 overall loudness, already smoothed. */
  level: number;
  /** Per-band levels, low to high, for the bar visualiser. */
  bands: number[];
};

const BAND_COUNT = 48;
const SILENT: Amplitude = { level: 0, bands: new Array(BAND_COUNT).fill(0) };

/**
 * Read the microphone into a smoothed amplitude, for as long as `active`.
 *
 * The stream is opened when practice starts and released the moment it stops.
 * Holding a microphone open because the page might want it later is how a
 * browser ends up showing a recording indicator over an idle tab.
 */
export function useAmplitude(active: boolean): Amplitude {
  const [amplitude, setAmplitude] = useState<Amplitude>(SILENT);

  useEffect(() => {
    if (!active || typeof navigator === "undefined" || !navigator.mediaDevices) {
      setAmplitude(SILENT);
      return;
    }

    let context: AudioContext | null = null;
    let stream: MediaStream | null = null;
    let frame = 0;
    let cancelled = false;

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((granted) => {
        if (cancelled) {
          granted.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = granted;
        context = new AudioContext();
        const source = context.createMediaStreamSource(granted);
        const analyser = context.createAnalyser();
        // 512 bins over ~24kHz is roughly 47Hz per bin: enough resolution for
        // a voice to look like a voice, cheap enough to run every frame.
        analyser.fftSize = 1024;
        analyser.smoothingTimeConstant = 0.72;
        source.connect(analyser);

        const spectrum = new Uint8Array(analyser.frequencyBinCount);

        const read = () => {
          analyser.getByteFrequencyData(spectrum);

          // Speech lives under about 4kHz. Reading the whole spectrum wastes
          // most of the bars on silence above the voice.
          const usable = Math.floor(spectrum.length * 0.36);
          const per = Math.max(1, Math.floor(usable / BAND_COUNT));
          const bands: number[] = [];
          let total = 0;

          for (let band = 0; band < BAND_COUNT; band++) {
            let sum = 0;
            for (let i = 0; i < per; i++) sum += spectrum[band * per + i] ?? 0;
            const value = sum / per / 255;
            bands.push(value);
            total += value;
          }

          setAmplitude({ level: Math.min(1, (total / BAND_COUNT) * 2.4), bands });
          frame = requestAnimationFrame(read);
        };
        frame = requestAnimationFrame(read);
      })
      .catch(() => {
        // Permission refused, or no input device. The instruments read zero,
        // which is the truth.
        setAmplitude(SILENT);
      });

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((track) => track.stop());
      context?.close().catch(() => {});
      setAmplitude(SILENT);
    };
  }, [active]);

  return amplitude;
}

/* --------------------------------------------------------------------------
 * The orb
 * ----------------------------------------------------------------------- */

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

/**
 * The neural voice orb.
 *
 * Amplitude is written to a custom property rather than to React state, so a
 * value updating sixty times a second moves a box shadow instead of
 * re-rendering a subtree.
 */
export function Orb({
  state,
  level = 0,
  size,
}: {
  state: OrbState;
  level?: number;
  size?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.style.setProperty("--orb-amp", level.toFixed(3));
  }, [level]);

  return (
    <div
      ref={ref}
      className="sx-orb"
      data-state={state}
      style={size ? { width: size } : undefined}
      role="img"
      aria-label={
        {
          idle: "Engine idle",
          listening: "Listening",
          thinking: "Thinking",
          speaking: "Buyer speaking",
        }[state]
      }
    >
      <span className="sx-orb-ring sx-orb-ring-1" />
      <span className="sx-orb-ring sx-orb-ring-2" />
      <span className="sx-orb-ring sx-orb-ring-3" />
      <OrbTicks />
      <span className="sx-orb-core" />
    </div>
  );
}

/** The dial the amplitude is read against. */
function OrbTicks() {
  const ticks = Array.from({ length: 60 }, (_, i) => i);
  return (
    <svg className="sx-orb-ticks" viewBox="0 0 100 100" aria-hidden="true">
      {ticks.map((tick) => {
        const angle = (tick / ticks.length) * Math.PI * 2 - Math.PI / 2;
        const major = tick % 5 === 0;
        const inner = major ? 44 : 46.4;
        // Rounded to three places on purpose. Trigonometry in Node and
        // trigonometry in V8 disagree in the last bits of a double, and an
        // attribute that differs by 1e-14 is still a hydration mismatch.
        const at = (radius: number, fn: (n: number) => number) =>
          (50 + fn(angle) * radius).toFixed(3);
        return (
          <line
            key={tick}
            x1={at(inner, Math.cos)}
            y1={at(inner, Math.sin)}
            x2={at(48, Math.cos)}
            y2={at(48, Math.sin)}
            stroke={major ? "var(--accent-gold)" : "var(--text-quaternary)"}
            strokeWidth={major ? 0.7 : 0.4}
          />
        );
      })}
    </svg>
  );
}

/* --------------------------------------------------------------------------
 * The waveform
 * ----------------------------------------------------------------------- */

/**
 * A bar visualiser over live bands.
 *
 * When `bands` is all zeros the bars sit at a floor rather than collapsing to
 * nothing, so a silent input reads as a quiet instrument rather than as a
 * broken one.
 */
export function Waveform({
  bands,
  live,
  voice = "rep",
}: {
  bands: number[];
  live: boolean;
  voice?: "rep" | "buyer";
}) {
  return (
    <div className="sx-wave" data-live={live} data-voice={voice} aria-hidden="true">
      {bands.map((value, index) => (
        <span
          key={index}
          className="sx-wave-bar"
          style={{ "--h": Math.max(0.045, value) } as React.CSSProperties}
        />
      ))}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Diagnostics
 * ----------------------------------------------------------------------- */

export type Diagnostic = {
  label: string;
  value: string;
  tone?: "signal" | "gold" | "muted";
};

export function Diagnostics({
  title,
  rows,
  foot,
}: {
  title: string;
  rows: Diagnostic[];
  foot?: React.ReactNode;
}) {
  return (
    <div className="sx-diag">
      <div className="sx-diag-head">
        <span>{title}</span>
        <span style={{ color: "var(--accent-signal)" }}>●</span>
      </div>
      {rows.map((row) => (
        <div className="sx-diag-row" key={row.label} data-tone={row.tone ?? "signal"}>
          <span>{row.label}</span>
          <b>{row.value}</b>
        </div>
      ))}
      {foot}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Typewriter
 * ----------------------------------------------------------------------- */

/**
 * Reveal text a character at a time as it arrives.
 *
 * Used for the buyer's reply, which streams in over SSE. The typewriter runs
 * *behind* the stream rather than ahead of it: it never types a character the
 * server has not sent, so the effect can never claim words the model did not
 * produce. If the stream outruns the typist the speed rises to catch up rather
 * than the buffer growing without bound.
 */
export function useTypewriter(target: string, speed = 14): string {
  const [shown, setShown] = useState("");
  const index = useRef(0);

  useEffect(() => {
    // A new message — or a correction that shortened the text — restarts.
    if (!target.startsWith(shown)) {
      index.current = 0;
      setShown("");
      return;
    }
    if (index.current >= target.length) return;

    const behind = target.length - index.current;
    const step = behind > 90 ? Math.ceil(behind / 40) : 1;
    const timer = setTimeout(() => {
      index.current = Math.min(target.length, index.current + step);
      setShown(target.slice(0, index.current));
    }, speed);

    return () => clearTimeout(timer);
  }, [target, shown, speed]);

  return shown;
}
