"use client";

/**
 * The site footer.
 *
 * Lives here rather than beside the index because a Next.js route file may
 * only export `default` and a handful of reserved names -- exporting a
 * component from `page.tsx` and importing it elsewhere fails the build.
 *
 * Shared by every art-directed route, which is the point: the giant outlined
 * wordmark and the engine colophon are the last thing on the index and the
 * last thing on the archive, so the two read as one document.
 */

import Link from "next/link";

import { FooterWord } from "./FooterWord";

export function SiteFooter() {
  return (
    <footer className="sx-foot" data-status="COLOPHON">
      <FooterWord />

      <div className="sx-foot-grid">
        <div>
          <div className="sx-tag sx-tag-gold" style={{ marginBottom: 14 }}>
            [ PRODUCT ]
          </div>
          <Link className="sx-foot-link" href="/console">
            Command centre
          </Link>
          <Link className="sx-foot-link" href="/calls">
            Every call
          </Link>
          <Link className="sx-foot-link" href="/playbook">
            The playbook
          </Link>
          <Link className="sx-foot-link" href="/deals">
            Deals at risk
          </Link>
        </div>

        <div>
          <div className="sx-tag sx-tag-gold" style={{ marginBottom: 14 }}>
            [ PRACTICE ]
          </div>
          <Link className="sx-foot-link" href="/dojo">
            The Dojo
          </Link>
          <Link className="sx-foot-link" href="/upload">
            Analyse a recording
          </Link>
          <Link className="sx-foot-link" href="/report">
            Cycle report
          </Link>
          <Link className="sx-foot-link" href="/archive">
            Provenance
          </Link>
        </div>

        <div>
          <div className="sx-tag sx-tag-gold" style={{ marginBottom: 14 }}>
            [ ENGINE ]
          </div>
          {/* The capabilities, not four Qwen model names. The reasoning and
              embedding layers speak the OpenAI protocol and can point at
              Gemini, Groq or Cerebras, so naming Qwen here was accurate only
              for the deployment it was written on. What is actually answering
              is on the index page, read from /api/health at runtime. */}
          <p className="sx-tag" style={{ whiteSpace: "normal", lineHeight: 2.1 }}>
            REASONING · OPENAI-COMPATIBLE
            <br />
            ASR · DIARIZED FILE TRANSCRIPTION
            <br />
            INDEX · DENSE VECTOR · COSINE
            <br />
            SPEECH · NEURAL, PER LANGUAGE
          </p>
        </div>

        <div>
          <div className="sx-tag sx-tag-gold" style={{ marginBottom: 14 }}>
            [ COLOPHON ]
          </div>
          <p
            style={{
              fontSize: 12.5,
              lineHeight: 1.75,
              color: "var(--text-tertiary)",
              margin: 0,
              maxWidth: "30ch",
            }}
          >
            <em>Salix</em> is the Latin genus of the willow — the bark that gave
            medicine its first lesson in treating the cause rather than the
            complaint.
          </p>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 20,
          flexWrap: "wrap",
          marginTop: 40,
          paddingTop: 20,
          borderTop: "1px solid var(--line)",
        }}
      >
        <span className="sx-tag">[ PAYMENTS BY PAYPAL · SDK BY APIMATIC ]</span>
        <span className="sx-tag">[ MIT LICENSE ]</span>
      </div>
    </footer>
  );
}
