"use client";

/**
 * Provenance.
 *
 * Where every number on the rest of the site comes from. This is the page a
 * sceptic is sent to, so it is built to be checked rather than admired: the
 * corpus table is the real corpus fetched from the running API, the service
 * manifest names the exact model identifiers in use, and the timeline is the
 * actual DAG in the order it executes.
 *
 * Composed against black and locked out of the theme toggle, like the index —
 * this is editorial, not a tool somebody has open all day.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { LockedTheme } from "@/components/LockedTheme";
import { Mark } from "@/components/Mark";
import { HorizontalRun } from "@/components/system/HorizontalRun";
import {
  Count,
  FadeWords,
  Parallax,
  RevealWords,
  Seal,
  useProgress,
} from "@/components/system/primitives";
import { SiteFooter } from "@/components/system/SiteFooter";
import { api } from "@/lib/api";
import { duration, percent, shortDate } from "@/lib/format";
import type { CallSummary, Health, RepSnapshot } from "@/lib/types";

/* ==========================================================================
   Content
   ========================================================================== */

/** The DAG, in execution order. Each entry is a real stage in api/salix. */
const STAGES = [
  {
    time: "T+0",
    name: "Transcriptionist",
    detail:
      "The recording goes to a file transcription service, Deepgram Nova-3 or Qwen ASR, and comes back as diarized segments with millisecond boundaries. Which speaker is the salesperson is inferred from the conversation's shape, not from metadata.",
    emits: "Transcript · segments[] · speaker map",
  },
  {
    time: "T+1",
    name: "Prosodist",
    detail:
      "Seven measurements computed in Python from those timestamps. This stage consults no language model, which is why its output is the only thing on the site that carries no citation — there is nothing to cite but arithmetic.",
    emits: "Metrics · 7 axes · 0 model calls",
  },
  {
    time: "T+2",
    name: "Anatomist",
    detail:
      "Stages, objections, MEDDIC coverage and commitments, each citing the segment ids behind it. Citations are hydrated against the transcript; unresolvable ids send the agent back with the list of ids that exist.",
    emits: "Analysis · findings[] · citations[]",
  },
  {
    time: "T+3",
    name: "Playwright",
    detail:
      "Winning calls are mined for reusable narrative moves. Candidates are embedded on structure and matched against the existing library, so a rediscovery becomes an instance rather than a duplicate.",
    emits: "Plays · instances[] · moment index",
  },
  {
    time: "T+4",
    name: "Coach",
    detail:
      "For each axis where a rep trails, the moment index is searched for how a colleague who won handled the same situation, excluding the rep's own passages and diversified with MMR. The plan is written from what comes back.",
    emits: "Coaching plan · cited script",
  },
  {
    time: "T+5",
    name: "Analyst",
    detail:
      "Calls are chained into deal trajectories, risk is named and evidenced, and the cycle report is written explaining where the quarter landed and why.",
    emits: "Trajectories · risks[] · cycle report",
  },
];

/** What each AI service does. Which one is answering right now is read from /api/health. */
const SERVICES = [
  {
    index: "I",
    capability: "File transcription with diarization",
    model: "Deepgram Nova-3 or Qwen ASR",
    note: "Speakers are separated in the transcript itself. The only stage whose failure is fatal, because without a transcript there is nothing to analyse.",
    surface: "File transcription API",
  },
  {
    index: "II",
    capability: "Anatomy, plays, coaching, reporting",
    model: "Gemini Flash-Lite, with automatic failover",
    note: "Every structured output is validated against the Pydantic contract, and a failure is returned to the model with the validator's own complaint rather than silently discarded.",
    surface: "OpenAI-compatible endpoint",
  },
  {
    index: "III",
    capability: "High-volume and low-latency passes",
    model: "Any OpenAI-compatible model",
    note: "Where the work is bulk classification rather than reasoning, the cheaper model does it. Which model produced a given field is recorded, not inferred.",
    surface: "OpenAI-compatible endpoint",
  },
  {
    index: "IV",
    capability: "Semantic retrieval over moments",
    model: "Gemini or Qwen embeddings",
    note: "Dense vectors over conversational moments, searched with cosine similarity and diversified with MMR so a coaching plan is not five phrasings of one sentence.",
    surface: "Vector index · SQLite / Postgres",
  },
  {
    index: "V",
    capability: "The Dojo buyer's voice",
    model: "Neural voices, Edge TTS or Qwen TTS",
    note: "The practice opponent speaks. Where no key is configured the browser's own speech synthesis stands in, and the interface says which is talking.",
    surface: "Streaming synthesis",
  },
  {
    index: "VI",
    capability: "Realtime ASR (optional Dojo path)",
    model: "Browser dictation or Qwen ASR",
    note: "The rep's turn can be routed through a server model rather than the Web Speech API. The browser path is the default because it cannot fail on venue wifi.",
    surface: "Websocket",
  },
];

