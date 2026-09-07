"use client";

/**
 * One call, read end to end.
 *
 * The Helix sits at the top as the shape of the conversation; the transcript
 * runs beside the findings. The binding idea is that nothing is asserted
 * without its evidence: every objection, issue and play links to the exact
 * transcript line it came from, and clicking it scrolls and highlights that
 * line. A claim you cannot check is worth less than no claim.
 */

import Link from "next/link";
import { use, useEffect, useMemo, useRef, useState } from "react";

import { ScoreRing, Stat, TalkRatioBar } from "@/components/charts";
import { Helix } from "@/components/helix/Helix";
import {
  IconArrow,
  IconCheck,
  IconQuote,
  IconSpark,
  IconWarning,
} from "@/components/icons";
import { ErrorState, LoadingState, SectionHead } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { AUTO_DIR, isRtl } from "@/lib/lang";
import {
  AXIS_LABELS,
  clock,
  duration,
  longDate,
  outcomeChip,
  percent,
  scoreTone,
  talkRatioVerdict,
} from "@/lib/format";
import type { CallDetailResponse, EvidenceRef, Segment } from "@/lib/types";

export default function CallPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<CallDetailResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [positionMs, setPositionMs] = useState(0);
  const [focused, setFocused] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  /**
   * The benchmarks the measurements are read against.
   *
   * These were hard-coded constants scattered through the tone expressions
   * below. They are parameters, and a team that has decided its own ceiling is
   * 55% rather than 43% should be able to say so and watch the verdicts move.
   * The measurements themselves never change -- only the line they are being
   * judged against, which is the honest half to make adjustable.
   */
  const [targets, setTargets] = useState({
    talkRatio: 0.43,
    monologueSec: 120,
    patienceMs: 600,
  });

  useEffect(() => {
    api
      .call(id)
      .then(setData)
      .catch(setError);
  }, [id]);

  /** Jump the transcript and the playhead to a cited segment. */
  function goToSegment(segmentId: string | null | undefined) {
    if (!segmentId || !data?.transcript) return;
    const segment = data.transcript.segments.find((s) => s.id === segmentId);
    if (!segment) return;
    setFocused(segmentId);
    setPositionMs(segment.start_ms);
    document
      .getElementById(`seg-${segmentId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!data) return <LoadingState />;

  const { call, metrics, scorecard, analysis, transcript, plays, deal, rep_name } = data;

  return (
    <div className="page" data-status="CALL DETAIL">
      <header className="page-head">
        <div style={{ minWidth: 0 }}>
          <div
            className="eyebrow"
            style={{ marginBottom: 8, display: "flex", gap: 10, alignItems: "center" }}
          >
            <Link href="/calls" style={{ color: "var(--ink-3)" }}>
              Calls
            </Link>
            <span>/</span>
            <span>{call.account}</span>
            <span className={`chip ${outcomeChip(call.outcome)}`}>{call.outcome}</span>
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            {call.title}
          </h1>
          <div
            style={{
              marginTop: 10,
              fontSize: 13,
              color: "var(--ink-3)",
              display: "flex",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <Link href={`/reps/${call.rep_id}`} style={{ color: "var(--ink-2)" }}>
              {rep_name}
            </Link>
            <span>{longDate(call.occurred_at)}</span>
            <span className="num">{duration(call.duration_ms)}</span>
            {deal && (
              <Link href="/deals" style={{ color: "var(--ink-2)" }}>
                {deal.name}
              </Link>
            )}
          </div>
        </div>
        {scorecard && (
          <div style={{ flexShrink: 0, paddingRight: 4 }}>
            <ScoreRing score={scorecard.overall} size={68} caption="score" />
          </div>
        )}
      </header>

      {analysis?.headline && (
        <p
          className="display d3 rise"
          style={{
            margin: "0 0 26px",
            maxWidth: "34ch",
            color: "var(--ink)",
            borderLeft: "2px solid var(--willow)",
            paddingLeft: 18,
          }}
        >
          {analysis.headline}
        </p>
      )}

      {/* --- Specification masthead ---------------------------------------
          The pinned layout: the conversation's own shape on the left, the
          spec sheet and the benchmarks it is read against sticky on the
          right. Moving a benchmark re-judges every verdict on the page
          without touching a single measurement. */}
      {metrics && (
        <section className="call-spec">
          <div className="call-spec-media">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginBottom: 4,
              }}
            >
              <div>
                <h2 className="display" style={{ fontSize: 19, margin: 0 }}>
                  The shape of the conversation
                </h2>
                <p style={{ fontSize: 12.5, color: "var(--ink-3)", margin: "3px 0 0" }}>
                  The ribbon rises when the rep holds the floor and twists when the
                  floor changes hands. Click to seek.
                </p>
              </div>
              <span className="num" style={{ fontSize: 12, color: "var(--ink-3)" }}>
                {clock(positionMs)}
              </span>
            </div>
            <Helix
              metrics={metrics}
              analysis={analysis}
              plays={plays}
              positionMs={positionMs}
              onSeek={setPositionMs}
              height={300}
            />
          </div>

          <aside className="call-spec-side">
            <div className="sx-diag" style={{ marginBottom: 18 }}>
              <div className="sx-diag-head">
                <span>Specification</span>
                <span style={{ color: "var(--accent-signal)" }}>&#9679;</span>
              </div>
              <div className="sx-diag-row" data-tone="muted">
                <span>[ Segments ]</span>
                <b>{transcript?.segments.length ?? 0}</b>
              </div>
              <div className="sx-diag-row" data-tone="muted">
                <span>[ Duration ]</span>
                <b>{duration(call.duration_ms)}</b>
              </div>
              <div className="sx-diag-row">
                <span>[ Talk ratio ]</span>
                <b>{percent(metrics.talk_ratio_rep)}</b>
              </div>
              <div className="sx-diag-row">
                <span>[ Longest monologue ]</span>
                <b>{duration(metrics.longest_monologue_ms)}</b>
              </div>
              <div className="sx-diag-row">
                <span>[ Patience ]</span>
                <b>{Math.round(metrics.patience_ms)}ms</b>
              </div>
              <div className="sx-diag-row" data-tone="gold">
                <span>[ Delivery ]</span>
                <b>{Math.round(metrics.rep_wpm)} wpm</b>
              </div>
              <div className="sx-diag-row" data-tone="gold">
                <span>[ Questions ]</span>
                <b>{metrics.rep_question_count}</b>
              </div>
              <div className="sx-diag-row" data-tone="muted">
                <span>[ Measured by ]</span>
                <b>arithmetic &middot; 0 model calls</b>
              </div>
            </div>

            <div className="eyebrow" style={{ marginBottom: 4 }}>
              Benchmarks
            </div>
            <p style={{ fontSize: 12, color: "var(--ink-3)", margin: "0 0 6px", lineHeight: 1.5 }}>
              Move a line and every verdict below is recomputed against it. The
              measurements do not move.
            </p>

            <Param
              label="Talk-ratio ceiling"
              display={percent(targets.talkRatio)}
              min={25}
              max={75}
              step={1}
              value={Math.round(targets.talkRatio * 100)}
              onChange={(v) => setTargets((t) => ({ ...t, talkRatio: v / 100 }))}
            />
            <Param
              label="Monologue ceiling"
              display={`${targets.monologueSec}s`}
              min={30}
              max={300}
              step={5}
              value={targets.monologueSec}
              onChange={(v) => setTargets((t) => ({ ...t, monologueSec: v }))}
            />
            <Param
              label="Patience target"
              display={`${targets.patienceMs}ms`}
              min={200}
              max={1500}
              step={50}
              value={targets.patienceMs}
              onChange={(v) => setTargets((t) => ({ ...t, patienceMs: v }))}
            />
          </aside>
        </section>
      )}

      {/* --- Measured facts ----------------------------------------------- */}
      {metrics && (
        <section
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(178px, 1fr))",
            gap: 12,
            marginBottom: 26,
          }}
        >
          <div className="panel" style={{ padding: "15px 17px" }}>
            <div className="eyebrow" style={{ marginBottom: 9 }}>
              Talk ratio
            </div>
            <div className="num stat" style={{ marginBottom: 9 }}>
              {percent(metrics.talk_ratio_rep)}
            </div>
            <TalkRatioBar ratio={metrics.talk_ratio_rep} />
            <div
              style={{
                marginTop: 7,
                fontSize: 12,
                color:
                  metrics.talk_ratio_rep > targets.talkRatio
                    ? "var(--ember)"
                    : "var(--sage)",
              }}
            >
              {talkRatioVerdict(metrics.talk_ratio_rep)} &middot; ceiling{" "}
              {percent(targets.talkRatio)}
            </div>
          </div>

          <Stat
            label="Longest monologue"
            value={duration(metrics.longest_monologue_ms)}
            tone={
              metrics.longest_monologue_ms > targets.monologueSec * 1000
                ? "var(--rose)"
                : undefined
            }
            hint={
              metrics.longest_monologue_ms > targets.monologueSec * 1000 ? (
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ padding: 0, height: "auto", color: "var(--willow)" }}
                  onClick={() => setPositionMs(metrics.longest_monologue_at_ms)}
                >
                  Starts at {clock(metrics.longest_monologue_at_ms)} →
                </button>
              ) : (
                `Under the ${targets.monologueSec}s ceiling`
              )
            }
          />

          <Stat
            label="Patience"
            value={`${Math.round(metrics.patience_ms)}ms`}
            hint={`Pause before replying. Target ${targets.patienceMs}ms.`}
            tone={metrics.patience_ms < targets.patienceMs ? "var(--ember)" : undefined}
          />

          <Stat
            label="Questions asked"
            value={metrics.rep_question_count}
            hint={`${metrics.rep_question_rate_per_min}/min · ${percent(
              metrics.open_question_ratio,
            )} open-ended`}
          />

          <Stat
            label="Delivery"
            value={`${Math.round(metrics.rep_wpm)}`}
            hint={`words per minute · ${metrics.filler_rate_rep} fillers per 100`}
          />
        </section>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.05fr)",
          gap: 22,
          alignItems: "start",
        }}
        className="call-grid"
      >
        {/* --- Transcript ------------------------------------------------- */}
        <section className="panel-flush" style={{ position: "sticky", top: 18 }}>
          <SectionHead
            title="Transcript"
            hint={`${transcript?.segments.length ?? 0} turns`}
          />
          <div
            ref={transcriptRef}
            style={{ maxHeight: "72vh", overflowY: "auto", padding: "4px 0" }}
          >
            {transcript?.segments.map((segment) => (
              <TranscriptLine
                key={segment.id}
                segment={segment}
                active={
                  positionMs >= segment.start_ms && positionMs < segment.end_ms
                }
                focused={focused === segment.id}
                onClick={() => {
                  setPositionMs(segment.start_ms);
                  setFocused(segment.id);
                }}
              />
            ))}
          </div>
        </section>

        {/* --- Findings --------------------------------------------------- */}
        <div style={{ display: "grid", gap: 22 }}>
          {scorecard && (
            <section className="panel-flush">
              <SectionHead title="Scorecard" hint="Against the team ceiling" />
              <div style={{ padding: "12px 17px 16px" }}>
                {scorecard.axes.map((axis) => (
                  <div key={axis.axis} style={{ marginBottom: 13 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        marginBottom: 5,
                      }}
                    >
                      <span style={{ fontSize: 13 }}>{AXIS_LABELS[axis.axis]}</span>
                      <span
                        className="num"
                        style={{ fontSize: 13, color: scoreTone(axis.score) }}
                      >
                        {axis.score.toFixed(0)}
                      </span>
                    </div>
                    <div className="meter">
                      <i
                        style={{
                          width: `${axis.score}%`,
                          background: scoreTone(axis.score),
                        }}
                      />
                      <span
                        style={{
                          position: "absolute",
                          left: `${axis.benchmark}%`,
                          top: -2,
                          bottom: -2,
                          width: 1.5,
                          background: "var(--ink-3)",
                          opacity: 0.6,
                        }}
                      />
                    </div>
                    {axis.drivers.length > 0 && (
                      <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 5 }}>
                        {axis.drivers[0]}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {analysis && (
            <>
              {analysis.objections.length > 0 && (
                <section className="panel-flush">
                  <SectionHead
                    title="Objections"
                    hint={`${analysis.objections.filter((o) => o.handled).length} of ${
                      analysis.objections.length
                    } addressed`}
                  />
                  <div style={{ padding: "6px 17px 16px" }}>
                    {analysis.objections.map((objection) => (
                      <div
                        key={objection.id}
                        style={{
                          padding: "12px 0",
                          borderBottom: "1px solid var(--rule)",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            marginBottom: 6,
                          }}
                        >
                          <span
                            className={`chip ${
                              objection.handled ? "chip-sage" : "chip-rose"
                            }`}
                          >
                            {objection.category.replace("_", " ")}
                          </span>
                          <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                            {objection.handled
                              ? `handled · ${objection.handling_quality}/5`
                              : "left open"}
                          </span>
                        </div>
                        <EvidenceQuote
                          evidence={objection.raised}
                          onGo={() => goToSegment(objection.raised.segment_id)}
                        />
                        {objection.note && (
                          <p
                            style={{
                              fontSize: 12.5,
                              color: "var(--ink-2)",
                              margin: "7px 0 0",
                            }}
                          >
                            {objection.note}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <MeddicPanel analysis={analysis} onGo={goToSegment} />

              {plays.length > 0 && (
                <section className="panel-flush">
                  <SectionHead title="Plays run" hint="Reusable narrative moves" />
                  <div style={{ padding: "6px 17px 16px" }}>
                    {plays.map((play) => (
                      <div key={play.id} style={{ padding: "11px 0", borderBottom: "1px solid var(--rule)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                          <IconSpark size={13} style={{ color: "var(--willow)" }} />
                          <Link href={`/playbook/${play.id}`} className="display" style={{ fontSize: 17 }}>
                            {play.name}
                          </Link>
                        </div>
                        <p style={{ fontSize: 12.5, color: "var(--ink-3)", margin: "4px 0 0" }}>
                          {play.thesis}
                        </p>
                        {play.instance?.quote && (
                          <p
                            className={`quote${isRtl(play.instance.quote) ? " urdu-prose" : ""}`}
                            dir={AUTO_DIR}
                            style={{ fontSize: 12.5, marginTop: 8 }}
                          >
                            {play.instance.quote.slice(0, 260)}
                            {play.instance.quote.length > 260 ? "…" : ""}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <IssueList
                title="What cost this call"
                items={analysis.issues}
                tone="warn"
                onGo={goToSegment}
              />
              <IssueList
                title="What worked"
                items={analysis.strengths}
                tone="good"
                onGo={goToSegment}
              />

              <NextStepPanel analysis={analysis} onGo={goToSegment} />
            </>
          )}
        </div>
      </div>

      <style>{`
        @media (max-width: 1080px) {
          .call-grid { grid-template-columns: minmax(0, 1fr) !important; }
          .call-grid > section:first-child { position: static !important; }
        }
      `}</style>
    </div>
  );
}

/* ---------------------------------------------------------------------- */

/**
 * One adjustable benchmark.
 *
 * A real `input[type=range]` rather than a div with a drag handler, so it
 * arrives with keyboard control, a label association and the platform's own
 * touch target for free.
 */
function Param({
  label,
  display,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  display: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  const id = `param-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <div className="sx-param">
      <div className="sx-param-head">
        <label htmlFor={id} className="eyebrow">
          {label}
        </label>
        <span className="sx-param-value">{display}</span>
      </div>
      <input
        id={id}
        className="sx-range"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

function TranscriptLine({
  segment,
  active,
  focused,
  onClick,
}: {
  segment: Segment;
  active: boolean;
  focused: boolean;
  onClick: () => void;
}) {
  const isRep = segment.role === "rep";
  return (
    <div
      id={`seg-${segment.id}`}
      onClick={onClick}
      style={{
        display: "grid",
        gridTemplateColumns: "46px 1fr",
        gap: 10,
        padding: "7px 16px",
        cursor: "pointer",
        background: focused
          ? "var(--willow-wash)"
          : active
            ? "var(--paper-3)"
            : "transparent",
        borderLeft: `2px solid ${
          focused ? "var(--willow)" : active ? "var(--rule-strong)" : "transparent"
        }`,
        transition: "background 200ms ease",
      }}
    >
      <span
        className="num"
        style={{ fontSize: 10.5, color: "var(--ink-4)", paddingTop: 3 }}
      >
        {clock(segment.start_ms)}
      </span>
      <div style={{ minWidth: 0 }}>
        <span
          className={`chip ${isRep ? "chip-rep" : "chip-buyer"}`}
          style={{ marginRight: 7, verticalAlign: 1 }}
        >
          {isRep ? "rep" : "buyer"}
        </span>
        <span style={{ fontSize: 13.5, lineHeight: 1.58, color: "var(--ink-2)" }}>
          <span
            dir={AUTO_DIR}
            className={isRtl(segment.text) ? "urdu-prose" : undefined}
            style={{ display: "block" }}
          >
            {segment.text}
          </span>
        </span>
      </div>
    </div>
  );
}

function EvidenceQuote({
  evidence,
  onGo,
}: {
  evidence: EvidenceRef;
  onGo: () => void;
}) {
  if (!evidence.quote) return null;
  return (
    <button
      onClick={onGo}
      className="quote"
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        border: "none",
        borderLeft: "2px solid var(--rule-strong)",
        background: "transparent",
        cursor: "pointer",
        font: "inherit",
        fontSize: 13,
        padding: "2px 0 2px 14px",
      }}
      title="Jump to this line in the transcript"
    >
      <IconQuote
        size={11}
        style={{ color: "var(--ink-4)", marginRight: 5, verticalAlign: -1 }}
      />
      <span dir={AUTO_DIR} className={isRtl(evidence.quote) ? "urdu-prose" : undefined}>
        {evidence.quote}
      </span>
      {evidence.start_ms != null && (
        <span className="num" style={{ color: "var(--willow)", marginLeft: 6, fontSize: 11 }}>
          {clock(evidence.start_ms)}
        </span>
      )}
    </button>
  );
}

