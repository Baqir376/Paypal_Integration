"use client";

/**
 * The index.
 *
 * Structured as an argument, not a feature list: the claim, the mechanism, the
 * proof, the way in. Every number on this page is either fetched from the
 * running API or is a fact about the repository that a reader can check — the
 * test count, the model identifiers, the embedding width. Nothing here is
 * decorative arithmetic, because the product's entire thesis is that a figure
 * you cannot recompute is a figure you should not trust.
 *
 * Structure follows the DormData benchmark:
 *
 *   hero            split headline, word reveal scrubbed by scroll velocity,
 *                   dual-layer rolling actions, monospaced technical metadata
 *   manifesto       sticky bracket tag left, editorial statement right with a
 *                   word-by-word fade, metric cards beneath
 *   chapter runs    horizontally expanding accordion over the six agents,
 *                   each opening onto a full-bleed plate and a spec table
 *   pinned slides   the four principles, parallax plates, technical bullets
 *   evidence        a real analysed call, rendered live through the same
 *                   component the console uses
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { Helix } from "@/components/helix/Helix";
import { LockedTheme } from "@/components/LockedTheme";
import { Mark } from "@/components/Mark";
import { ChapterSlides, type Slide } from "@/components/system/ChapterSlides";
import { Loader } from "@/components/system/Loader";
import {
  Count,
  FadeWords,
  Parallax,
  RevealWords,
  Seal,
} from "@/components/system/primitives";
import { SiteFooter } from "@/components/system/SiteFooter";
import { SvcCols, type Chapter } from "@/components/system/SvcCols";
import { api } from "@/lib/api";
import { TEST_COUNT } from "@/lib/facts";
import { percent } from "@/lib/format";
import { scrollTo } from "@/lib/motion";
import SAMPLE_CALL from "@/lib/sample-call.json";
import type { CallDetailResponse, Health, Me, Overview } from "@/lib/types";

/* ==========================================================================
   Content
   ========================================================================== */

/** The six specialists of the analysis DAG, in the order they run. */
const CHAPTERS: Chapter[] = [
  {
    index: "01",
    spine: "Transcriptionist",
    title: "Hears who was speaking",
    copy: "Qwen ASR with speaker diarization, submitted as an async task and polled to completion. Which voice belongs to the salesperson is then worked out from the shape of the conversation — who asks, who answers, who names the price — rather than from a label somebody remembered to set in the CRM.",
    plate: "--img-ch-01",
    specs: [
      { label: "Model", value: "qwen-audio-3.0-asr-flash" },
      { label: "Transport", value: "X-DashScope-Async" },
      { label: "Diarization", value: "2 speakers" },
      { label: "Timestamp resolution", value: "1 ms" },
    ],
  },
  {
    index: "02",
    spine: "Prosodist",
    title: "Measures, never guesses",
    copy: "Pure arithmetic over diarized millisecond timestamps. Overlapping speech is unioned rather than summed, so ratios stay coherent; a two-word acknowledgement from the buyer does not end the rep's monologue; interruptions are excluded from the patience mean rather than dragging it to zero. No language model is consulted, and every figure on every screen can be recomputed by hand from the transcript.",
    plate: "--img-ch-02",
    specs: [
      { label: "Language model calls", value: "0" },
      { label: "Measured axes", value: "7" },
      { label: "Hand-computed fixtures", value: "45" },
      { label: "Talk-ratio benchmark", value: "43%" },
    ],
  },
  {
    index: "03",
    spine: "Anatomist",
    title: "Reads the structure",
    copy: "Stages, objections, MEDDIC coverage and commitments — each one citing the transcript segments it came from. Citations are hydrated against the real transcript, and a segment id that does not exist is treated as a fabrication: the agent is asked again with the list of ids it may actually use. A citation that still cannot be resolved is removed rather than displayed.",
    plate: "--img-ch-03",
    specs: [
      { label: "Model", value: "qwen3.8-max" },
      { label: "Citation policy", value: "hydrate or drop" },
      { label: "On a bad id", value: "re-ask with legal ids" },
      { label: "Framework", value: "MEDDIC" },
    ],
  },
  {
    index: "04",
    spine: "Playwright",
    title: "Finds the moves that won",
    copy: "A team of five reps generates hundreds of play candidates that are mostly the same handful of moves rediscovered. Candidates are embedded on their structure — kind, thesis, trigger, beats — so a near match becomes another instance of an existing play rather than a near-duplicate entry. The library converges on a dozen named moves instead of sprawling into hundreds.",
    plate: "--img-ch-04",
    specs: [
      { label: "Embedding", value: "text-embedding-v4" },
      { label: "Vector width", value: "1024 d" },
      { label: "Similarity", value: "cosine" },
      { label: "Embedded on", value: "structure, not prose" },
    ],
  },
  {
    index: "05",
    spine: "Coach",
    title: "Retrieves, does not advise",
    copy: "For each axis where a rep trails the team, Salix searches the moment index for how a colleague who won handled the same situation — filtered to exclude the rep's own habits, diversified with MMR so the passages are not five phrasings of one sentence. The script is written from those passages, and every line traces back to a real call with the colleague's name on it.",
    plate: "--img-ch-05",
    specs: [
      { label: "Retrieval", value: "MMR-diversified" },
      { label: "Excluded", value: "the rep's own calls" },
      { label: "Restricted to", value: "won outcomes" },
      { label: "Every line", value: "clickable to source" },
    ],
  },
  {
    index: "06",
    spine: "Analyst",
    title: "Explains the number",
    copy: "Calls are chained into deal trajectories, risk is flagged with a named and evidenced cause rather than a score, and at the end of the cycle it writes the report explaining why the quarter landed where it did — in terms of the conversations that produced it.",
    plate: "--img-ch-06",
    specs: [
      { label: "Unit of analysis", value: "the deal, not the call" },
      { label: "Risk", value: "named + evidenced" },
      { label: "Output", value: "cycle report" },
      { label: "Degradation", value: "per stage, non-fatal" },
    ],
  },
];

