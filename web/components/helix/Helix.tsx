"use client";

/**
 * The Conversation Helix.
 *
 * A call rendered as a twisting ribbon: it rises when the rep holds the floor,
 * corkscrews when the conversation is genuinely two-sided, and pinches thin
 * through silence. Objections notch it; plays glow on it.
 *
 * What separates this from a plotted chart is the finishing, and each piece
 * earns its cost:
 *
 *   - Geometry is spline-smoothed (see geometry.ts). Without it the ribbon
 *     spikes and folds through itself.
 *   - An iridescent shader tints the surface by its angle to the viewer, so
 *     the twist is visible as a shift in colour rather than only in silhouette.
 *   - Selective bloom picks up the emissive edges and the markers, which is
 *     what makes it read as lit rather than filled.
 *   - Film grain and vignette sit over the whole frame. This is the cheapest
 *     large gain in perceived quality available.
 *
 * All of it degrades. WebGL missing, context lost, or a low-core device: the
 * SVG rendering of the same three signals takes over, and post-processing is
 * dropped before geometry is.
 */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer, Noise } from "@react-three/postprocessing";
import { BlendFunction, KernelSize } from "postprocessing";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { token } from "@/lib/tokens";

import type { CallAnalysis, CallMetrics, PlayWithInstance } from "@/lib/types";
import { clock } from "@/lib/format";

import { capabilities } from "../three/caps";

import { buildHelix, pointAt, timeToX } from "./geometry";
import { HelixFlat } from "./HelixFlat";

const REP_HEX = "#4fd6c8";
const BUYER_HEX = "#c98fd4";

export interface HelixMarker {
  ms: number;
  kind: "objection" | "play" | "monologue" | "next_step";
  label: string;
  detail?: string;
}

interface HelixProps {
  metrics: CallMetrics;
  analysis?: CallAnalysis | null;
  plays?: PlayWithInstance[];
  positionMs?: number;
  onSeek?: (ms: number) => void;
  /** Any CSS length. The landing hero passes "100%" to fill its stage. */
  height?: number | string;
  interactive?: boolean;
  /** Landing hero uses a slower, wider presentation. */
  cinematic?: boolean;
  /** The marker key. Off where the ribbon is a backdrop rather than a chart. */
  legend?: boolean;
}

export function markersFor(
  metrics: CallMetrics,
  analysis?: CallAnalysis | null,
  plays: PlayWithInstance[] = [],
): HelixMarker[] {
  const markers: HelixMarker[] = [];

  for (const objection of analysis?.objections ?? []) {
    const ms = objection.raised?.start_ms;
    if (ms == null) continue;
    markers.push({
      ms,
      kind: "objection",
      label: objection.category.replace("_", " "),
      detail: objection.text,
    });
  }

  for (const play of plays) {
    const ms = play.instance?.evidence?.[0]?.start_ms;
    markers.push({
      ms: ms ?? metrics.duration_ms * 0.5,
      kind: "play",
      label: play.name,
      detail: play.thesis,
    });
  }

  if (metrics.longest_monologue_ms > 120_000) {
    markers.push({
      ms: metrics.longest_monologue_at_ms,
      kind: "monologue",
      label: `${Math.round(metrics.longest_monologue_ms / 1000)}s monologue`,
      detail: "The rep held the floor without a handoff.",
    });
  }

  const next = analysis?.next_step?.evidence?.start_ms;
  if (next != null) {
    markers.push({ ms: next, kind: "next_step", label: "Next step agreed" });
  }

  return markers.sort((a, b) => a.ms - b.ms);
}

const MARKER_COLOR: Record<HelixMarker["kind"], string> = {
  objection: "#f0b46a",
  play: token("--willow"),
  monologue: "#e895a6",
  next_step: "#8fd4a4",
};

/* -------------------------------------------------------------------------
 * Ribbon material
 *
 * Physical shading plus a hand-written iridescence term. The onBeforeCompile
 * injection is deliberate: MeshPhysicalMaterial's own iridescence is a thin-
 * film model tuned for soap and oil, and it washes out the vertex colours that
 * carry who is speaking. This adds a narrow fresnel-driven hue shift on top of
 * the existing shading instead of replacing it.
 * ---------------------------------------------------------------------- */

function useRibbonMaterial(reducedMotion: boolean) {
  return useMemo(() => {
    const material = new THREE.MeshPhysicalMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      roughness: 0.42,
      metalness: 0.12,
      clearcoat: 0.45,
      clearcoatRoughness: 0.4,
      emissive: new THREE.Color("#08131a"),
      emissiveIntensity: 0.3,
    });

    material.onBeforeCompile = (shader) => {
      shader.uniforms.uTime = { value: 0 };
      material.userData.shader = shader;

      shader.fragmentShader = shader.fragmentShader
        .replace(
          "#include <common>",
          `#include <common>
           uniform float uTime;
           // Edge-weighted rainbow. Peaks where the surface turns away from
           // the camera, which is exactly where the twist lives.
           vec3 irid(float f) {
             return 0.5 + 0.5 * cos(6.28318 * (vec3(0.0, 0.33, 0.67) + f));
           }`,
        )
        .replace(
          "#include <dithering_fragment>",
          `#include <dithering_fragment>
           vec3 vd = normalize(vViewPosition);
           float fres = pow(1.0 - clamp(dot(normalize(vNormal), vd), 0.0, 1.0), 2.4);
           vec3 sheen = irid(fres * 0.85 + uTime * 0.015);
           gl_FragColor.rgb += sheen * fres * 0.11;
           // Lift the very edge so the silhouette stays crisp against the
           // background rather than dissolving into it.
           gl_FragColor.rgb += vec3(0.45, 0.80, 0.78) * pow(fres, 7.0) * 0.22;`,
        );
    };

    return material;
  }, [reducedMotion]);
}

