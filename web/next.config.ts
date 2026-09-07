import type { NextConfig } from "next";

/**
 * There are no rewrites, deliberately.
 *
 * Both /api and /audio are Route Handlers instead. A rewrite cannot attach a
 * header, and both need the shared key. Worse, `rewrites()` is evaluated at
 * BUILD time and baked into the routes manifest, so SALIX_API_URL would be
 * frozen at whatever the build machine had -- in a container, nothing.
 */
const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  // Docker only. `standalone` traces the exact node_modules the server needs
  // into .next/standalone, which turns a ~1GB image into ~200MB. It is opt-in
  // because it changes what `next start` expects to find, and a local run
  // should not have to care.
  ...(process.env.SALIX_STANDALONE ? { output: "standalone" as const } : {}),

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // The microphone is the product; everything else is off.
          {
            key: "Permissions-Policy",
            value: "microphone=(self), camera=(), geolocation=(), payment=()",
          },
        ],
      },
    ];
  },
};

export default config;
