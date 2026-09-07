"use client";

/**
 * The field: the room the whole product sits inside.
 *
 * A single fixed canvas behind every page, mounted once in the root layout and
 * never unmounted. That matters for more than tidiness -- a canvas per route
 * would create and destroy a WebGL context on every navigation, and a browser
 * grants only a handful before it starts force-losing the ones still in use.
 * One context, for the life of the document.
 *
 * What it draws is the product's own subject rather than generic space dust:
 * conversation threads receding into depth, and the motes of a room with air in
 * it. Two speakers, two colours, the same duotone the transcript uses.
 *
 * It answers to three things:
 *   - the pointer, as parallax, damped so it drifts rather than snaps;
 *   - the scroll position, which pushes the camera through the threads;
 *   - the route, which sets how much of itself it shows. The landing page is
 *     composed to be looked at, so it gets the full scene. A console someone
 *     reads all day gets a quiet version at a third the density, because
 *     depth behind a number must never compete with the number.
 *
 * It draws nothing at all under `prefers-reduced-motion`, or where WebGL is
 * unavailable. The CSS atmosphere underneath is the floor, and the page is
 * designed to be complete without this.
 */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { token } from "@/lib/tokens";
import * as THREE from "three";

import { capabilities } from "./caps";

/* --------------------------------------------------------------------------
 * Palette
 *
 * Hard-coded rather than read from CSS custom properties: these are lit in a
 * linear colour space against black, and the token values are chosen for text
 * on paper. They are the same two hues, tuned for light.
 * ----------------------------------------------------------------------- */

const REP = new THREE.Color("#4fd6c8");
const BUYER = new THREE.Color("#c98fd4");
// Read from the stylesheet so the palette lives in exactly one place.
const WILLOW = new THREE.Color(token("--willow"));

interface Tuning {
  motes: number;
  threads: number;
  moteOpacity: number;
  threadOpacity: number;
  /** How far the camera travels through the scene over a full scroll. */
  scrollDepth: number;
  parallax: number;
}

const CINEMATIC: Tuning = {
  motes: 900,
  threads: 7,
  moteOpacity: 0.85,
  threadOpacity: 0.5,
  scrollDepth: 5.2,
  parallax: 0.85,
};

/* A third the density and half the brightness. Behind a table of numbers this
   has to read as depth, not as content. */
const AMBIENT: Tuning = {
  motes: 300,
  threads: 4,
  moteOpacity: 0.42,
  threadOpacity: 0.22,
  scrollDepth: 1.4,
  parallax: 0.34,
};

/* --------------------------------------------------------------------------
 * Motes
 * ----------------------------------------------------------------------- */

/**
 * Points drawn as soft discs.
 *
 * A shader rather than a sprite texture: `gl_PointCoord` gives a round, feathered
 * point for a couple of instructions and no image to load or decode. Size
 * attenuates with depth so the field reads as a volume rather than a flat
 * scatter, and each mote carries its own phase so they drift independently
 * instead of pulsing as one.
 */
function Motes({ count, opacity, dark }: { count: number; opacity: number; dark: boolean }) {
  const points = useRef<THREE.Points>(null);

  const { geometry, material } = useMemo(() => {
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const scales = new Float32Array(count);
    const phases = new Float32Array(count);

    const color = new THREE.Color();
    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 30;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 15;
      // The whole volume sits well behind the camera's near field. Motes
      // allowed close in are drawn enormous by size attenuation and, because
      // only a narrow cone is visible that near, they pile into the middle of
      // the frame as one bright clot rather than reading as depth.
      positions[i * 3 + 2] = -24 + Math.random() * 19;

      // Mostly the two speaker hues, with willow as the rare accent -- the same
      // rationing the interface uses for its one accent colour.
      const roll = Math.random();
      color.copy(roll < 0.46 ? REP : roll < 0.92 ? BUYER : WILLOW);
      colors[i * 3] = color.r;
      colors[i * 3 + 1] = color.g;
      colors[i * 3 + 2] = color.b;

      // Cubed, so most motes are small and a few carry the field.
      scales[i] = Math.pow(Math.random(), 3) * 20 + 2.2;
      phases[i] = Math.random() * Math.PI * 2;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute("aScale", new THREE.BufferAttribute(scales, 1));
    geometry.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));

    const material = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      // Additive light only adds. Over the dark theme that is exactly right --
      // motes glow. Over paper it cannot lighten what is already near-white, so
      // the canvas composites its own dark-on-transparent pixels onto the page
      // and every mote lands as a grey smudge. On paper they are ink instead:
      // ordinary alpha, full colour, low opacity.
      blending: dark ? THREE.AdditiveBlending : THREE.NormalBlending,
      uniforms: {
        uTime: { value: 0 },
        uOpacity: { value: opacity },
      },
      vertexShader: /* glsl */ `
        attribute float aScale;
        attribute float aPhase;
        uniform float uTime;
        varying vec3 vColor;
        varying float vFade;

        void main() {
          vColor = color;

          vec3 p = position;
          // A slow rise with a lateral sway, wrapped so the field never empties.
          p.y = mod(p.y + uTime * 0.16 + 7.5, 15.0) - 7.5;
          p.x += sin(uTime * 0.22 + aPhase) * 0.42;

          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          gl_Position = projectionMatrix * mv;

          float d = max(-mv.z, 1.0);
          // Capped: one mote drifting close to the camera should not become a
          // hundred-pixel disc across the middle of somebody's dashboard.
          gl_PointSize = min(aScale * (13.0 / d), 30.0);

          // Fade at both ends of the volume so nothing pops into or out of view.
          vFade = smoothstep(3.0, 9.0, d) * (1.0 - smoothstep(22.0, 34.0, d));
        }
      `,
      fragmentShader: /* glsl */ `
        uniform float uOpacity;
        varying vec3 vColor;
        varying float vFade;

        void main() {
          // Round, feathered point straight from the point coordinate.
          float d = length(gl_PointCoord - vec2(0.5));
          if (d > 0.5) discard;
          float alpha = smoothstep(0.5, 0.06, d);
          gl_FragColor = vec4(vColor, alpha * vFade * uOpacity);
        }
      `,
      vertexColors: true,
    });

    return { geometry, material };
  }, [count, opacity, dark]);

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);

  useFrame((state) => {
    material.uniforms.uTime.value = state.clock.elapsedTime;
  });

  return <points ref={points} geometry={geometry} material={material} />;
}