/* -------------------------------------------------------------------------
 * Scene
 * ---------------------------------------------------------------------- */

function Ribbon({
  metrics,
  markers,
  positionMs,
  onSeek,
  reducedMotion,
  cinematic,
}: {
  metrics: CallMetrics;
  markers: HelixMarker[];
  positionMs: number;
  onSeek?: (ms: number) => void;
  reducedMotion: boolean;
  cinematic: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const { pointer } = useThree();
  const material = useRibbonMaterial(reducedMotion);

  const build = useMemo(
    () => buildHelix(metrics.timeline, REP_HEX, BUYER_HEX),
    [metrics.timeline],
  );

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(build.positions, 3));
    g.setAttribute("color", new THREE.BufferAttribute(build.colors, 3));
    g.setAttribute("normal", new THREE.BufferAttribute(build.normals, 3));
    g.setAttribute("uv", new THREE.BufferAttribute(build.uvs, 2));
    g.setIndex(new THREE.BufferAttribute(build.indices, 1));
    g.computeBoundingSphere();
    return g;
  }, [build]);

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);

  useFrame((state, delta) => {
    const shader = material.userData.shader;
    if (shader) shader.uniforms.uTime.value = state.clock.elapsedTime;

    if (!group.current) return;
    if (reducedMotion) {
      group.current.rotation.set(-0.16, cinematic ? -0.32 : 0, 0);
      return;
    }

    // Weighted parallax toward the cursor, plus a very slow drift on the hero
    // so a still page is not a still image. No spin: this is an instrument.
    const idle = cinematic ? Math.sin(state.clock.elapsedTime * 0.11) * 0.19 : 0;
    const targetY = pointer.x * 0.3 + idle - (cinematic ? 0.3 : 0);
    const targetX = -0.16 + pointer.y * 0.13;
    const k = Math.min(1, delta * 2.4);
    group.current.rotation.y += (targetY - group.current.rotation.y) * k;
    group.current.rotation.x += (targetX - group.current.rotation.x) * k;
  });

  const head = pointAt(build, positionMs, metrics.duration_ms);
  const headX = timeToX(positionMs, metrics.duration_ms);

  return (
    <group ref={group}>
      {/* Time axis. Thin, dim, and behind everything. */}
      <mesh position={[0, 0, -0.02]}>
        <boxGeometry args={[11.4, 0.004, 0.004]} />
        <meshBasicMaterial color="#3a3a44" toneMapped={false} />
      </mesh>

      <mesh
        geometry={geometry}
        material={material}
        onPointerDown={(event) => {
          if (!onSeek) return;
          event.stopPropagation();
          const t = (event.point.x + 5.5) / 11;
          onSeek(Math.max(0, Math.min(1, t)) * metrics.duration_ms);
        }}
      />

      {markers.map((marker, index) => {
        const [x, y, z] = pointAt(build, marker.ms, metrics.duration_ms);
        const isPlay = marker.kind === "play";
        return (
          <group key={`${marker.kind}-${index}`} position={[x, y, z]}>
            <mesh>
              <sphereGeometry args={[isPlay ? 0.075 : 0.058, 20, 20]} />
              <meshBasicMaterial
                color={MARKER_COLOR[marker.kind]}
                toneMapped={false}
              />
            </mesh>
            {/* A dim halo so bloom has something to catch. */}
            <mesh>
              <sphereGeometry args={[isPlay ? 0.17 : 0.13, 16, 16]} />
              <meshBasicMaterial
                color={MARKER_COLOR[marker.kind]}
                transparent
                opacity={0.14}
                toneMapped={false}
                depthWrite={false}
              />
            </mesh>
          </group>
        );
      })}

      {/* Playhead */}
      <mesh position={head}>
        <sphereGeometry args={[0.05, 16, 16]} />
        <meshBasicMaterial color="#ffffff" toneMapped={false} />
      </mesh>
      <mesh position={[headX, 0, 0]}>
        <boxGeometry args={[0.008, 2.7, 0.008]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.2} toneMapped={false} />
      </mesh>
    </group>
  );
}

