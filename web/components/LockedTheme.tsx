"use client";

/**
 * Pins a route to one theme regardless of the user's preference.
 *
 * The landing page is art-directed dark: the Helix lighting, the bloom
 * threshold and the atmosphere washes are all composed against black, and
 * rendering them on paper is a different design rather than the same one
 * inverted. The console behind it still honours the preference, because that
 * is a tool somebody looks at all day.
 *
 * The inline script in `layout.tsx` handles the first paint so there is no
 * flash on a cold load. This component covers client-side navigation -- a
 * light-mode user clicking the logo in the sidebar -- and, critically,
 * restores their setting on unmount so visiting the landing page does not
 * silently change what the rest of the app looks like.
 */

import { useEffect } from "react";

export function LockedTheme({ theme = "dark" }: { theme?: "dark" | "light" }) {
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute("data-theme", theme);

    return () => {
      // Restore from localStorage, not from whatever the attribute happened to
      // be at mount. On a cold load of this route the inline script in
      // layout.tsx has *already* forced the attribute to `theme`, so reading
      // it here would capture the lock itself and leave the whole app pinned
      // dark after a light-mode user visited the home page. Storage is the
      // only real record of what they chose.
      let stored: string | null = null;
      try {
        stored = localStorage.getItem("salix-theme");
      } catch {
        /* private mode, blocked storage: fall through to system */
      }
      if (stored === "light" || stored === "dark") {
        root.setAttribute("data-theme", stored);
      } else {
        // No stored choice means "follow the system", which is the absence of
        // the attribute rather than any particular value.
        root.removeAttribute("data-theme");
      }
    };
  }, [theme]);

  return null;
}