/** The four principles, as pinned slides. */
const PRINCIPLES: Slide[] = [
  {
    chapter: "PRINCIPLE 01",
    eyebrow: "ARITHMETIC",
    title: "A number you cannot recompute is a number you should not trust",
    body: "Talk ratio, longest monologue, patience, interruptions, question rate, pace and filler density are computed in Python from diarized timestamps. There is no model in that path, and there is nothing to hallucinate.",
    bullets: [
      "Overlapping speech is unioned rather than summed, so two ratios cannot add to more than one.",
      "A two-word “mm-hmm” does not break a monologue; a real turn does.",
      "Interruptions are excluded from the patience mean rather than collapsing it to zero.",
      "Forty-five unit tests check the engine against fixtures computed by hand.",
    ],
    plate: "--img-ch-02",
  },
  {
    chapter: "PRINCIPLE 02",
    eyebrow: "EVIDENCE",
    title: "Nothing is asserted without the seconds it came from",
    body: "Every finding the language model produces must cite the transcript segments behind it. Those citations are resolved against the real transcript before anything reaches a screen.",
    bullets: [
      "A segment id that does not exist is treated as a fabrication, not as a typo.",
      "The agent is asked again, with the explicit list of ids it may use.",
      "A citation that still cannot be resolved is removed rather than displayed.",
      "Structured output that fails validation is returned with the validator's complaint attached.",
    ],
    plate: "--img-ch-03",
  },
  {
    chapter: "PRINCIPLE 03",
    eyebrow: "CONVERGENCE",
    title: "A playbook that grows forever is not a playbook",
    body: "Play candidates are embedded on their structure rather than their wording, so the same move discovered in four different calls converges into one named play with four instances.",
    bullets: [
      "Embedded on kind, thesis, trigger and beats — not on the sentence.",
      "A near match becomes another instance, not another entry.",
      "The library settles on roughly a dozen moves across a full cycle.",
      "Each play carries the recordings that prove it works.",
    ],
    plate: "--img-ch-04",
  },
  {
    chapter: "PRINCIPLE 04",
    eyebrow: "TRANSFER",
    title: "Coaching is retrieval, not advice",
    body: "Telling a rep to build more rapport changes nothing. What changes behaviour is hearing the exact sentence a colleague used to turn the exact objection that keeps beating them.",
    bullets: [
      "The search is scoped to calls that were actually won.",
      "The rep's own habits are excluded, so the answer is never their own reflex returned to them.",
      "MMR diversification stops five passages saying one thing.",
      "The Dojo scores practice on the same engine that scores real recordings.",
    ],
    plate: "--img-ch-05",
  },
];

/* ==========================================================================
   Page
   ========================================================================== */

