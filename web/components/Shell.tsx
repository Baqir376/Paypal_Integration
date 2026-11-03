"use client";

import { LayoutGroup, MotionConfig, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { cx } from "@/lib/format";
import type { BillingState, Health, Me } from "@/lib/types";

import { PageTransition } from "./Motion";
import { QuickActions, Toaster, popToast } from "./Pop";
import { StudioBackdrop } from "./Studio";

import { CommandPalette } from "./CommandPalette";
import { Mark } from "./Mark";
import {
  IconBook,
  IconCoin,
  IconDeal,
  IconDojo,
  IconGauge,
  IconReport,
  IconTeam,
  IconUpload,
  IconWave,
} from "./icons";

const NAV = [
  { href: "/console", label: "Command centre", icon: IconGauge },
  { href: "/calls", label: "Calls", icon: IconWave },
  { href: "/team", label: "Team", icon: IconTeam },
  { href: "/playbook", label: "Playbook", icon: IconBook },
  { href: "/deals", label: "Deals at risk", icon: IconDeal },
  { href: "/dojo", label: "The Dojo", icon: IconDojo },
  { href: "/report", label: "Cycle report", icon: IconReport },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  /** Undefined until the API has answered; null if it could not. */
  const [me, setMe] = useState<Me | null | undefined>(undefined);

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  // Set on the way out of the sign-in screen, so this happens once and only then.
  useEffect(() => {
    if (!me?.user) return;
    try {
      if (sessionStorage.getItem("salix-welcome")) {
        sessionStorage.removeItem("salix-welcome");
        popToast(`You're in, ${me.user.name.split(" ")[0]}`);
      }
    } catch {
      /* only costs a greeting */
    }
  }, [me]);

  const mustSignIn = !!me?.auth_required && !me.user;
  useEffect(() => {
    if (mustSignIn) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [mustSignIn, pathname, router]);
  const [health, setHealth] = useState<Health | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [billing, setBilling] = useState<BillingState | null>(null);

  // On every navigation, because the balance changes elsewhere: spent on the
  // upload page, bought on the return page.
  useEffect(() => {
    if (mustSignIn || me === undefined) return;
    const refresh = () => api.billing().then(setBilling).catch(() => setBilling(null));
    refresh();
    window.addEventListener("salix:credits", refresh);
    return () => window.removeEventListener("salix:credits", refresh);
  }, [pathname, mustSignIn, me]);

  // Worth interrupting for: anything done while offline is about to fail.
  useEffect(() => {
    const offline = () => popToast("You are offline. Nothing will save until you reconnect.", "bad");
    const online = () => popToast("You are back online");
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
    };
  }, []);

  // Said once a session, and not on the pages where buying is already on screen.
  useEffect(() => {
    if (!billing?.enforced || !billing.can_purchase || pathname.startsWith("/billing")) return;
    if (billing.balance > 2 * billing.call_cost) return;
    try {
      if (sessionStorage.getItem("salix-credits-warned")) return;
      sessionStorage.setItem("salix-credits-warned", "1");
    } catch {
      return;
    }
    const buy = { href: "/billing", label: "Buy credits" };
    if (billing.balance < billing.call_cost) popToast("You are out of credits", "bad", buy);
    else popToast(`Only ${billing.balance} ${billing.balance === 1 ? "credit" : "credits"} left`, "good", buy);
  }, [billing, pathname]);

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

  // Only once it is known to be closed. Waiting for the answer as well would blank
  // the page whenever the API is slow or down, when the page's own loading and error
  // states are what somebody needs. Nothing leaks meanwhile: the API refuses a
  // signed-out request whatever is on screen.
  if (mustSignIn) {
    return <div className="shell-waiting" aria-busy="true" />;
  }

  return (
    <div className="shell" data-tab={pathname.split("/")[1] || "console"}>
      <StudioBackdrop />
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

        <MotionConfig reducedMotion="user">
        <LayoutGroup id="rail">
        <nav className="app-rail-nav">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                className="rail-link"
                data-active={active}
                aria-current={active ? "page" : undefined}
              >
                {active && <RailMarker />}
                <Icon size={15} className="rail-link-icon" />
                <span className="rail-link-label">{label}</span>
              </Link>
            );
          })}

          <div className="app-rail-divider" />

          <Link
            href="/upload"
            className="rail-link"
            data-active={pathname === "/upload"}
            aria-current={pathname === "/upload" ? "page" : undefined}
          >
            {pathname === "/upload" && <RailMarker />}
            <IconUpload size={15} className="rail-link-icon" />
            <span className="rail-link-label">Analyse a call</span>
          </Link>

          {billing && (billing.enforced || billing.can_purchase) && (
            <Link
              href="/billing"
              className="rail-link"
              data-active={pathname.startsWith("/billing")}
              aria-current={pathname.startsWith("/billing") ? "page" : undefined}
            >
              {pathname.startsWith("/billing") && <RailMarker />}
              <IconCoin size={15} className="rail-link-icon" />
              <span className="rail-link-label">Credits</span>
              <span
                key={billing.balance}
                className="num rail-credits"
                style={{
                  position: "relative",
                  marginLeft: "auto",
                  fontSize: 12,
                  color: billing.balance > 0 ? "var(--ink-3)" : "var(--rose)",
                }}
              >
                {billing.balance}
              </span>
            </Link>
          )}
        </nav>
        </LayoutGroup>
        </MotionConfig>

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

          {me?.user && <Account me={me} />}
          <ModeBadge health={health} />
          <ThemeToggle />
        </div>
      </aside>

      <main
        style={{ minWidth: 0 }}
        className="app-main"
        onPointerMove={(event) => {
          event.currentTarget.style.setProperty("--mx", `${event.clientX}px`);
          event.currentTarget.style.setProperty("--my", `${event.clientY}px`);
          // A soft light under the pointer, on whichever card it is over.
          const card = (event.target as Element).closest<HTMLElement>(".panel, .panel-flush");
          if (!card) return;
          const box = card.getBoundingClientRect();
          card.style.setProperty("--spot-x", `${event.clientX - box.left}px`);
          card.style.setProperty("--spot-y", `${event.clientY - box.top}px`);
        }}
      >
        {me?.user && me.mail_enabled && !me.user.email_verified && <ConfirmEmail email={me.user.email} />}
        <PageTransition>{children}</PageTransition>
      </main>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <QuickActions />
      <Toaster />
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

