"use client";

/**
 * Logging in, signing up and choosing a new password.
 *
 * Google or a password, and the two share one Google flow, because the server decides on
 * the way back: a known account signs in, and a new one gets a team. Logging in and signing
 * up are still separate addresses, because somebody clicking "Get started" should not be
 * greeted as though they had been here before, but moving between them only changes the
 * address, so the card stays put and its contents change in place.
 *
 * The product listens to conversations, so this screen does too. A pulse opens the card,
 * the leaf reacts to what is happening in the form and shuts while a password is typed, and
 * every keystroke runs through the ribbon of sound behind the glass. Everything behind
 * the card is decorative and hidden from screen readers, and the pop-ups are labelled
 * as samples.
 */

import {
  AnimatePresence,
  MotionConfig,
  animate,
  motion,
  useAnimationControls,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, MouseEvent, MutableRefObject, PointerEvent } from "react";

import { IconCheck } from "@/components/icons";
import { InfoTip } from "@/components/Pop";
import { ApiError, api } from "@/lib/api";
import type { Me } from "@/lib/types";

const ERRORS: Record<string, string> = {
  cancelled: "Sign-in was cancelled, and nothing was changed.",
  expired: "That took too long or was opened in another browser. Please try again.",
  failed: "Google could not confirm your account. Please try again.",
  not_configured: "Google sign-in is not set up on this server yet.",
  link_expired: "That link has expired. Log in and ask for a new one.",
};

type Mode = "login" | "signup" | "reset";
type View = Mode | "forgot";
type Mood = "idle" | "hiding" | "wrong" | "done";

const TITLES: Record<View, string> = {
  login: "Welcome back",
  signup: "Create your team",
  forgot: "Reset your password",
  reset: "Choose a new password",
};

const SUBMIT: Record<View, string> = {
  login: "Log in",
  signup: "Create account",
  forgot: "Email me a link",
  reset: "Save new password",
};

const MIN_PASSWORD = 10;
const EASE = [0.16, 1, 0.3, 1] as const;
const POP = { type: "spring", stiffness: 260, damping: 19, mass: 0.85 } as const;
/** How long the opening pulse holds the card back. */
const OPENING_MS = 820;
const WELCOME_KEY = "salix-welcome";

const stagger = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.055, delayChildren: 0.14 } },
};
const rise = {
  hidden: { opacity: 0, y: 14 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE } },
};

/** Only ever somewhere on this site, whatever the address bar was given. */
function safeNext(next: string): string {
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/console";
}

function rememberWelcome() {
  try {
    sessionStorage.setItem(WELCOME_KEY, "1");
  } catch {
    /* only costs a greeting */
  }
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.7 1.2 9.2 3.6l6.9-6.9C35.9 2.4 30.4 0 24 0 14.6 0 6.5 5.4 2.6 13.2l8 6.2C12.5 13.7 17.8 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.2 5.3-4.6 7l7.2 5.6c4.2-3.9 7.1-9.6 7.1-17.1z" />
      <path fill="#FBBC05" d="M10.6 28.6c-.5-1.4-.8-3-.8-4.6s.3-3.2.8-4.6l-8-6.2C.9 16.5 0 20.1 0 24s.9 7.5 2.6 10.8l8-6.2z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.2-5.6c-2.2 1.5-5.1 2.4-8.7 2.4-6.2 0-11.5-4.2-13.4-9.9l-8 6.2C6.5 42.6 14.6 48 24 48z" />
    </svg>
  );
}

function Eye({ open }: { open: boolean }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.8" />
      {!open && <path d="M4 4l16 16" />}
    </svg>
  );
}

/* ---------------------------------------------------------------------- */

const LEAF = "M12 1.6c5.4 3.3 8.2 7.2 8.2 10.9 0 4.6-3.7 8.3-8.2 9.9-4.5-1.6-8.2-5.3-8.2-9.9 0-3.7 2.8-7.6 8.2-10.9Z";
const STROKES = [
  { x: 8.5, y1: 9.8, y2: 12.4 },
  { x: 12, y1: 7.2, y2: 15.4 },
  { x: 15.5, y1: 9.7, y2: 13.1 },
];