/* --------------------------------------------------------------------------
 * Threads
 * ----------------------------------------------------------------------- */

/**
 * Long, thin ribbons crossing the volume: the conversation shape, seen from
 * far enough away to be atmosphere rather than data.
 *
 * Built once as tubes and animated by moving the group, never by rebuilding
 * geometry -- a curve rebuilt each frame is the easy way to make a background
 * cost more than the page in front of it.
 */
function Threads({ count, opacity, dark }: { count: number; opacity: number; dark: boolean }) {
  const group = useRef<THREE.Group>(null);

  const threads = useMemo(() => {
    const made: { geometry: THREE.TubeGeometry; material: THREE.MeshBasicMaterial; phase: number; y: number }[] = [];

    for (let i = 0; i < count; i++) {
      const t = count === 1 ? 0.5 : i / (count - 1);
      const y = (t - 0.5) * 9.5;
      const z = -13 + t * 9 + (Math.random() - 0.5) * 2.6;

      // Five control points across the volume, with a gentle vertical wander.
      const controls: THREE.Vector3[] = [];
      for (let k = 0; k < 5; k++) {
        const u = k / 4;
        controls.push(
          new THREE.Vector3(
            -15 + u * 30,
            y + Math.sin(u * Math.PI * 1.6 + i) * 1.5,
            z + Math.cos(u * Math.PI * 1.2 + i * 0.7) * 1.4,
          ),
        );
      }

      const curve = new THREE.CatmullRomCurve3(controls, false, "catmullrom", 0.5);
      // 3 radial segments: at this radius nobody can tell it is a triangle,
      // and it is a third of the vertices of a hexagonal tube.
      const geometry = new THREE.TubeGeometry(curve, 96, 0.016, 3, false);

      const material = new THREE.MeshBasicMaterial({
        color: REP.clone().lerp(BUYER, t),
        transparent: true,
        opacity: opacity * (0.45 + 0.55 * (1 - Math.abs(t - 0.5) * 2)),
        depthWrite: false,
        blending: dark ? THREE.AdditiveBlending : THREE.NormalBlending,
      });

      made.push({ geometry, material, phase: i * 1.27, y });
    }
    return made;
  }, [count, opacity, dark]);

  useEffect(
    () => () => {
      for (const thread of threads) {
        thread.geometry.dispose();
        thread.material.dispose();
      }
    },
    [threads],
  );

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const node = group.current;
    if (!node) return;
    node.children.forEach((child, i) => {
      const thread = threads[i];
      if (!thread) return;
      child.position.y = Math.sin(t * 0.14 + thread.phase) * 0.5;
      child.rotation.z = Math.sin(t * 0.09 + thread.phase) * 0.045;
    });
  });

  return (
    <group ref={group}>
      {threads.map((thread, i) => (
        <mesh key={i} geometry={thread.geometry} material={thread.material} />
      ))}
    </group>
  );
}

/* --------------------------------------------------------------------------
 * Camera
 * ----------------------------------------------------------------------- */

/**
 * Moves the camera, and is the only thing that does.
 *
 * Pointer and scroll are both read from refs written by plain DOM listeners
 * rather than React state: this runs every frame, and re-rendering the tree
 * sixty times a second to move a camera is how a background starts costing
 * more than the interface. Everything is damped toward a target, so a flicked
 * cursor drifts to a stop instead of snapping.
 */
