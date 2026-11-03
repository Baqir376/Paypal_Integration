import type { Metadata, Viewport } from "next";
import {
  Instrument_Serif,
  Noto_Nastaliq_Urdu,
  Noto_Naskh_Arabic,
} from "next/font/google";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { Atmosphere } from "@/components/Atmosphere";
import { Chrome } from "@/components/system/Chrome";
import { FieldMount } from "@/components/three/FieldMount";

import "./globals.css";
// After the design system, deliberately. The set pieces share class names
// with it (`panel` in particular), and a CSS @import always lands *before*
// the rules that follow it -- so imported first, every collision was
// silently resolved against them.
import "./effects.css";
// The art direction, last. Where it collides with either of the above it wins,
// which is the whole reason it is a separate file rather than more rules in
// globals.css: the precedence is stated by the import order instead of being
// fought out with selector weight.
import "./system.css";
import "./payments.css";
import "./studio.css";

/* An editorial serif for display type. In a category where every product
   ships a geometric sans, this is the fastest signal that a person made
   decisions here. */
const instrumentSerif = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-instrument-serif",
  display: "swap",
});

/* Urdu needs two faces, not one.

   Naskh is horizontal, compact, and sits inside a normal line box, so it is
   what the interface falls back to for labels, tags and table cells — the
   places where a line height is fixed by a neighbouring English string.

   Nastaliq is the face Urdu is actually read in: calligraphic, descending
   steeply from right to left. It is beautiful and it is tall, so it is applied
   only where the line height is ours to set — a transcript line, a Dojo turn,
   a quoted passage. Using it everywhere would clip descenders against every
   fixed-height control in the product. */
const notoNaskh = Noto_Naskh_Arabic({
  subsets: ["arabic"],
  weight: ["400", "500"],
  variable: "--font-urdu-ui",
  display: "swap",
});

const notoNastaliq = Noto_Nastaliq_Urdu({
  subsets: ["arabic"],
  weight: "400",
  variable: "--font-urdu",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Salix",
    template: "%s · Salix",
  },
  description:
    "Salix listens to every sales call, measures what actually happened, and turns the moves that win into coaching for the reps who need them.",
  keywords: [
    "sales conversation intelligence",
    "call analysis",
    "sales coaching",
    "revenue operations",
  ],
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f6f3" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0b0c" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable} ${instrumentSerif.variable} ${notoNaskh.variable} ${notoNastaliq.variable}`}
    >
      <head>
        {/* Applied before first paint so a chosen theme never flashes the
            other one. Kept tiny and inline for that reason.

            The editorial routes -- the index and the archive -- are
            art-directed dark and ignore the preference entirely. Their heroes,
            the Helix lighting and the atmosphere washes are composed against
            black, and rendering them on paper is a different design rather
            than the same one inverted. The console behind them honours the
            user's choice, because that is a tool somebody looks at all day. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                var p = location.pathname;
                if (p === '/' || p === '/archive') {
                  document.documentElement.setAttribute('data-theme', 'dark');
                } else {
                  var t = localStorage.getItem('salix-theme');
                  if (t === 'light' || t === 'dark') {
                    document.documentElement.setAttribute('data-theme', t);
                  }
                }
              } catch (e) {}
            `,
          }}
        />
      </head>
      <body>
        {/* Order is the stack. The 3D field is the deepest layer; the CSS
            atmosphere -- washes, blueprint grid, film grain -- paints over it
            as a veil, which is what stops the WebGL reading as a separate
            window cut into the page. Both sit below the content. */}
        <FieldMount />
        <Atmosphere />
        {children}
        {/* Last in the body and never unmounted. The rail, the pill, the
            cursor and the grain persist across every route, so moving between
            the landing page and the console is a change of content inside one
            instrument rather than a page load. */}
        <Chrome />
      </body>
    </html>
  );
}
