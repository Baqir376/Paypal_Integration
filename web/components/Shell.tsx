"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { cx } from "@/lib/format";
import type { Health } from "@/lib/types";

import { PageTransition } from "./Motion";

import { CommandPalette } from "./CommandPalette";
import { Mark } from "./Mark";
import {
  IconBook,
  IconDeal,
  IconDojo,
  IconGauge,
  IconReport,
  IconUpload,
  IconWave,
} from "./icons";

const NAV = [
  { href: "/console", label: "Command centre", icon: IconGauge },
  { href: "/calls", label: "Calls", icon: IconWave },
  { href: "/playbook", label: "Playbook", icon: IconBook },
  { href: "/deals", label: "Deals at risk", icon: IconDeal },
  { href: "/dojo", label: "The Dojo", icon: IconDojo },
  { href: "/report", label: "Cycle report", icon: IconReport },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      api
        .health()
        .then((h) => alive && setHealth(h))
        .catch(() => alive && setHealth(null));
    poll();
    // Slow re-poll so the badge recovers on its own if the API restarts
    // mid-session rather than reading "unreachable" until a page reload.
    const timer = setInterval(poll, 20000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="shell">
      {/* Layout lives in globals.css rather than inline, because an inline
          style cannot be overridden by a media query -- and stacked above the
          content on a phone, this rail needs to become a bar. */}
      <aside className="app-rail no-print">
        <div className="app-rail-brand">
          <Link
            href="/"
            style={{ display: "inline-flex", alignItems: "center", gap: 9 }}
          >
            <Mark size={22} />
            <span
              className="display"
              style={{ fontSize: 25, letterSpacing: "-0.02em" }}
            >
              Salix
            </span>
          </Link>
        </div>

        <nav className="app-rail-nav">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "8px 10px",
                  borderRadius: "var(--r)",
                  marginBottom: 1,
                  fontSize: 13.5,
                  fontWeight: active ? 550 : 450,
                  color: active ? "var(--ink)" : "var(--ink-2)",
                  background: active ? "var(--paper-3)" : "transparent",
                  transition: "background 120ms ease, color 120ms ease",
                }}
              >
                <Icon
                  size={15}
                  style={{ color: active ? "var(--willow)" : "var(--ink-3)" }}
                />
                {label}
              </Link>
            );
          })}

          <div className="app-rail-divider" />

          <Link
            href="/upload"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 10px",
              borderRadius: "var(--r)",
              fontSize: 13.5,
              color: pathname === "/upload" ? "var(--ink)" : "var(--ink-2)",
              background: pathname === "/upload" ? "var(--paper-3)" : "transparent",
            }}
          >
            <IconUpload size={15} style={{ color: "var(--ink-3)" }} />
            Analyse a call
          </Link>
        </nav>

        <div className="app-rail-foot">
          <button
            className="btn btn-ghost btn-sm app-rail-search"
            onClick={() => setPaletteOpen(true)}
          >
            <span style={{ color: "var(--ink-3)" }}>Search everything</span>
            <kbd
              className="num"
              style={{
                fontSize: 10,
                color: "var(--ink-4)",
                border: "1px solid var(--rule)",
                borderRadius: 4,
                padding: "1px 4px",
              }}
            >
              ⌘K
            </kbd>
          </button>

          <ModeBadge health={health} />
          <ThemeToggle />
        </div>
      </aside>

      <main style={{ minWidth: 0 }}>
        <PageTransition>{children}</PageTransition>
      </main>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}

/**
 * States plainly whether the analysis on screen came from Qwen or from the
 * offline fallback. A judge should never have to wonder which they are
 * looking at.
 */
function ModeBadge({ health }: { health: Health | null }) {
  if (!health) {
    return (
      <div className="eyebrow app-rail-mode" style={{ color: "var(--rose)" }}>
        API unreachable
      </div>
    );
  }

  const live = health.provider_mode === "live";
  // Whoever is actually answering, not a vendor written down at build time.
  // The reasoning layer speaks the OpenAI protocol and can point at Gemini,
  // Groq or Cerebras, so a hard-coded "Qwen live" was a lie on every
  // deployment that did exactly what the configuration invited.
  const who = health.providers?.reasoning;
  const named = live && who && who !== "offline twin" ? who : null;
  return (
    <div
      title={
        named
          ? `Live inference: ${health.models.reasoning} via ${named}`
          : "Running on deterministic offline providers. Set a model key for live inference."
      }
      className="app-rail-mode"
    >
      <i
        className={live ? "pulse" : undefined}
        style={{
          width: 6,
          height: 6,
          borderRadius: 999,
          background: live ? "var(--willow)" : "var(--ink-4)",
          flexShrink: 0,
        }}
      />
      <span className="eyebrow" style={{ color: live ? "var(--ink-2)" : "var(--ink-3)" }}>
        {named ? `${named} live` : "Offline mode"}
      </span>
    </div>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | "system">("system");

  useEffect(() => {
    const stored = localStorage.getItem("salix-theme");
    if (stored === "light" || stored === "dark") setTheme(stored);
  }, []);

  function apply(next: "light" | "dark" | "system") {
    setTheme(next);
    if (next === "system") {
      localStorage.removeItem("salix-theme");
      document.documentElement.removeAttribute("data-theme");
    } else {
      localStorage.setItem("salix-theme", next);
      document.documentElement.setAttribute("data-theme", next);
    }
  }

  return (
    <div className="app-rail-theme">
      {(["light", "system", "dark"] as const).map((option) => (
        <button
          key={option}
          onClick={() => apply(option)}
          aria-pressed={theme === option}
          title={`${option} theme`}
          className="eyebrow"
          style={{
            flex: 1,
            padding: "3px 0",
            border: "1px solid",
            borderColor: theme === option ? "var(--rule-strong)" : "transparent",
            background: theme === option ? "var(--paper-3)" : "transparent",
            color: theme === option ? "var(--ink-2)" : "var(--ink-4)",
            borderRadius: "var(--r-sm)",
            cursor: "pointer",
          }}
        >
          {option[0].toUpperCase()}
        </button>
      ))}
    </div>
  );
}
