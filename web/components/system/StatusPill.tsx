"use client";

/**
 * The floating status pill.
 *
 * Persistent across every route, so the app reads as one piece of software
 * rather than as a marketing site with a dashboard bolted to it. Two halves:
 *
 *   left   a live readout of the section the reader is currently inside,
 *          rolling over rather than swapping, plus the provider state polled
 *          from the API so it is never a decorative dot;
 *   right  the navigation, each label a dual-layer rolling hover.
 *
 * Sections announce themselves with `data-status="LABEL"`. Nothing is
 * registered from here, so adding a section anywhere in the app puts it in
 * the readout without touching this file.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { Health } from "@/lib/types";

const NAV = [
  { href: "/console", label: "Console" },
  { href: "/calls", label: "Calls" },
  { href: "/playbook", label: "Playbook" },
  { href: "/dojo", label: "Dojo" },
  { href: "/archive", label: "Archive" },
];

export function StatusPill() {
  const pathname = usePathname();
  const [section, setSection] = useState("INDEX");
  const [previous, setPrevious] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);

  /* --- The provider badge -------------------------------------------- */

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

  /* --- The section readout -------------------------------------------- */

  useEffect(() => {
    // The route changed, so whatever section was showing belongs to a page
    // that is gone. Reset before the observer has anything to say.
    setSection(pathname === "/" ? "INDEX" : pathname.slice(1).split("/")[0].toUpperCase());

    const nodes = Array.from(
      document.querySelectorAll<HTMLElement>("[data-status]"),
    );
    if (nodes.length === 0) return;

    // Sorted by document order once, so "the topmost visible section" is a
    // lookup rather than a comparison of bounding rects on every frame.
    const order = new Map(nodes.map((node, index) => [node, index]));
    const visible = new Set<HTMLElement>();

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const node = entry.target as HTMLElement;
          if (entry.isIntersecting) visible.add(node);
          else visible.delete(node);
        }

        let best: HTMLElement | null = null;
        for (const node of visible) {
          if (!best || (order.get(node) ?? 0) > (order.get(best) ?? 0)) best = node;
        }

        const label = best?.dataset.status;
        if (label) {
          setSection((current) => {
            if (current === label) return current;
            setPrevious(current);
            return label;
          });
        }
      },
      // A band across the upper-middle of the viewport: a section counts as
      // "the one you are in" when its top has passed the pill and its bottom
      // has not yet left, which is where a reader's attention actually is.
      { rootMargin: "-18% 0px -62% 0px", threshold: 0 },
    );

    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [pathname]);

  /* --- Retreat on the way down ---------------------------------------- */

  const lastY = useRef(0);
  useEffect(() => {
    lastY.current = window.scrollY;
    let frame = 0;

    const update = () => {
      frame = 0;
      const y = window.scrollY;
      const delta = y - lastY.current;
      // A dead band, so a trackpad's jitter around a resting point does not
      // flicker the pill in and out.
      if (Math.abs(delta) > 6) {
        setHidden(delta > 0 && y > 220);
        lastY.current = y;
      }
    };

    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(update);
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(frame);
    };
  }, []);

  const live = health?.provider_mode === "live";

  return (
    <nav
      className={`sx-pill no-print${hidden ? " is-hidden" : ""}`}
      aria-label="Primary"
    >
      <div className="sx-pill-status">
        <span
          className="sx-pill-dot"
          style={{
            background: health
              ? live
                ? "var(--accent-signal)"
                : "var(--accent-gold)"
              : "var(--text-quaternary)",
            animation: health ? undefined : "none",
          }}
        />
        <div className="sx-pill-readout sx-tag" aria-live="polite">
          {previous && (
            <span
              key={`out-${previous}-${section}`}
              className="is-out"
              aria-hidden="true"
              onAnimationEnd={() => setPrevious(null)}
            >
              [ {previous} ]
            </span>
          )}
          <span key={section} className={previous ? "is-in" : undefined}>
            [ {section} ]
          </span>
        </div>
      </div>

      <div className="sx-pill-nav">
        <Link href="/" className="sx-pill-link roll-host" data-active={pathname === "/"}>
          <span className="roll">
            <span>Index</span>
            <span>Index</span>
          </span>
        </Link>

        {NAV.map(({ href, label }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              className="sx-pill-link roll-host"
              data-active={active}
              aria-current={active ? "page" : undefined}
            >
              <span className="roll">
                <span>{label}</span>
                <span>{label}</span>
              </span>
            </Link>
          );
        })}
      </div>

      <Link href="/upload" className="sx-pill-cta roll-host">
        <span className="roll">
          <span>Analyse</span>
          <span>Analyse</span>
        </span>
      </Link>
    </nav>
  );
}