/** The Salix leaf, alive. It hears keystrokes, shuts for passwords and flinches at errors. */
function Leaf({ mood, beat, size = 44 }: { mood: Mood; beat: number; size?: number }) {
  const controls = useAnimationControls();

  useEffect(() => {
    if (beat > 0) {
      controls.start((i: number) => ({
        scaleY: [1, 1.5 - i * 0.12, 1],
        transition: { duration: 0.28, delay: i * 0.025, ease: "easeOut" },
      }));
    }
  }, [beat, controls]);

  return (
    <motion.svg
      className="leaf"
      data-mood={mood}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      animate={mood === "wrong" ? { x: [0, -4, 4, -3, 3, 0] } : { x: 0 }}
      transition={{ duration: 0.4 }}
    >
      <motion.path
        d={LEAF}
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinejoin="round"
        className="leaf-outline"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.7, ease: "easeInOut" }}
      />
      <g className="leaf-strokes">
        {STROKES.map((stroke, i) => (
          <motion.line
            key={stroke.x}
            custom={i}
            animate={controls}
            x1={stroke.x}
            x2={stroke.x}
            y1={stroke.y1}
            y2={stroke.y2}
            strokeWidth="1.7"
            strokeLinecap="round"
            style={{ transformBox: "fill-box", transformOrigin: "center" }}
          />
        ))}
      </g>
    </motion.svg>
  );
}

/** The opening: a leaf drawn in the dark, then a pulse that pushes the card out of it. */
function Opening() {
  return (
    <motion.div className="auth-opening" aria-hidden="true" exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
      {[0, 1, 2].map((ring) => (
        <motion.i
          key={ring}
          initial={{ scale: 0.2, opacity: 0 }}
          animate={{ scale: 7, opacity: [0, 0.55, 0] }}
          transition={{ duration: 1, delay: 0.42 + ring * 0.12, ease: [0.2, 0.7, 0.2, 1] }}
        />
      ))}
      <motion.div
        initial={{ scale: 0.7, opacity: 0 }}
        animate={{ scale: [0.7, 1.08, 1], opacity: 1 }}
        exit={{ scale: 0.4, opacity: 0 }}
        transition={{ duration: 0.55, ease: EASE }}
      >
        <Leaf mood="idle" beat={0} size={76} />
      </motion.div>
    </motion.div>
  );
}

/* ---------------------------------------------------------------------- */

/** A ribbon of sound behind the glass. Typing raises it, and it leans towards the pointer. */
function VoiceRibbon({
  energy,
  pointer,
}: {
  energy: MutableRefObject<number>;
  pointer: MutableRefObject<{ x: number; y: number; on: boolean }>;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;

    let frame = 0;
    let width = 0;
    let height = 0;
    let lean = 0;

    const resize = () => {
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      element.width = width * scale;
      element.height = height * scale;
      context.setTransform(scale, 0, 0, scale, 0, 0);
    };

    const draw = (time: number) => {
      const t = time / 1000;
      context.clearRect(0, 0, width, height);
      energy.current *= 0.965;
      lean += ((pointer.current.on ? 1 : 0) - lean) * 0.05;
      const amplitude = 16 + height * 0.022 + energy.current * 86;
      const middle = height * 0.56;
      const stroke = context.createLinearGradient(0, 0, width, 0);
      stroke.addColorStop(0, "rgb(212 245 90 / 0)");
      stroke.addColorStop(0.2, "rgb(212 245 90 / 0.75)");
      stroke.addColorStop(0.55, "rgb(125 220 210 / 0.75)");
      stroke.addColorStop(0.82, "rgb(185 142 224 / 0.7)");
      stroke.addColorStop(1, "rgb(185 142 224 / 0)");
      context.strokeStyle = stroke;

      for (let ribbon = 0; ribbon < 6; ribbon++) {
        context.beginPath();
        context.globalAlpha = 0.16 + (ribbon === 2 ? 0.5 : ribbon * 0.05);
        context.lineWidth = ribbon === 2 ? 1.8 : 1;
        for (let x = 0; x <= width + 12; x += 12) {
          const wave =
            Math.sin(x * 0.0058 + t * 0.85 + ribbon * 0.62) +
            0.55 * Math.sin(x * 0.0147 - t * 1.25 + ribbon * 1.1) +
            energy.current * 0.5 * Math.sin(x * 0.041 + t * 7 + ribbon);
          let y = middle + (ribbon - 2.5) * 11 + wave * amplitude * (0.55 + ribbon * 0.12);
          const distance = x - pointer.current.x;
          y += Math.exp(-(distance * distance) / 42000) * (pointer.current.y - y) * 0.2 * lean;
          if (x === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        }
        context.stroke();
      }
      context.globalAlpha = 1;
      if (!reduced && !document.hidden) frame = requestAnimationFrame(draw);
    };

    const wake = () => {
      cancelAnimationFrame(frame);
      if (!document.hidden) frame = requestAnimationFrame(draw);
    };
    const onResize = () => {
      resize();
      if (reduced) draw(0);
    };

    resize();
    frame = requestAnimationFrame(draw);
    window.addEventListener("resize", onResize);
    if (!reduced) document.addEventListener("visibilitychange", wake);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
      document.removeEventListener("visibilitychange", wake);
    };
  }, [energy, pointer, reduced]);

  return <canvas ref={canvas} className="auth-ribbon" />;
}