/** Slow-drifting motes. Cheap parallax that gives the void a sense of scale. */
function Dust({ count = 140 }: { count?: number }) {
  const points = useRef<THREE.Points>(null);

  const geometry = useMemo(() => {
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 16;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 7;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 6 - 1.5;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return g;
  }, [count]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  useFrame((state) => {
    if (points.current) {
      points.current.rotation.y = state.clock.elapsedTime * 0.012;
    }
  });

  return (
    <points ref={points} geometry={geometry}>
      <pointsMaterial
        size={0.022}
        color="#8fa0a8"
        transparent
        opacity={0.4}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  );
}

/* -------------------------------------------------------------------------
 * Wrapper
 * ---------------------------------------------------------------------- */

export function Helix({
  metrics,
  analysis,
  plays = [],
  positionMs = 0,
  onSeek,
  height = 320,
  interactive = true,
  cinematic = false,
  legend = true,
}: HelixProps) {
  const [caps, setCaps] = useState<{ webgl: boolean; heavy: boolean } | null>(null);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setCaps(capabilities());
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(query.matches);
    const onChange = () => setReducedMotion(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const markers = useMemo(
    () => markersFor(metrics, analysis, plays),
    [metrics, analysis, plays],
  );

  if (caps === null) {
    return <div className="skeleton" style={{ height, borderRadius: 12 }} />;
  }

  if (!caps.webgl || failed) {
    return (
      <HelixFlat
        metrics={metrics}
        markers={markers}
        positionMs={positionMs}
        onSeek={onSeek}
        height={height}
      />
    );
  }

  const postfx = caps.heavy && !reducedMotion;

  return (
    <div style={{ height, position: "relative" }}>
      <Canvas
        camera={{ position: cinematic ? [0.4, 0.7, 7.6] : [0, 0.5, 7.4], fov: 40 }}
        // 1.5 on high-DPI rather than 2: roughly 44% of the GPU cost for a
        // difference nobody can see at this size.
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        onCreated={({ gl }) => {
          gl.setClearColor(0x000000, 0);
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 0.98;
          // A dropped context leaves a frozen or blank canvas, and nothing in
          // React notices. Catching it is what makes the promised degradation
          // to the SVG rendering actually happen.
          //
          // Only while the canvas is still on the page, though: three.js
          // deliberately force-loses the context when it disposes the
          // renderer, so an unmount fires this event too and would otherwise
          // look identical to the browser taking the context away.
          gl.domElement.addEventListener(
            "webglcontextlost",
            (event) => {
              if (!(event.target as HTMLCanvasElement).isConnected) return;
              event.preventDefault();
              setFailed(true);
            },
            { once: true },
          );
          setReady(true);
        }}
        onError={() => setFailed(true)}
        style={{
          pointerEvents: interactive ? "auto" : "none",
          // Fade in rather than popping a black rectangle on first frame.
          opacity: ready ? 1 : 0,
          transition: "opacity 900ms cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        {/* Three lights, each with a job: a cool key from the front-right, a
            warm willow rim from behind-left, and a dim fill so the far face
            never goes fully black. */}
        <ambientLight intensity={0.55} />
        <directionalLight position={[4, 5, 6]} intensity={2.1} color="#dff3ff" />
        <directionalLight position={[-5, -2, -4]} intensity={1.1} color={token("--willow")} />
        <directionalLight position={[0, -4, 2]} intensity={0.5} color="#7fd8ff" />

        <Ribbon
          metrics={metrics}
          markers={markers}
          positionMs={positionMs}
          onSeek={onSeek}
          reducedMotion={reducedMotion}
          cinematic={cinematic}
        />
        {cinematic && <Dust />}

        {postfx && (
          <EffectComposer multisampling={0}>
            {/* Threshold sits high on purpose: only the markers and the
                specular edge should bloom. Lower and the whole ribbon
                blows out into a white smear. */}
            <Bloom
              intensity={cinematic ? 0.7 : 0.45}
              luminanceThreshold={0.92}
              luminanceSmoothing={0.2}
              kernelSize={KernelSize.MEDIUM}
              mipmapBlur
            />
            <Noise opacity={0.022} blendFunction={BlendFunction.OVERLAY} />
          </EffectComposer>
        )}
      </Canvas>

      {legend && <HelixLegend markers={markers} duration={metrics.duration_ms} />}
    </div>
  );
}

function HelixLegend({
  markers,
  duration,
}: {
  markers: HelixMarker[];
  duration: number;
}) {
  const kinds = Array.from(new Set(markers.map((m) => m.kind)));
  return (
    <div
      className="no-print"
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        pointerEvents: "none",
      }}
    >
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        <LegendSwatch color={REP_HEX} label="rep" />
        <LegendSwatch color={BUYER_HEX} label="buyer" />
        {kinds.map((kind) => (
          <LegendSwatch
            key={kind}
            color={MARKER_COLOR[kind]}
            label={kind.replace("_", " ")}
          />
        ))}
      </div>
      <span className="num" style={{ fontSize: 11, color: "var(--ink-3)" }}>
        {clock(duration)}
      </span>
    </div>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span
      className="eyebrow"
      style={{ display: "inline-flex", alignItems: "center", gap: 5 }}
    >
      <i
        style={{
          width: 6,
          height: 6,
          borderRadius: 999,
          background: color,
          boxShadow: `0 0 8px ${color}`,
          display: "inline-block",
        }}
      />
      {label}
    </span>
  );
}