/* ==========================================================================
   Page
   ========================================================================== */

export default function ArchivePage() {
  const [calls, setCalls] = useState<CallSummary[]>([]);
  const [reps, setReps] = useState<RepSnapshot[]>([]);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    // Outside the app shell, so it asks for itself: with accounts on, the calls
    // and people on this page are only for somebody signed in.
    api
      .me()
      .then((me) => {
        if (me.auth_required && !me.user) window.location.assign("/login?next=/archive");
      })
      .catch(() => {});
    api.calls({ limit: 50 }).then(setCalls).catch(() => {});
    api.reps().then(setReps).catch(() => {});
    api.health().then(setHealth).catch(() => {});
  }, []);

  const timeline = useProgress<HTMLDivElement>();

  return (
    <main className="sx-page sx-dark">
      <LockedTheme theme="dark" />

      {/* ================================================================
          HERO
          ============================================================== */}
      <section
        className="sx-hero"
        style={{ minHeight: "78svh", ["--img-hero" as string]: "var(--img-archive)" }}
        data-status="PROVENANCE"
      >
        <Parallax className="sx-hero-plate" distance={140} />

        <div className="sx-hero-head">
          <div
            style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 26 }}
          >
            <Mark size={22} />
            <span className="sx-tag sx-tag-gold">[ ARCHIVE ]</span>
            <span className="sx-tag">
              [{" "}
              {health?.provider_mode === "live" &&
              health?.providers?.reasoning &&
              health.providers.reasoning !== "offline twin"
                ? `${health.providers.reasoning.toUpperCase()} LIVE`
                : "OFFLINE TWIN"}{" "}
              ]
            </span>
          </div>

          <h1 className="sx-display sx-d1">
            <RevealWords as="span" text="Where every number" />
            <RevealWords
              as="span"
              text="came from."
              delay={200}
              className="sx-italic sx-gold"
              style={{ display: "block" }}
            />
          </h1>

          <p className="sx-lede" style={{ marginTop: 26 }}>
            The corpus, the services, the order the agents run in, and the rules
            each one is held to. Nothing on the rest of this site is asserted
            that is not traceable back to something on this page.
          </p>
        </div>
      </section>

      {/* ================================================================
          THE NAME
          ============================================================== */}
      <section className="sx-section sx-section-line" data-status="ETYMOLOGY">
        <div className="sx-two-col">
          <div className="sx-sticky">
            <span className="sx-bracket">01 — ETYMOLOGY</span>
            <div style={{ marginTop: 26 }}>
              <Seal text="SALIX ALBA · CORTEX SALICIS · TREAT THE CAUSE · " />
            </div>
          </div>
          <div>
            <FadeWords
              className="sx-display sx-d2"
              style={{ maxWidth: "20ch" }}
              text="Willow bark yields salicin — medicine's first lesson in treating the cause rather than the complaint. The product is named after the lesson, not the tree."
            />
            <div className="sx-body" style={{ marginTop: 38 }}>
              <p>
                For two thousand years the bark of <em>Salix alba</em> was chewed
                for pain without anyone knowing why it worked. In 1828 salicin
                was isolated from it; seventy years later the same molecule,
                buffered, became aspirin. The interesting part is not the drug.
                It is that the entire advance consisted of finding out
                <em> which part of the bark was doing the work</em>.
              </p>
              <p>
                A sales team is in the position of the bark chewers. Something in
                the four hundred hours is working. Everyone can feel the effect
                and nobody can name the compound. This product does one thing:
                it isolates it, names it, and hands it to the people who do not
                have it yet.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ================================================================
          TIMELINE — the DAG in execution order
          ============================================================== */}
      <section className="sx-section sx-section-line" data-status="EXECUTION ORDER">
        <div className="sx-two-col">
          <div className="sx-sticky">
            <span className="sx-bracket">02 — EXECUTION ORDER</span>
            <RevealWords
              as="h2"
              className="sx-display sx-d3"
              text="One recording, six passes"
              style={{ marginTop: 20, maxWidth: "12ch" }}
            />
            <p className="sx-tag" style={{ marginTop: 22, whiteSpace: "normal", lineHeight: 2 }}>
              EACH STAGE DEGRADES ALONE.
              <br />
              ONLY THE FIRST IS FATAL.
            </p>
          </div>

          <div className="sx-timeline" ref={timeline}>
            {STAGES.map((stage) => (
              <article className="sx-tl-item" key={stage.name}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: 14,
                    marginBottom: 10,
                    flexWrap: "wrap",
                  }}
                >
                  <span className="sx-tag sx-tag-signal">{stage.time}</span>
                  <h3 className="sx-display sx-d3">{stage.name}</h3>
                </div>
                <p
                  style={{
                    fontSize: 13.5,
                    lineHeight: 1.7,
                    color: "var(--text-secondary)",
                    maxWidth: "56ch",
                    margin: "0 0 12px",
                  }}
                >
                  {stage.detail}
                </p>
                <span className="sx-tag sx-tag-gold sx-tag-wrap">[ EMITS · {stage.emits} ]</span>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ================================================================
          HORIZONTAL RUN — the service manifest
          ============================================================== */}
      <section data-status="SERVICE MANIFEST">
        <div
          style={{
            padding: "clamp(70px, 10vh, 130px) var(--edge) clamp(32px, 5vh, 54px)",
            borderTop: "1px solid var(--line)",
          }}
        >
          <span className="sx-bracket">03 — SERVICE MANIFEST</span>
          <RevealWords
            as="h2"
            className="sx-display sx-d1"
            text="Six services, named"
            style={{ marginTop: 20, maxWidth: "12ch" }}
          />
          <p className="sx-lede" style={{ marginTop: 20 }}>
            Every capability maps to one model, and the mapping is a decision
            with a reason rather than a default. Scroll on.
          </p>
        </div>

        <HorizontalRun>
          {SERVICES.map((service) => (
            <article className="sx-run-card" key={service.model}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  marginBottom: 30,
                }}
              >
                <span className="sx-tag sx-tag-gold">[ {service.index} ]</span>
                <span className="sx-tag sx-tag-wrap" style={{ textAlign: "right" }}>
                  {service.surface}
                </span>
              </div>

              <h3 className="sx-display sx-d3" style={{ marginBottom: 14 }}>
                {service.capability}
              </h3>

              <p
                style={{
                  fontSize: 13,
                  lineHeight: 1.68,
                  color: "var(--text-tertiary)",
                  margin: "0 0 auto",
                }}
              >
                {service.note}
              </p>

              <div
                className="sx-num sx-signal"
                style={{
                  marginTop: 28,
                  paddingTop: 14,
                  borderTop: "1px solid var(--line)",
                  fontSize: 12,
                  wordBreak: "break-all",
                }}
              >
                {service.model}
              </div>
            </article>
          ))}
        </HorizontalRun>
      </section>

      {/* ================================================================
          THE CORPUS — live from the API
          ============================================================== */}
      <section className="sx-section sx-section-line" data-status="THE CORPUS">
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            gap: 28,
            flexWrap: "wrap",
            marginBottom: 34,
          }}
        >
          <div>
            <span className="sx-bracket">04 — THE CORPUS</span>
            <RevealWords
              as="h2"
              className="sx-display sx-d2"
              text="Ten conversations, written to tell the truth"
              style={{ marginTop: 20, maxWidth: "16ch" }}
            />
          </div>
          <p className="sx-lede" style={{ maxWidth: "38ch" }}>
            A test asserts that the designated top performer measures best and
            the struggling rep measures worst. If an edit ever inverted that,
            the suite fails rather than the demo quietly telling the opposite of
            the truth.
          </p>
        </div>

        <div className="scroll-x">
          <table className="sx-table">
            <thead>
              <tr>
                <th style={{ width: 34 }}>#</th>
                <th>Conversation</th>
                <th>Rep</th>
                <th>Outcome</th>
                <th style={{ width: 92 }}>Talk ratio</th>
                <th style={{ width: 84 }}>Duration</th>
                <th style={{ width: 72 }}>Score</th>
                <th style={{ width: 74 }}>Date</th>
              </tr>
            </thead>
            <tbody>
              {calls.length === 0 && (
                <tr>
                  <td colSpan={8} className="sx-tag" style={{ padding: "28px 14px" }}>
                    [ START THE API AND SEED THE DATABASE TO POPULATE THE CORPUS ]
                  </td>
                </tr>
              )}
              {calls.map((row, index) => (
                <tr key={row.call.id}>
                  <td className="sx-td-num" style={{ color: "var(--text-quaternary)" }}>
                    {String(index + 1).padStart(2, "0")}
                  </td>
                  <td>
                    <Link
                      href={`/calls/${row.call.id}`}
                      style={{ color: "var(--text-primary)" }}
                    >
                      {row.call.title}
                    </Link>
                  </td>
                  <td>{row.rep_name}</td>
                  <td>
                    <span
                      className="sx-tag"
                      style={{
                        color:
                          row.call.outcome === "won"
                            ? "var(--accent-signal)"
                            : row.call.outcome === "lost"
                              ? "var(--voice-buyer)"
                              : "var(--text-tertiary)",
                      }}
                    >
                      {row.call.outcome.toUpperCase()}
                    </span>
                  </td>
                  <td className="sx-td-num">{percent(row.talk_ratio_rep)}</td>
                  <td className="sx-td-num">{duration(row.call.duration_ms)}</td>
                  <td className="sx-td-num">{row.score?.toFixed(0) ?? "--"}</td>
                  <td className="sx-td-num" style={{ color: "var(--text-quaternary)" }}>
                    {shortDate(row.call.occurred_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* --- The cast ---------------------------------------------------- */}
        {reps.length > 0 && (
          <div style={{ marginTop: 56 }}>
            <span className="sx-bracket">05 — THE CAST</span>
            <div className="sx-metrics" style={{ marginTop: 22 }}>
              {reps.map((snapshot) => (
                <Link
                  key={snapshot.rep.id}
                  href={`/reps/${snapshot.rep.id}`}
                  className="sx-metric roll-host"
                  style={{ display: "block" }}
                >
                  <div className="sx-metric-value">
                    <Count value={snapshot.overall_score} format={(v) => v.toFixed(0)} />
                  </div>
                  <div className="sx-metric-label" style={{ color: "var(--text-secondary)" }}>
                    <span className="roll">
                      <span>{snapshot.rep.name}</span>
                      <span className="sx-signal">{snapshot.rep.name}</span>
                    </span>
                  </div>
                  <div className="sx-tag" style={{ marginTop: 8 }}>
                    {percent(snapshot.win_rate)} WIN · {snapshot.calls} CALLS
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* ================================================================
          THE REFUSALS
          ============================================================== */}
      <section className="sx-section sx-section-line" data-status="NOT SHIPPING ERRORS">
        <div className="sx-two-col">
          <div className="sx-sticky">
            <span className="sx-bracket">06 — NOT SHIPPING ERRORS</span>
          </div>
          <dl
            style={{
              display: "grid",
              gap: 1,
              background: "var(--line)",
              border: "1px solid var(--line)",
              margin: 0,
            }}
          >
            {[
              [
                "Offline mode",
                "Every provider has a deterministic twin. No key, no network, still a complete product — and every test runs without touching a wire.",
              ],
              [
                "Per-stage degradation",
                "If play extraction fails, the call keeps its transcript, metrics and anatomy. Only transcription is fatal.",
              ],
              [
                "Repair loops",
                "Structured output that fails validation is returned to the model with the validator's complaint; citations naming nonexistent segments come back with the list of legal ids.",
              ],
              [
                "Typed across the boundary",
                "The Pydantic contract is compiled into the frontend's types. Renaming a field in Python breaks the typecheck instead of breaking a page at runtime.",
              ],
            ].map(([title, body]) => (
              <div
                key={title}
                style={{ background: "var(--bg-primary)", padding: "24px 26px" }}
              >
                <dt
                  className="sx-display sx-d3"
                  style={{ marginBottom: 10, color: "var(--text-primary)" }}
                >
                  {title}
                </dt>
                <dd
                  style={{
                    margin: 0,
                    fontSize: 13.5,
                    lineHeight: 1.68,
                    color: "var(--text-tertiary)",
                    maxWidth: "62ch",
                  }}
                >
                  {body}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <SiteFooter />
    </main>
  );
}