/* ---------------------------------------------------------------------- */

const BARS = Array.from({ length: 13 }, (_, i) => (0.2 + 0.8 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * 0.43))).toFixed(3));

function SampleScore() {
  const count = useMotionValue(41);
  const rounded = useTransform(count, (value) => Math.round(value));

  useEffect(() => {
    const controls = animate(count, 86, { duration: 1.4, ease: EASE, delay: 0.15 });
    return () => controls.stop();
  }, [count]);

  return (
    <>
      <svg width="42" height="42" viewBox="0 0 42 42" className="signal-ring">
        <circle cx="21" cy="21" r="17" className="signal-track" />
        <motion.circle
          cx="21"
          cy="21"
          r="17"
          className="signal-arc"
          initial={{ pathLength: 0.41 }}
          animate={{ pathLength: 0.86 }}
          transition={{ duration: 1.4, ease: EASE, delay: 0.15 }}
        />
      </svg>
      <div>
        <strong className="signal-number">
          <motion.span>{rounded}</motion.span>
        </strong>
        <small>Deal score</small>
      </div>
    </>
  );
}

function SampleLanguage() {
  return (
    <>
      <div className="signal-bars">
        {BARS.map((height, i) => (
          <i key={i} style={{ "--h": height, animationDelay: `${i * -90}ms` } as React.CSSProperties} />
        ))}
      </div>
      <div>
        <strong>Roman Urdu</strong>
        <small>Detected</small>
      </div>
    </>
  );
}

function SampleEvent({ title, detail }: { title: string; detail: string }) {
  return (
    <>
      <span className="signal-tick">
        <IconCheck size={15} />
      </span>
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
    </>
  );
}

const SIGNALS = [
  { at: "a", body: <SampleScore /> },
  { at: "b", body: <SampleLanguage /> },
  { at: "c", body: <SampleEvent title="Objection handled" detail="Pricing" /> },
  { at: "d", body: <SampleEvent title="Next step booked" detail="Tuesday, 10am" /> },
];

/** One sample at a time pops up beside the card, shows what the product notices, and goes. */
function Signals({ active }: { active: boolean }) {
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!active || reduced) return;
    const timer = setInterval(() => setIndex((n) => (n + 1) % SIGNALS.length), 3400);
    return () => clearInterval(timer);
  }, [active, reduced]);

  if (!active) return null;
  const signal = SIGNALS[index];

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={signal.at}
        className={`signal signal-at-${signal.at}`}
        initial={{ opacity: 0, scale: 0.6, y: 18 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.88, y: -8, transition: { duration: 0.2 } }}
        transition={{ ...POP, delay: 0.2 }}
      >
        <span className="signal-tag">Sample</span>
        {signal.body}
      </motion.div>
    </AnimatePresence>
  );
}

/* ---------------------------------------------------------------------- */

function Heading({ text }: { text: string }) {
  return (
    <motion.h1
      aria-label={text}
      initial="hidden"
      animate="shown"
      exit={{ opacity: 0, y: -8, transition: { duration: 0.14 } }}
      variants={{ shown: { transition: { staggerChildren: 0.016 } } }}
    >
      {Array.from(text).map((letter, i) => (
        <motion.span
          key={i}
          aria-hidden="true"
          variants={{
            hidden: { opacity: 0, y: 14, rotateX: -70 },
            shown: { opacity: 1, y: 0, rotateX: 0, transition: { type: "spring", stiffness: 380, damping: 22 } },
          }}
        >
          {letter}
        </motion.span>
      ))}
    </motion.h1>
  );
}