function RailMarker() {
  return (
    <motion.span
      layoutId="rail-marker"
      className="rail-marker"
      transition={{ type: "spring", stiffness: 480, damping: 38 }}
    />
  );
}

function ConfirmEmail({ email }: { email: string }) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "failed">("idle");

  async function resend() {
    setState("sending");
    try {
      await api.resendVerification();
      setState("sent");
    } catch {
      setState("failed");
    }
  }

  return (
    <div className="confirm-email" role="status">
      <span>
        Confirm <strong>{email}</strong> from your inbox to invite teammates.
      </span>
      {state === "sent" ? (
        <span>Sent. Check your inbox.</span>
      ) : (
        <button className="btn btn-ghost btn-sm" onClick={resend} disabled={state === "sending"}>
          {state === "failed" ? "Could not send. Try again" : "Send it again"}
        </button>
      )}
    </div>
  );
}

function Account({ me }: { me: Me }) {
  const user = me.user!;
  const [leaving, setLeaving] = useState(false);

  async function signOut() {
    setLeaving(true);
    try {
      await api.logout();
      // A full navigation, so nothing of this person's stays in memory.
      window.location.assign("/login");
    } catch {
      // Still signed in. Going to the login page would only bounce them straight back.
      setLeaving(false);
      popToast("You are still signed in. Check your connection and try again.", "bad");
    }
  }

  return (
    <div className="app-rail-account">
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          title={user.email}
          style={{ fontSize: 12.5, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {user.name}
        </div>
        <div
          style={{ fontSize: 11, color: "var(--ink-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {user.org_name}
        </div>
      </div>
      <button className="btn btn-ghost btn-sm" onClick={signOut} disabled={leaving}>
        Sign out
      </button>
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