function Rig({ tuning }: { tuning: Tuning }) {
  const { camera } = useThree();
  const pointer = useRef({ x: 0, y: 0 });
  const scroll = useRef(0);

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      pointer.current.x = (event.clientX / window.innerWidth - 0.5) * 2;
      pointer.current.y = (event.clientY / window.innerHeight - 0.5) * 2;
    };
    const onScroll = () => {
      const span = document.documentElement.scrollHeight - window.innerHeight;
      scroll.current = span > 0 ? Math.min(1, window.scrollY / span) : 0;
    };
    // Pointer parallax is a nicety; on a touch screen there is no pointer to
    // follow and the listener is pure cost.
    const fine = window.matchMedia("(pointer: fine)").matches;
    if (fine) window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  useFrame((_, delta) => {
    // Frame-rate independent damping: the same feel at 60Hz and at 144Hz.
    const k = 1 - Math.pow(0.0016, delta);

    const targetX = pointer.current.x * tuning.parallax;
    const targetY = -pointer.current.y * tuning.parallax * 0.6;
    const targetZ = 6.4 - scroll.current * tuning.scrollDepth;

    camera.position.x += (targetX - camera.position.x) * k;
    camera.position.y += (targetY - camera.position.y) * k;
    camera.position.z += (targetZ - camera.position.z) * k;
    camera.lookAt(0, 0, -6);
  });

  return null;
}

/* --------------------------------------------------------------------------
 * The field itself
 * ----------------------------------------------------------------------- */

/** Watches the document's resolved theme, both the toggle and the preference. */
function useIsDark(): boolean {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const read = () => {
      const attribute = document.documentElement.getAttribute("data-theme");
      setDark(attribute ? attribute === "dark" : query.matches);
    };
    read();
    query.addEventListener("change", read);
    // The toggle writes `data-theme` on the root element rather than firing an
    // event, so the attribute itself is what there is to watch.
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      query.removeEventListener("change", read);
      observer.disconnect();
    };
  }, []);

  return dark;
}

export function Field() {
  const pathname = usePathname();
  const [enabled, setEnabled] = useState(false);
  const dark = useIsDark();
  const wrapper = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Mounted only after the client has answered both questions, so the server
    // renders nothing and there is no hydration mismatch to reconcile.
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const decide = () => setEnabled(capabilities().webgl && !reduced.matches);
    decide();
    reduced.addEventListener("change", decide);
    return () => reduced.removeEventListener("change", decide);
  }, []);

  const cinematic = pathname === "/";
  const tuning = cinematic ? CINEMATIC : AMBIENT;

  // The cinematic density is composed for the hero, where a scrim sits between
  // it and the type. Below the fold there is no scrim and the same field reads
  // as noise behind body copy, so it fades back over the first screen. Written
  // straight to the node: this runs on every scroll frame and re-rendering a
  // WebGL tree to change one opacity would be absurd.
  useEffect(() => {
    const node = wrapper.current;
    if (!node || !cinematic) return;

    let frame = 0;
    const update = () => {
      frame = 0;
      const t = Math.min(1, window.scrollY / Math.max(1, window.innerHeight));
      node.style.opacity = (1 - t * 0.66).toFixed(3);
    };
    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(frame);
    };
  }, [cinematic, enabled]);

  // Paper carries far less of this than black does before it starts competing
  // with the text sitting on it.
  const moteOpacity = tuning.moteOpacity * (dark ? 1 : 0.5);
  const threadOpacity = tuning.threadOpacity * (dark ? 1 : 0.55);

  if (!enabled) return null;

  return (
    <div ref={wrapper} className="depth-field no-print" aria-hidden="true">
      <Canvas
        camera={{ position: [0, 0, 6.4], fov: 46 }}
        dpr={[1, 1.5]}
        gl={{ antialias: false, alpha: true, powerPreference: "low-power" }}
        onCreated={({ gl }) => {
          gl.setClearColor(0x000000, 0);
          // If the browser reclaims this context there is nothing to fall back
          // to and nothing worth recovering -- the field is decoration. Take
          // the dead canvas out of the page rather than leaving a blank one
          // sitting over the atmosphere that was doing the job underneath.
          gl.domElement.addEventListener(
            "webglcontextlost",
            (event) => {
              if (!(event.target as HTMLCanvasElement).isConnected) return;
              event.preventDefault();
              setEnabled(false);
            },
            { once: true },
          );
        }}
        style={{ pointerEvents: "none" }}
      >
        <Motes
          key={`motes-${tuning.motes}-${dark}`}
          count={tuning.motes}
          opacity={moteOpacity}
          dark={dark}
        />
        <Threads
          key={`threads-${tuning.threads}-${dark}`}
          count={tuning.threads}
          opacity={threadOpacity}
          dark={dark}
        />
        <Rig tuning={tuning} />
      </Canvas>
    </div>
  );
}