function IssueList({
  title,
  items,
  tone,
  onGo,
}: {
  title: string;
  items: CallDetailResponse["analysis"] extends null
    ? never
    : NonNullable<CallDetailResponse["analysis"]>["issues"];
  tone: "warn" | "good";
  onGo: (id: string | null | undefined) => void;
}) {
  if (!items || items.length === 0) return null;
  const Icon = tone === "warn" ? IconWarning : IconCheck;
  const color = tone === "warn" ? "var(--ember)" : "var(--sage)";

  return (
    <section className="panel-flush">
      <SectionHead title={title} />
      <div style={{ padding: "6px 17px 16px" }}>
        {items.map((item, index) => (
          <div key={index} style={{ padding: "12px 0", borderBottom: "1px solid var(--rule)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
              <Icon size={13} style={{ color }} />
              <span style={{ fontSize: 13.5, fontWeight: 500 }}>{item.title}</span>
            </div>
            <p style={{ fontSize: 12.8, color: "var(--ink-2)", margin: "0 0 8px", lineHeight: 1.55 }}>
              {item.explanation}
            </p>
            {item.evidence.map((evidence, i) => (
              <EvidenceQuote
                key={i}
                evidence={evidence}
                onGo={() => onGo(evidence.segment_id)}
              />
            ))}
            {item.better_move && (
              <p
                style={{
                  fontSize: 12.8,
                  margin: "9px 0 0",
                  padding: "8px 11px",
                  borderRadius: "var(--r)",
                  background: tone === "warn" ? "var(--ember-wash)" : "var(--sage-wash)",
                  color: "var(--ink-2)",
                }}
              >
                <span className="eyebrow" style={{ marginRight: 7, color }}>
                  {tone === "warn" ? "instead" : "why"}
                </span>
                {item.better_move}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function MeddicPanel({
  analysis,
  onGo,
}: {
  analysis: NonNullable<CallDetailResponse["analysis"]>;
  onGo: (id: string | null | undefined) => void;
}) {
  const rows = [
    ["Metrics", analysis.meddic.metrics],
    ["Economic buyer", analysis.meddic.economic_buyer],
    ["Decision criteria", analysis.meddic.decision_criteria],
    ["Decision process", analysis.meddic.decision_process],
    ["Pain", analysis.meddic.identify_pain],
    ["Champion", analysis.meddic.champion],
  ] as const;

  const covered = rows.filter(([, item]) => item.covered).length;

  return (
    <section className="panel-flush">
      <SectionHead title="What we learned" hint={`MEDDIC ${covered}/6`} />
      <div style={{ padding: "8px 17px 16px" }}>
        {rows.map(([label, item]) => (
          <div
            key={label}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              padding: "8px 0",
              borderBottom: "1px solid var(--rule)",
            }}
          >
            <span
              style={{
                width: 15,
                height: 15,
                borderRadius: 4,
                display: "grid",
                placeItems: "center",
                flexShrink: 0,
                marginTop: 1,
                background: item.covered ? "var(--sage-wash)" : "var(--paper-3)",
                color: item.covered ? "var(--sage)" : "var(--ink-4)",
                border: `1px solid ${item.covered ? "transparent" : "var(--rule)"}`,
              }}
            >
              {item.covered ? <IconCheck size={10} /> : null}
            </span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 13, color: item.covered ? "var(--ink)" : "var(--ink-3)" }}>
                {label}
              </div>
              {item.evidence[0]?.quote && (
                <button
                  onClick={() => onGo(item.evidence[0].segment_id)}
                  style={{
                    border: "none",
                    background: "none",
                    padding: 0,
                    marginTop: 3,
                    font: "inherit",
                    fontSize: 12,
                    color: "var(--ink-3)",
                    textAlign: "left",
                    cursor: "pointer",
                    display: "block",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    maxWidth: "100%",
                  }}
                >
                  <span
                    dir={AUTO_DIR}
                    className={isRtl(item.evidence[0].quote ?? "") ? "urdu-prose" : undefined}
                  >
                    {item.evidence[0].quote}
                  </span>
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function NextStepPanel({
  analysis,
  onGo,
}: {
  analysis: NonNullable<CallDetailResponse["analysis"]>;
  onGo: (id: string | null | undefined) => void;
}) {
  const step = analysis.next_step;

  return (
    <section
      className="panel"
      style={{
        padding: "16px 18px",
        borderColor: step
          ? "var(--rule)"
          : "color-mix(in oklab, var(--rose) 40%, var(--rule))",
      }}
    >
      <div className="eyebrow" style={{ marginBottom: 9 }}>
        How it ended
      </div>
      {!step ? (
        <p style={{ margin: 0, fontSize: 14, color: "var(--rose)" }}>
          No next step was agreed. The deal moves forward only if someone
          remembers to chase it.
        </p>
      ) : (
        <>
          <p style={{ margin: "0 0 10px", fontSize: 14, lineHeight: 1.55 }}>{step.text}</p>
          <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
            <span className={`chip ${step.has_date ? "chip-sage" : "chip-ember"}`}>
              {step.has_date ? "dated" : "no date"}
            </span>
            <span className={`chip ${step.is_mutual ? "chip-sage" : "chip-ember"}`}>
              {step.is_mutual ? "mutual" : "rep only"}
            </span>
          </div>
          {step.evidence && (
            <div style={{ marginTop: 10 }}>
              <EvidenceQuote
                evidence={step.evidence}
                onGo={() => onGo(step.evidence?.segment_id)}
              />
            </div>
          )}
        </>
      )}
    </section>
  );
}