function Screen() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const reduced = useReducedMotion();
  const mode: Mode = pathname?.startsWith("/signup") ? "signup" : pathname?.startsWith("/reset-password") ? "reset" : "login";
  const next = safeNext(search.get("next") ?? "/console");
  const error = search.get("error");
  const resetToken = search.get("token") ?? "";
  const [me, setMe] = useState<Me | null>(null);
  const [opened, setOpened] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [forgot, setForgot] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [inPassword, setInPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [finished, setFinished] = useState(false);
  const [beat, setBeat] = useState(0);
  const [wrong, setWrong] = useState(false);
  const [problem, setProblem] = useState<{ text: string; attempt: number } | null>(null);
  const [mailed, setMailed] = useState(false);
  const card = useRef<HTMLDivElement>(null);
  const energy = useRef(0);
  const pointer = useRef({ x: 0, y: 0, on: false });
  const view: View = mode === "login" && forgot ? "forgot" : mode;
  const showing = opened || reduced === true;

  const mood: Mood = finished ? "done" : wrong ? "wrong" : inPassword && !showPassword ? "hiding" : "idle";

  // The pointer, from -0.5 to 0.5 across the screen. Everything that follows it reads this.
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const springX = useSpring(pointerX, { stiffness: 70, damping: 20, mass: 0.6 });
  const springY = useSpring(pointerY, { stiffness: 70, damping: 20, mass: 0.6 });
  const rotateY = useTransform(springX, [-0.5, 0.5], [-4.5, 4.5]);
  const rotateX = useTransform(springY, [-0.5, 0.5], [4.5, -4.5]);
  const skyX = useTransform(springX, [-0.5, 0.5], [26, -26]);
  const skyY = useTransform(springY, [-0.5, 0.5], [18, -18]);

  useEffect(() => {
    const timer = setTimeout(() => setOpened(true), OPENING_MS);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    api
      .me()
      .then((state) => {
        setMe(state);
        // Somebody who opened a reset link while signed in still came here to reset.
        if (mode !== "reset" && (state.user || !state.auth_required)) router.replace(next);
      })
      .catch(() => setMe(null));
    // Back from Google's page with the browser's cache, the button must be live again.
    const reset = () => setLeaving(false);
    window.addEventListener("pageshow", reset);
    return () => window.removeEventListener("pageshow", reset);
  }, [router, next, mode]);

  const follow = (event: PointerEvent<HTMLElement>) => {
    if (event.pointerType === "touch" || reduced) return;
    pointerX.set(event.clientX / window.innerWidth - 0.5);
    pointerY.set(event.clientY / window.innerHeight - 0.5);
    pointer.current = { x: event.clientX, y: event.clientY, on: true };
    const box = card.current?.getBoundingClientRect();
    if (box) {
      card.current?.style.setProperty("--mx", `${event.clientX - box.left}px`);
      card.current?.style.setProperty("--my", `${event.clientY - box.top}px`);
    }
  };

  const settle = () => {
    pointerX.set(0);
    pointerY.set(0);
    pointer.current = { ...pointer.current, on: false };
  };

  /** A keystroke, heard by the leaf and the ribbon. */
  const hear = useCallback(() => {
    setBeat((n) => n + 1);
    energy.current = Math.min(energy.current + 0.3, 1.5);
  }, []);

  const flinch = (text: string) => {
    setProblem({ text, attempt: Date.now() });
    setWrong(true);
    setTimeout(() => setWrong(false), 900);
  };

  const hrefFor = (target: Mode) => {
    const path = target === "signup" ? "/signup" : "/login";
    return next === "/console" ? path : `${path}?next=${encodeURIComponent(next)}`;
  };

  // A new tab still opens a new tab. Otherwise only the address changes, and the card stays.
  const switchTo = (target: Mode) => (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    setForgot(false);
    setProblem(null);
    setMailed(false);
    energy.current = Math.min(energy.current + 0.5, 1.5);
    if (target !== mode) window.history.pushState(null, "", hrefFor(target));
  };

  const showForgot = (open: boolean) => {
    setForgot(open);
    setProblem(null);
    setMailed(false);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setProblem(null);
    if ((view === "signup" || view === "reset") && password.length < MIN_PASSWORD) {
      flinch(`Use at least ${MIN_PASSWORD} characters for your password.`);
      return;
    }
    setBusy(true);
    try {
      if (view === "forgot") {
        await api.forgotPassword(email);
        setMailed(true);
        energy.current = 1.2;
      } else {
        if (view === "signup") await api.signup(name, email, password);
        else if (view === "reset") await api.resetPassword(resetToken, password);
        else await api.login(email, password);
        rememberWelcome();
        setFinished(true);
        setInPassword(false);
        energy.current = 1.5;
        await new Promise((resolve) => setTimeout(resolve, reduced ? 0 : 480));
        // A full navigation, so that everything is loaded as this person.
        window.location.assign(next);
        return;
      }
    } catch (cause) {
      flinch(cause instanceof ApiError ? cause.detail : "Something went wrong. Please try again.");
    }
    setBusy(false);
  };

  const googleAvailable = me === null || me.google_enabled;
  const passwordIsNew = view === "signup" || view === "reset";
  const strength = Math.min(password.length / MIN_PASSWORD, 1);

  return (
    <MotionConfig reducedMotion="user">
      <main className="auth" onPointerMove={follow} onPointerLeave={settle}>
        <div className="auth-sky" aria-hidden="true">
          <motion.div className="auth-sky-layer" style={{ x: skyX, y: skyY }}>
            <i className="auth-aurora auth-aurora-a" />
            <i className="auth-aurora auth-aurora-b" />
            <i className="auth-aurora auth-aurora-c" />
            <i className="auth-aurora auth-aurora-d" />
          </motion.div>
          <VoiceRibbon energy={energy} pointer={pointer} />
          <div className="auth-grain" />
        </div>

        <div className="auth-signals" aria-hidden="true">
          <Signals active={showing} />
        </div>

        <AnimatePresence>{!showing && <Opening key="opening" />}</AnimatePresence>

        <motion.header
          className="auth-top"
          initial={{ opacity: 0, y: -10 }}
          animate={showing ? { opacity: 1, y: 0 } : { opacity: 0, y: -10 }}
          transition={{ duration: 0.7, ease: EASE }}
        >
          <Link href="/" className="auth-brand" aria-label="Salix home">
            Salix
          </Link>
          <Link href="/" className="auth-back">
            <span aria-hidden="true">&larr;</span> Home
          </Link>
        </motion.header>

        <motion.div
          ref={card}
          className="auth-card"
          data-leaving={leaving}
          style={{ rotateX, rotateY, transformPerspective: 1100 }}
          initial={{ opacity: 0, scale: 0.3, y: 30 }}
          animate={
            finished
              ? { opacity: 0, scale: 0.9, y: -16, transition: { duration: 0.42, ease: EASE, delay: 0.08 } }
              : showing
                ? { opacity: 1, scale: 1, y: 0 }
                : { opacity: 0, scale: 0.3, y: 30 }
          }
          transition={POP}
        >
          <svg className="auth-card-edge" aria-hidden="true">
            <rect className="auth-edge-base" width="100%" height="100%" rx="26" />
            <rect className="auth-edge-teal" width="100%" height="100%" rx="26" pathLength={100} />
            <rect className="auth-edge-lime" width="100%" height="100%" rx="26" pathLength={100} />
          </svg>

          <motion.div
            className="auth-perch"
            data-mood={mood}
            initial={{ scale: 0 }}
            animate={showing ? { scale: finished ? 1.2 : 1 } : { scale: 0 }}
            transition={{ type: "spring", stiffness: 340, damping: 15, delay: showing && !finished ? 0.16 : 0 }}
          >
            <Leaf mood={mood} beat={beat} />
          </motion.div>

          <motion.div className="auth-card-body" variants={stagger} initial="hidden" animate={showing ? "shown" : "hidden"}>
            {mode !== "reset" && (
              <motion.nav variants={rise} className="auth-tabs" data-mode={mode} aria-label="Log in or sign up">
                <span className="auth-tabs-pill" aria-hidden="true" />
                <Link href={hrefFor("login")} aria-current={mode === "login" ? "page" : undefined} onClick={switchTo("login")}>
                  Log in
                </Link>
                <Link href={hrefFor("signup")} aria-current={mode === "signup" ? "page" : undefined} onClick={switchTo("signup")}>
                  Sign up
                </Link>
              </motion.nav>
            )}

            <motion.div variants={rise} className="auth-heading">
              <AnimatePresence mode="wait" initial={false}>
                <Heading key={view} text={TITLES[view]} />
              </AnimatePresence>
            </motion.div>

            <AnimatePresence initial={false}>
              {error && !problem && (
                <motion.div
                  key="error"
                  className="auth-error-wrap"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.35, ease: EASE }}
                >
                  <div role="alert" className="auth-error">
                    {ERRORS[error] ?? ERRORS.failed}
                  </div>
                </motion.div>
              )}
              {problem && (
                <motion.div
                  key={problem.attempt}
                  className="auth-error-wrap"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto", x: [0, -7, 7, -4, 4, 0] }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.38, ease: "easeOut" }}
                >
                  <div role="alert" className="auth-error">
                    {problem.text}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {(mode === "login" || mode === "signup") && !forgot && googleAvailable && (
              <motion.div variants={rise}>
                <a
                  className="auth-google"
                  data-leaving={leaving}
                  href={`/api/auth/google/start?next=${encodeURIComponent(next)}`}
                  onClick={() => {
                    setLeaving(true);
                    rememberWelcome();
                  }}
                >
                  {leaving ? <span className="auth-spinner" aria-hidden="true" /> : <GoogleMark />}
                  <span>{leaving ? "Opening Google…" : "Continue with Google"}</span>
                </a>
                <div className="auth-or">or</div>
              </motion.div>
            )}

            {view === "reset" && !resetToken ? (
              <motion.p variants={rise} className="auth-note">
                This page needs the link from your email. <Link href="/login">Back to log in</Link>
              </motion.p>
            ) : view === "forgot" && me !== null && !me.mail_enabled ? (
              <motion.div className="auth-note" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                This server cannot send email, so it cannot send a reset link. If this is a Google address, continue with Google instead.
              </motion.div>
            ) : mailed ? (
              <motion.div className="auth-sent" role="status" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={POP}>
                If there is an account for <strong>{email}</strong>, a link is on its way.
              </motion.div>
            ) : (
              <motion.form variants={rise} className="auth-form" onSubmit={submit} onKeyDown={hear} noValidate>
                <AnimatePresence initial={false}>
                  {view === "signup" && (
                    <motion.div
                      key="name"
                      className="auth-field-wrap"
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.36, ease: EASE }}
                    >
                      <div className="auth-field">
                        <input id="auth-name" name="name" autoComplete="name" required placeholder=" " value={name} onChange={(e) => setName(e.target.value)} />
                        <label htmlFor="auth-name">Your name</label>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {view !== "reset" && (
                  <div className="auth-field">
                    <input id="auth-email" name="email" type="email" autoComplete="email" inputMode="email" required placeholder=" " value={email} onChange={(e) => setEmail(e.target.value)} />
                    <label htmlFor="auth-email">Work email</label>
                  </div>
                )}

                {view !== "forgot" && (
                  <div className="auth-field">
                    <input
                      id="auth-password"
                      name="password"
                      placeholder=" "
                      aria-describedby={passwordIsNew ? "auth-password-hint" : undefined}
                      type={showPassword ? "text" : "password"}
                      autoComplete={passwordIsNew ? "new-password" : "current-password"}
                      required
                      maxLength={128}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      onFocus={() => setInPassword(true)}
                      onBlur={() => setInPassword(false)}
                    />
                    <label htmlFor="auth-password">Password</label>
                    <button
                      type="button"
                      className="auth-reveal"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      aria-pressed={showPassword}
                      onClick={() => setShowPassword((shown) => !shown)}
                    >
                      <Eye open={showPassword} />
                    </button>
                    {passwordIsNew && (
                      <span className="auth-meter" data-enough={strength === 1}>
                        <i style={{ transform: `scaleX(${strength})` }} />
                        <span id="auth-password-hint" className="sr-only">
                          At least {MIN_PASSWORD} characters
                        </span>
                      </span>
                    )}
                  </div>
                )}

                <motion.button type="submit" className="auth-submit" disabled={busy} whileTap={{ scale: 0.97 }}>
                  {busy && !finished && <span className="auth-spinner" aria-hidden="true" />}
                  {finished && <IconCheck size={16} />}
                  <span>{SUBMIT[view]}</span>
                </motion.button>

                {view === "login" && (
                  <button type="button" className="auth-text-button auth-forgot" onClick={() => showForgot(true)}>
                    Forgot password?
                  </button>
                )}
              </motion.form>
            )}

            {view === "forgot" && (
              <motion.button type="button" className="auth-text-button auth-back-to-login" onClick={() => showForgot(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                &larr; Back to log in
              </motion.button>
            )}

            {view === "signup" && (
              <div className="auth-invited">
                <InfoTip text="Invited by a colleague?" align="center">
                  Use the address they invited, then confirm it from your inbox.
                </InfoTip>
              </div>
            )}
          </motion.div>
        </motion.div>
      </main>
    </MotionConfig>
  );
}

export function AuthScreen() {
  return (
    <Suspense fallback={null}>
      <Screen />
    </Suspense>
  );
}
