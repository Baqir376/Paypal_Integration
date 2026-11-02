"use client";

/**
 * Things that pop up: a note kept out of the way until it is asked for, a toast, a
 * burst of celebration, and the quick actions button.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { IconCheck, IconCoin, IconDojo, IconTeam, IconUpload, IconWarning } from "@/components/icons";

const SPRING = { type: "spring", stiffness: 420, damping: 26, mass: 0.7 } as const;

/** Closes on Escape or a click elsewhere, which every pop-up here wants. */
function useDismiss(open: boolean, close: () => void) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && close();
    const onPress = (event: PointerEvent) => {
      if (!box.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPress);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPress);
    };
  }, [open, close]);
  return box;
}

/** A small button, and the longer explanation it keeps out of the way until it is asked for. */
export function InfoTip({
  children,
  label = "More about this",
  text,
  align = "start",
}: {
  children: React.ReactNode;
  label?: string;
  /** Words on the button. Without them it is just the "i". */
  text?: string;
  align?: "start" | "center" | "end";
}) {
  const [open, setOpen] = useState(false);
  const box = useDismiss(open, () => setOpen(false));
  const id = useId();

  return (
    <div className="info" ref={box}>
      <button
        type="button"
        className="info-button"
        aria-label={text ? undefined : label}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((was) => !was)}
      >
        <span className="info-dot" aria-hidden="true">
          i
        </span>
        {text}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            id={id}
            role="note"
            className="info-pop"
            data-align={align}
            initial={{ opacity: 0, scale: 0.86, y: -6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: -4, transition: { duration: 0.12 } }}
            transition={SPRING}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** What used to be a paragraph under a page's title. */
export function PageNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="page-note">
      <InfoTip text="How this works">{children}</InfoTip>
    </div>
  );
}

/* ---------------------------------------------------------------------- */

type Toast = { id: number; text: string; tone: "good" | "bad" };

let listener: ((toast: Toast) => void) | null = null;
let counter = 0;

/** From anywhere. Silently does nothing on a page without a Toaster. */
export function popToast(text: string, tone: Toast["tone"] = "good") {
  listener?.({ id: ++counter, text, tone });
}

export function Toaster() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    listener = (toast) => {
      setToasts((all) => [...all.slice(-2), toast]);
      setTimeout(() => setToasts((all) => all.filter((t) => t.id !== toast.id)), 4200);
    };
    return () => {
      listener = null;
    };
  }, []);

  return (
    <div className="toasts" role="status" aria-live="polite">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            layout
            className="toast"
            data-tone={toast.tone}
            initial={{ opacity: 0, y: 26, scale: 0.8 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.16 } }}
            transition={SPRING}
          >
            <span className="toast-icon" aria-hidden="true">
              {toast.tone === "good" ? <IconCheck size={13} /> : <IconWarning size={13} />}
            </span>
            {toast.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

/* ---------------------------------------------------------------------- */

const COLOURS = ["#d4f55a", "#7ddcd2", "#ffc439", "#b98ee0", "#7d9410"];
const PIECES = Array.from({ length: 30 }, (_, i) => {
  const angle = (i / 30) * Math.PI * 2 + (i % 3) * 0.13;
  const reach = 90 + ((i * 37) % 130);
  return {
    x: Math.round(Math.cos(angle) * reach),
    y: Math.round(Math.sin(angle) * reach),
    spin: (i * 67) % 360,
    size: 5 + (i % 4) * 2,
    colour: COLOURS[i % COLOURS.length],
    round: i % 2 === 0,
  };
});

/** A burst from the middle of whatever holds it. Decoration, so it is skipped for stillness. */
export function Burst() {
  const reduced = useReducedMotion();
  if (reduced) return null;
  return (
    <div className="burst" aria-hidden="true">
      {PIECES.map((piece, i) => (
        <motion.i
          key={i}
          style={{ width: piece.size, height: piece.size, background: piece.colour, borderRadius: piece.round ? 99 : 2 }}
          initial={{ x: 0, y: 0, opacity: 1, scale: 0.4, rotate: 0 }}
          animate={{ x: piece.x, y: piece.y + 34, opacity: 0, scale: 1, rotate: piece.spin }}
          transition={{ duration: 1.25, ease: [0.12, 0.8, 0.3, 1], delay: 0.05 }}
        />
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------------- */

const ACTIONS = [
  { href: "/upload", label: "Analyse a call", icon: IconUpload },
  { href: "/dojo", label: "Practise", icon: IconDojo },
  { href: "/team", label: "Add a teammate", icon: IconTeam },
  { href: "/billing", label: "Buy credits", icon: IconCoin },
];

/** Pages where the bottom corner is already in use, or where this would be a distraction. */
const HIDDEN_ON = ["/upload", "/dojo", "/roleplay", "/billing/return"];

export function QuickActions() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const box = useDismiss(open, () => setOpen(false));

  useEffect(() => setOpen(false), [pathname]);

  if (HIDDEN_ON.some((path) => pathname.startsWith(path))) return null;

  return (
    <div className="quick" ref={box}>
      <AnimatePresence>
        {open && (
          <motion.nav className="quick-list" aria-label="Quick actions" initial="closed" animate="open" exit="closed"
            variants={{ open: { transition: { staggerChildren: 0.045, staggerDirection: -1 } }, closed: { transition: { staggerChildren: 0.02 } } }}
          >
            {ACTIONS.map(({ href, label, icon: Icon }) => (
              <motion.div
                key={href}
                variants={{ open: { opacity: 1, y: 0, scale: 1 }, closed: { opacity: 0, y: 14, scale: 0.8 } }}
                transition={SPRING}
              >
                <Link href={href} className="quick-item">
                  <Icon size={15} />
                  {label}
                </Link>
              </motion.div>
            ))}
          </motion.nav>
        )}
      </AnimatePresence>
      <motion.button
        type="button"
        className="quick-button"
        aria-label={open ? "Close quick actions" : "Quick actions"}
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
        initial={{ scale: 0 }}
        animate={{ scale: 1, rotate: open ? 45 : 0 }}
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.92 }}
        transition={{ type: "spring", stiffness: 380, damping: 18, delay: 0 }}
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M10 3.5v13M3.5 10h13" />
        </svg>
      </motion.button>
    </div>
  );
}
