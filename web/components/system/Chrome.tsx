"use client";

/**
 * The persistent chrome.
 *
 * Mounted once in the root layout and never unmounted, which is the point:
 * the telemetry rail, the status pill, the cursor and the grain survive every
 * route change, so navigating between the landing page and the console is a
 * change of content inside one instrument rather than a page load.
 *
 * The scroll engine is booted here too, for the same reason — recreating
 * Lenis per route is what produces the half second of native scrolling
 * immediately after a navigation.
 */

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { getEngine } from "@/lib/motion";

import { Cursor } from "./Cursor";
import { SiteHeader } from "./SiteHeader";
import { TelemetryRail } from "./TelemetryRail";

/**
 * Which kind of page this is.
 *
 * The rail, the custom cursor and the drifting field set the mood on the public site.
 * In the app they are noise around numbers somebody is trying to read, and the app has
 * its own navigation. The sign-in pages are a page of their own.
 */
function surfaceOf(pathname: string): "site" | "auth" | "app" {
  if (pathname === "/" || pathname.startsWith("/archive")) return "site";
  if (pathname.startsWith("/login") || pathname.startsWith("/signup") || pathname.startsWith("/reset-password")) return "auth";
  return "app";
}

export function Chrome() {
  const pathname = usePathname();
  const surface = surfaceOf(pathname);

  useEffect(() => {
    getEngine();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.surface = surface;
  }, [surface]);

  // A route change replaces the document's entire measurable geometry, so
  // every pin and every scrub has to be re-measured. Two frames: one for the
  // new tree to commit, one for layout to settle under it.
  useEffect(() => {
    let frame = 0;
    getEngine().then(({ ScrollTrigger, lenis }) => {
      lenis?.scrollTo(0, { immediate: true });
      frame = requestAnimationFrame(() =>
        requestAnimationFrame(() => ScrollTrigger.refresh()),
      );
    });
    return () => cancelAnimationFrame(frame);
  }, [pathname]);

  return (
    <>
      {surface === "site" && (
        <>
          <TelemetryRail />
          <SiteHeader />
          <Cursor />
          <div className="sx-vignette no-print" aria-hidden="true" />
          <div className="sx-grain no-print" aria-hidden="true" />
        </>
      )}
    </>
  );
}
