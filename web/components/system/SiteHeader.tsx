"use client";

/**
 * The public site's header.
 *
 * What it offers depends on who is looking. A stranger is asked to log in or get
 * started, somebody already signed in goes straight to their dashboard, and a
 * deployment with no accounts just opens the demo.
 */

import { LayoutGroup, motion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Mark } from "@/components/Mark";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

const SECTIONS = [
  { id: "method", label: "Why Salix" },
  { id: "pipeline", label: "How it works" },
  { id: "evidence", label: "See a call" },
  { id: "entry", label: "Product" },
];

function goTo(id: string, onHome: boolean) {
  if (!onHome) {
    window.location.assign(`/#${id}`);
    return;
  }
  const target = document.getElementById(id);
  if (!target) return;
  const lenis = (window as unknown as {
    __lenis?: { scrollTo: (el: HTMLElement, options: { offset: number }) => void };
  }).__lenis;
  if (lenis) lenis.scrollTo(target, { offset: -84 });
  else target.scrollIntoView({ behavior: "smooth" });
}

export function SiteHeader() {
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const signedIn = !!me?.user;
  const noAccounts = me !== null && !me.auth_required;

  return (
    <motion.header
      className="site-header no-print"
      data-scrolled={scrolled}
      initial={{ y: -18, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
    >
      <div className="site-header-inner">
        <Link href="/" className="site-brand" aria-label="Salix home">
          <Mark size={22} />
          <span>Salix</span>
        </Link>

        <nav className="site-links" aria-label="On this page" onMouseLeave={() => setHovered(null)}>
          <LayoutGroup id="site-links">
            {SECTIONS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                className="site-link"
                onMouseEnter={() => setHovered(id)}
                onFocus={() => setHovered(id)}
                onClick={() => goTo(id, pathname === "/")}
              >
                {hovered === id && (
                  <motion.span
                    layoutId="site-link-hover"
                    className="site-link-hover"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span style={{ position: "relative" }}>{label}</span>
              </button>
            ))}
          </LayoutGroup>
        </nav>

        <div className="site-actions">
          {signedIn || noAccounts ? (
            <Link href="/console" className="site-cta">
              {signedIn ? "Open dashboard" : "Open the demo"}
              <span className="site-cta-arrow" aria-hidden="true">
                &rarr;
              </span>
            </Link>
          ) : (
            <>
              <Link href="/login" className="site-login">
                Log in
              </Link>
              <Link href="/signup" className="site-cta">
                Get started
                <span className="site-cta-arrow" aria-hidden="true">
                  &rarr;
                </span>
              </Link>
            </>
          )}
        </div>
      </div>
    </motion.header>
  );
}