export default function LandingPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [ownCall, setDemo] = useState<CallDetailResponse | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const demo = ownCall ?? (SAMPLE_CALL as unknown as CallDetailResponse);
  const stranger = !!me?.auth_required && !me.user;

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
    // The homepage is public, and a refused request sends the browser to log in. So
    // nothing private is even asked for until it is known who is reading.
    api
      .me()
      .then((me) => {
        setMe(me);
        if (me.auth_required && !me.user) return;
        api.overview().then(setOverview).catch(() => {});

        // Somebody with their own calls sees one of those in the evidence section.
        api
          .calls({ limit: 20 })
          .then((calls) => {
            const best =
              calls.find((c) => (c.score ?? 0) > 60 && c.call.outcome === "won") ??
              calls[0];
            if (best) return api.call(best.call.id);
          })
          .then((detail) => detail && setDemo(detail))
          .catch(() => {});
      })
      .catch(() => {});
  }, []);

  const team = overview?.team;
  const live = health?.provider_mode === "live";

  /**
   * What is actually answering, per capability.
   *
   * These used to be hard-coded Qwen model names beside a "QWEN LIVE" badge.
   * That was true when Model Studio was the only provider, and became a lie
   * the moment the reasoning layer could point elsewhere: a deployment running
   * Gemini with transcription on the offline twin still announced itself as
   * QWEN LIVE, with a Qwen ASR model named underneath, on the page whose whole
   * argument is that nothing should be asserted without evidence.
   *
   * /api/health already reports the resolved truth per capability. This reads
   * it rather than restating a guess.
   */
  const up = (value?: string) => (value ?? "").toUpperCase();
  const engine = {
    reasoning: health?.providers?.reasoning,
    transcription: health?.providers?.transcription,
    embedding: health?.providers?.embedding,
    speech: health?.providers?.speech,
  };
  const offline = (who?: string) => !who || who === "offline twin";
  /** The badge names whoever is actually reasoning, or says nobody is. */
  const badge = live && !offline(engine.reasoning)
    ? `${up(engine.reasoning)} LIVE`
    : "DETERMINISTIC OFFLINE TWIN";

  return (
    <main className="sx-page sx-dark">
      {/* Composed against black; ignores the theme preference entirely.
          See components/LockedTheme.tsx. */}
      <LockedTheme theme="dark" />
      <Loader />

      {/* ================================================================
          HERO
          ============================================================== */}
      <section className="sx-hero" data-status="INDEX">
        <Parallax className="sx-hero-plate" distance={180} />

        <div className="sx-hero-head">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              marginBottom: 30,
              flexWrap: "wrap",
            }}
          >
            <Mark size={26} />
            <span className="sx-tag sx-tag-gold">[ SALIX ]</span>
            <span className="sx-tag">[ SALES CALL COACHING ]</span>
          </div>

          <h1 className="sx-display sx-d0">
            <RevealWords as="span" text="Four hundred hours" />
            {/* The second line is the turn in the sentence, so it is set in
                the italic and carries the accent. High contrast between the
                halves is what makes the split read as an argument rather
                than as a line break. */}
            <RevealWords
              as="span"
              text="nobody listened to."
              delay={220}
              className="sx-italic sx-gold"
              style={{ display: "block" }}
            />
          </h1>

          <p className="sx-lede" style={{ marginTop: 30 }}>
            Salix listens to every call your team runs, measures what actually
            happened down to the millisecond, and hands the moves that close
            deals to the reps who are missing quota — in their own colleagues'
            words, with the recording to prove it.
          </p>

          <div className="sx-hero-actions">
            <Link href={stranger ? "/signup" : "/console"} className="sx-btn sx-btn-solid roll-host">
              <span className="roll">
                <span>{stranger ? "Get started" : "Open the dashboard"}</span>
                <span>{stranger ? "Get started" : "Open the dashboard"}</span>
              </span>
              <Arrow />
            </Link>
            <button
              type="button"
              className="sx-btn roll-host"
              onClick={() => scrollTo("#method", -40)}
            >
              <span className="roll">
                <span>Read the method</span>
                <span>Read the method</span>
              </span>
            </button>
          </div>

          <div className="sx-hero-meta">
            <span className="sx-tag">[ ENGLISH · URDU · ROMAN URDU ]</span>
            <span className="sx-tag">[ EVERY FINDING CITES THE TRANSCRIPT ]</span>
            <span className="sx-tag sx-tag-signal">[ PRACTISE AGAINST THE BUYER WHO BEAT YOU ]</span>
          </div>
        </div>

        <div className="sx-scroll-hint" aria-hidden="true">
          <span className="sx-tag" style={{ writingMode: "vertical-rl" }}>
            SCROLL
          </span>
          <div className="sx-scroll-hint-track" />
        </div>
      </section>

      {/* ================================================================
          MANIFESTO
          ============================================================== */}
      <section
        className="sx-section sx-section-line"
        id="method"
        data-status="MANIFESTO"
      >
        <div className="sx-manifesto-plate" aria-hidden="true" />

        <div className="sx-two-col">
          <div className="sx-sticky">
            <span className="sx-bracket">01 — MANIFESTO</span>
            <div style={{ marginTop: 26 }}>
              <Seal />
            </div>
          </div>

          <div>
            <FadeWords
              className="sx-display sx-d2"
              style={{ maxWidth: "22ch" }}
              text="Every dashboard can tell you the win rate fell. Almost none can tell you it fell because pricing objections went unanswered on second calls, and then play you the eleven seconds where it happened."
            />

            <div className="sx-body" style={{ marginTop: 40 }}>
              <p>
                Your top performer and your struggling rep make the same number
                of calls. The difference is what happens inside them, and nobody
                has four hundred hours to find out what.
              </p>
              <p>
                Conversation intelligence tools will tell you that a rep talks
                too much. That is true and nearly useless. Salix is built around
                one idea instead: the thing that changes behaviour is hearing the
                exact sentence a colleague used to turn the exact objection that
                keeps beating you.
              </p>
            </div>

            {/* Real figures from the running API, with the repository facts
                that do not change beside them. */}
            <div className="sx-metrics" style={{ marginTop: 48 }}>
              <Metric
                value={team ? <Count value={team.calls_analyzed} /> : "10"}
                label="Conversations through the full DAG, transcript to cycle report"
              />
              <Metric
                value={
                  team ? (
                    <Count
                      value={team.avg_talk_ratio}
                      format={(v) => percent(v)}
                    />
                  ) : (
                    "—"
                  )
                }
                label="Average talk ratio measured, against a 43% benchmark"
              />
              <Metric value={<Count value={45} />} label="Metric fixtures computed by hand and asserted in tests" />
              <Metric value={<Count value={TEST_COUNT} />} label="Tests across the engine, the DAG and every HTTP endpoint" />
              <Metric value="0" label="Language model calls anywhere in the measurement path" />
            </div>
          </div>
        </div>
      </section>

      {/* ================================================================
          CHAPTER RUNS — the six agents
          ============================================================== */}
      <section id="pipeline" className="sx-section-line" data-status="THE PIPELINE">
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            gap: 30,
            flexWrap: "wrap",
            padding: "clamp(70px, 10vh, 130px) var(--edge) clamp(34px, 5vh, 58px)",
          }}
        >
          <div>
            <span className="sx-bracket">02 — THE PIPELINE</span>
            <RevealWords
              as="h2"
              className="sx-display sx-d1"
              text="Six specialists, one recording"
              style={{ marginTop: 22, maxWidth: "13ch" }}
            />
          </div>
          <p className="sx-lede" style={{ maxWidth: "36ch" }}>
            Each stage degrades on its own. If play extraction fails, the call
            keeps its transcript, its metrics and its anatomy — only
            transcription is fatal, because without it there is nothing to
            analyse.
          </p>
        </div>

        <SvcCols chapters={CHAPTERS} />
      </section>

      {/* ================================================================
          PINNED CHAPTER SLIDES — the principles
          ============================================================== */}
      <section data-status="PRINCIPLES">
        <div
          style={{
            padding: "clamp(80px, 12vh, 150px) var(--edge) clamp(40px, 6vh, 70px)",
            borderTop: "1px solid var(--line)",
          }}
        >
          <span className="sx-bracket">03 — PRINCIPLES</span>
          <RevealWords
            as="h2"
            className="sx-display sx-d1"
            text="What we refused to do"
            style={{ marginTop: 22, maxWidth: "12ch" }}
          />
        </div>

        <ChapterSlides slides={PRINCIPLES} />
      </section>

      {/* ================================================================
          EVIDENCE — a real analysed call
          ============================================================== */}
      <section id="evidence" className="sx-section sx-section-line" data-status="EVIDENCE">
        <div className="sx-two-col">
          <div className="sx-sticky">
            <span className="sx-bracket">04 — EVIDENCE</span>
            <p
              className="sx-tag"
              style={{
                marginTop: 22,
                whiteSpace: "normal",
                lineHeight: 1.9,
                letterSpacing: "0.14em",
              }}
            >
              {ownCall
                ? `RENDERED LIVE FROM ${ownCall.call.title.toUpperCase()}`
                : "RENDERED LIVE FROM A SAMPLE CALL"}
            </p>
          </div>

          <div>
            <RevealWords
              as="h2"
              className="sx-display sx-d2"
              text="This is not a screenshot"
              style={{ maxWidth: "14ch" }}
            />
            <p className="sx-lede" style={{ marginTop: 20 }}>
              The ribbon below is a sample conversation, scripted for this
              demo and drawn by the same component the dashboard uses, from the
              same measurements. Its thickness is who held the floor; its markers
              are objections, commitments and the plays that landed.
            </p>

            <div
              style={{
                marginTop: 36,
                border: "1px solid var(--line)",
                background: "var(--bg-sunken)",
                minHeight: 340,
              }}
            >
              {demo?.metrics ? (
                <Helix
                  metrics={demo.metrics}
                  analysis={demo.analysis}
                  plays={demo.plays}
                  height={340}
                  interactive={false}
                  cinematic
                  legend={false}
                />
              ) : (
                <div
                  className="sx-tag"
                  style={{ display: "grid", placeItems: "center", height: 340 }}
                >
                  [ START THE API AND SEED THE DATABASE TO RENDER A REAL CALL ]
                </div>
              )}
            </div>

            {demo?.metrics && demo.transcript && (
              <div className="sx-metrics" style={{ marginTop: 1 }}>
                <Metric
                  value={percent(demo.metrics.talk_ratio_rep)}
                  label="Talk ratio — the share of speaking time the rep held"
                />
                <Metric
                  value={`${Math.round(demo.metrics.longest_monologue_ms / 1000)}s`}
                  label="Longest unbroken monologue in the conversation"
                />
                <Metric
                  value={String(demo.transcript.segments.length)}
                  label="Diarized segments, each one citable by id"
                />
                <Metric
                  value={String(demo.plays.length)}
                  label="Named plays extracted and matched against the library"
                />
              </div>
            )}

            {demo && (
              <div style={{ marginTop: 30 }}>
                <Link
                  href={`/calls/${demo.call.id}`}
                  className="sx-btn sx-btn-gold roll-host"
                >
                  <span className="roll">
                    <span>Open this call in full</span>
                    <span>Open this call in full</span>
                  </span>
                  <Arrow />
                </Link>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ================================================================
          THE WAY IN
          ============================================================== */}
      <section id="entry" className="sx-section sx-section-line" data-status="ENTRY">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 1,
            background: "var(--line)",
            border: "1px solid var(--line)",
          }}
        >
          <Door
            href="/console"
            index="A"
            title="The command centre"
            copy="One number that answers whether the team is okay, then what is at risk, then who needs help — every tile a doorway to a specific call."
          />
          <Door
            href="/dojo"
            index="B"
            title="The Dojo"
            copy="Practise by voice against a buyer assembled from the objections that actually killed your own deals, weighted by how badly each was handled."
          />
          <Door
            href="/archive"
            index="C"
            title="The provenance"
            copy="Where the measurements come from, what each Alibaba Cloud service is doing, and the corpus every claim on this page was computed against."
          />
        </div>
      </section>

      <SiteFooter />
    </main>
  );
}

/* ==========================================================================
   Furniture
   ========================================================================== */

function Metric({
  value,
  label,
}: {
  value: React.ReactNode;
  label: string;
}) {
  return (
    <div className="sx-metric">
      <div className="sx-metric-value">{value}</div>
      <div className="sx-metric-label">{label}</div>
    </div>
  );
}

function Door({
  href,
  index,
  title,
  copy,
}: {
  href: string;
  index: string;
  title: string;
  copy: string;
}) {
  return (
    <Link
      href={href}
      className="sx-metric roll-host"
      style={{ padding: "34px 30px 30px", display: "block" }}
    >
      <div className="sx-tag sx-tag-gold" style={{ marginBottom: 26 }}>
        [ {index} ]
      </div>
      <h3 className="sx-display sx-d3" style={{ marginBottom: 14 }}>
        <span className="roll">
          <span>{title}</span>
          <span className="sx-signal">{title}</span>
        </span>
      </h3>
      <p style={{ fontSize: 13.5, lineHeight: 1.65, color: "var(--text-tertiary)", margin: 0 }}>
        {copy}
      </p>
    </Link>
  );
}

function Arrow() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3 8h10M9 4l4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="square"
      />
    </svg>
  );
}
