"use client";

/**
 * One rep, diagnosed and coached.
 *
 * The radar shows where they sit against the team ceiling. The script below it
 * is the payoff: every line traceable to a colleague's real winning call, with
 * the source shown inline. That traceability is the reason a rep would use it.
 */

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { ScoreRing, SkillRadar, Sparkline, TalkRatioBar } from "@/components/charts";
import { IconArrow, IconDojo, IconLink, IconSpark } from "@/components/icons";
import { Avatar, ErrorState, LoadingState, SectionHead } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  AXIS_LABELS,
  clock,
  money,
  outcomeChip,
  percent,
  scoreTone,
  shortDate,
} from "@/lib/format";
import type { CoachingPlan, RepProfile } from "@/lib/types";

export default function RepPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<RepProfile | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [plan, setPlan] = useState<CoachingPlan | null>(null);
  const [coaching, setCoaching] = useState(false);
  const [coachError, setCoachError] = useState<string | null>(null);

  useEffect(() => {
    api
      .rep(id)
      .then((profile) => {
        setData(profile);
        setPlan(profile.coaching_plan);
      })
      .catch(setError);
  }, [id]);

  async function generatePlan() {
    setCoaching(true);
    setCoachError(null);
    try {
      setPlan(await api.coach(id));
    } catch (e) {
      setCoachError((e as ApiError).detail);
    } finally {
      setCoaching(false);
    }
  }

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!data) return <LoadingState />;

  const { snapshot, calls, plays_used, dojo_sessions } = data;
  const rep = snapshot.rep;

  return (
    <div className="page" data-status="REP PROFILE">
      <header className="page-head">
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <Avatar name={rep.name} top={rep.is_top_performer} />
          <div>
            <div className="eyebrow" style={{ marginBottom: 6 }}>
              Rank {snapshot.rank} of the team
              {rep.is_top_performer && " · sets the ceiling"}
            </div>
            <h1 className="display d2" style={{ margin: 0 }}>
              {rep.name}
            </h1>
            <div
              style={{
                marginTop: 8,
                fontSize: 13,
                color: "var(--ink-3)",
                display: "flex",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <span>{snapshot.calls} calls analysed</span>
              <span>
                {snapshot.won}W / {snapshot.lost}L · {percent(snapshot.win_rate)}
              </span>
              <span className="num">
                {money(rep.attained)} of {money(rep.quota)} quota
              </span>
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Link href={`/dojo?rep=${rep.id}`} className="btn">
            <IconDojo size={13} />
            Practise
          </Link>
          <div style={{ flexShrink: 0, paddingRight: 4 }}>
            <ScoreRing score={snapshot.overall_score} size={68} caption="score" />
          </div>
        </div>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.4fr)",
          gap: 22,
          alignItems: "start",
          marginBottom: 22,
        }}
        className="rep-grid"
      >
        {/* --- Radar ------------------------------------------------------ */}
        <section className="panel" style={{ padding: "17px 18px" }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>
            Skill profile
          </div>
          <div style={{ display: "grid", placeItems: "center", padding: "6px 0" }}>
            <SkillRadar
              values={snapshot.axes}
              benchmark={snapshot.team_axes}
              size={264}
              label={`${rep.name} skill profile against the team ceiling`}
            />
          </div>
          <div
            style={{
              display: "flex",
              gap: 16,
              justifyContent: "center",
              marginTop: 4,
            }}
          >
            <LegendItem color="var(--willow)" label={rep.name.split(" ")[0]} />
            <LegendItem color="var(--ink-4)" label="team ceiling" dashed />
          </div>

          <div style={{ marginTop: 18 }}>
            {Object.entries(snapshot.axes).map(([axis, value]) => {
              const ceiling = snapshot.team_axes[axis as keyof typeof snapshot.team_axes] ?? 0;
              const delta = value - ceiling;
              return (
                <div
                  key={axis}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "6px 0",
                    borderBottom: "1px solid var(--rule)",
                    fontSize: 13,
                  }}
                >
                  <span style={{ flex: 1 }}>
                    {AXIS_LABELS[axis as keyof typeof AXIS_LABELS]}
                  </span>
                  <span className="num" style={{ color: scoreTone(value) }}>
                    {value.toFixed(0)}
                  </span>
                  <span
                    className="num"
                    style={{
                      fontSize: 11.5,
                      width: 42,
                      textAlign: "right",
                      color: delta >= 0 ? "var(--sage)" : "var(--rose)",
                    }}
                  >
                    {delta >= 0 ? "+" : ""}
                    {delta.toFixed(0)}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        {/* --- Coaching plan --------------------------------------------- */}
        <section className="panel-flush">
          <SectionHead
            title="Coaching plan"
            hint={plan ? "Grounded in your team's winning calls" : undefined}
          />
          <div style={{ padding: "14px 18px 18px" }}>
            {!plan && (
              <div style={{ textAlign: "center", padding: "22px 0" }}>
                <p className="prose-body" style={{ margin: "0 auto 16px", fontSize: 13.5 }}>
                  Salix will find where {rep.name.split(" ")[0]} trails the team,
                  search the archive for how colleagues who won handled the same
                  situations, and write a script from those passages.
                </p>
                <button
                  className="btn btn-primary"
                  onClick={generatePlan}
                  disabled={coaching}
                >
                  {coaching ? "Reading the archive…" : "Generate the plan"}
                  {!coaching && <IconArrow size={13} />}
                </button>
                {coachError && (
                  <p style={{ color: "var(--rose)", fontSize: 12.5, marginTop: 12 }}>
                    {coachError}
                  </p>
                )}
              </div>
            )}

            {plan && (
              <>
                <p
                  className="display"
                  style={{
                    fontSize: 20,
                    margin: "0 0 16px",
                    lineHeight: 1.25,
                    borderLeft: "2px solid var(--willow)",
                    paddingLeft: 14,
                  }}
                >
                  {plan.diagnosis}
                </p>

                {plan.gaps.map((gap) => (
                  <div
                    key={gap.axis}
                    style={{ padding: "11px 0", borderBottom: "1px solid var(--rule)" }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "baseline",
                        gap: 8,
                        marginBottom: 4,
                      }}
                    >
                      <span style={{ fontSize: 13.5, fontWeight: 500 }}>
                        {AXIS_LABELS[gap.axis]}
                      </span>
                      <span
                        className={`chip ${
                          gap.severity === "high" ? "chip-rose" : "chip-ember"
                        }`}
                      >
                        {gap.delta.toFixed(0)} behind
                      </span>
                      <span
                        className="num"
                        style={{ marginLeft: "auto", fontSize: 12, color: "var(--ink-3)" }}
                      >
                        {gap.rep_value.toFixed(0)} → {gap.top_value.toFixed(0)}
                      </span>
                    </div>
                    <p style={{ fontSize: 12.8, color: "var(--ink-2)", margin: 0, lineHeight: 1.55 }}>
                      {gap.explanation}
                    </p>
                  </div>
                ))}

                <button
                  className="btn btn-sm"
                  onClick={generatePlan}
                  disabled={coaching}
                  style={{ marginTop: 14 }}
                >
                  {coaching ? "Regenerating…" : "Regenerate"}
                </button>
              </>
            )}
          </div>
        </section>
      </div>

      {/* --- The script -------------------------------------------------- */}
      {plan?.script && <ScriptPanel plan={plan} />}

      {/* --- Drills ------------------------------------------------------ */}
      {plan && plan.drills.length > 0 && (
        <section className="panel-flush" style={{ marginTop: 22 }}>
          <SectionHead title="Drills" hint="Practise these in the Dojo" />
          <div
            style={{
              padding: 18,
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: 14,
            }}
          >
            {plan.drills.map((drill, index) => (
              <div
                key={index}
                className="panel"
                style={{ padding: 15, background: "var(--paper)" }}
              >
                <div className="eyebrow" style={{ marginBottom: 7 }}>
                  {AXIS_LABELS[drill.axis]}
                </div>
                <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 6 }}>
                  {drill.title}
                </div>
                <p style={{ fontSize: 12.8, color: "var(--ink-2)", margin: "0 0 9px", lineHeight: 1.55 }}>
                  {drill.instruction}
                </p>
                <div className="eyebrow" style={{ color: "var(--sage)" }}>
                  Pass: {drill.success_criteria}
                </div>
                <Link
                  href={`/dojo?rep=${rep.id}`}
                  className="btn btn-sm"
                  style={{ marginTop: 12, width: "100%", justifyContent: "center" }}
                >
                  <IconDojo size={12} />
                  Run this drill
                </Link>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* --- Calls and plays --------------------------------------------- */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
          gap: 22,
          marginTop: 22,
          alignItems: "start",
        }}
        className="rep-grid"
      >
        <section className="panel-flush">
          <SectionHead title="Their calls" hint={`${calls.length} analysed`} />
          <div className="scroll-x">
            <table className="table">
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id}>
                    <td style={{ width: 46 }}>
                      <ScoreRing score={call.score} size={34} thickness={3} />
                    </td>
                    <td>
                      <Link href={`/calls/${call.id}`} style={{ fontWeight: 500 }}>
                        {call.title}
                      </Link>
                      <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 2 }}>
                        {shortDate(call.occurred_at)} · {clock(call.duration_ms)}
                      </div>
                    </td>
                    <td style={{ width: 88 }}>
                      <span className={`chip ${outcomeChip(call.outcome)}`}>
                        {call.outcome}
                      </span>
                    </td>
                    <td style={{ width: 96 }}>
                      {call.talk_ratio_rep != null && (
                        <TalkRatioBar ratio={call.talk_ratio_rep} height={5} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div style={{ display: "grid", gap: 22 }}>
          <section className="panel-flush">
            <SectionHead title="Plays they run" />
            <div style={{ padding: "6px 17px 16px" }}>
              {plays_used.length === 0 && (
                <p style={{ fontSize: 13, color: "var(--ink-3)", margin: "10px 0" }}>
                  No reusable narrative moves found in their calls yet. This is
                  usually the largest single opportunity.
                </p>
              )}
              {plays_used.map((play) => (
                <Link
                  key={play.id}
                  href={`/playbook/${play.id}`}
                  style={{ display: "block", padding: "10px 0", borderBottom: "1px solid var(--rule)" }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <IconSpark size={12} style={{ color: "var(--willow)" }} />
                    <span className="display" style={{ fontSize: 16 }}>
                      {play.name}
                    </span>
                    <span className="num" style={{ marginLeft: "auto", fontSize: 11, color: "var(--ink-4)" }}>
                      {play.my_instances?.length ?? 0}×
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </section>

          {dojo_sessions.length > 0 && (
            <section className="panel-flush">
              <SectionHead title="Practice history" />
              <div style={{ padding: "6px 17px 16px" }}>
                {dojo_sessions.map((session) => (
                  <div
                    key={session.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "9px 0",
                      borderBottom: "1px solid var(--rule)",
                    }}
                  >
                    <ScoreRing score={session.score?.overall ?? null} size={32} thickness={3} />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13 }}>vs {session.persona.name}</div>
                      <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                        {session.score?.objections_handled ?? 0} of{" "}
                        {session.score?.objections_faced ?? 0} objections handled
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      <style>{`
        @media (max-width: 1080px) {
          .rep-grid { grid-template-columns: minmax(0, 1fr) !important; }
        }
      `}</style>
    </div>
  );
}

/* ---------------------------------------------------------------------- */

function ScriptPanel({ plan }: { plan: CoachingPlan }) {
  const script = plan.script!;
  return (
    <section className="panel-flush" style={{ marginTop: 22 }}>
      <SectionHead
        title={script.title}
        hint={`${script.grounded_in.length} passages from real winning calls`}
      />
      <div style={{ padding: "16px 20px 22px" }}>
        <p className="lede" style={{ marginTop: 0, marginBottom: 22, fontSize: 14.5 }}>
          {script.scenario}
        </p>

        {script.sections.map((section, sectionIndex) => (
          <div key={sectionIndex} style={{ marginBottom: 26 }}>
            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 10,
                marginBottom: 10,
                paddingBottom: 7,
                borderBottom: "1px solid var(--rule)",
              }}
            >
              <span
                className="num"
                style={{ fontSize: 11, color: "var(--willow)", fontWeight: 500 }}
              >
                {String(sectionIndex + 1).padStart(2, "0")}
              </span>
              <span style={{ fontSize: 14.5, fontWeight: 550 }}>{section.label}</span>
              <span style={{ fontSize: 12, color: "var(--ink-3)", marginLeft: "auto" }}>
                {section.purpose}
              </span>
            </div>

            {section.lines.map((line, lineIndex) => {
              const isRep = line.speaker === "rep";
              return (
                <div key={lineIndex} style={{ marginBottom: 14 }}>
                  <div style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
                    <span
                      className={`chip ${isRep ? "chip-rep" : "chip-buyer"}`}
                      style={{ marginTop: 3, flexShrink: 0 }}
                    >
                      {isRep ? "you" : "them"}
                    </span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <p
                        style={{
                          margin: 0,
                          fontSize: isRep ? 15 : 13.5,
                          lineHeight: 1.6,
                          color: isRep ? "var(--ink)" : "var(--ink-3)",
                          fontStyle: isRep ? "normal" : "italic",
                        }}
                      >
                        {line.text}
                      </p>
                      {line.note && (
                        <p
                          style={{
                            margin: "5px 0 0",
                            fontSize: 12,
                            color: "var(--ink-3)",
                          }}
                        >
                          {line.note}
                        </p>
                      )}
                      {line.source && (
                        <SourceTag source={line.source} />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * The provenance tag under a script line.
 *
 * This is the component that makes the whole feature credible: it names the
 * colleague, the call, and links straight to the moment so the rep can hear it.
 */
function SourceTag({ source }: { source: NonNullable<import("@/lib/types").ScriptLine["source"]> }) {
  return (
    <div
      style={{
        marginTop: 8,
        padding: "8px 11px",
        borderRadius: "var(--r)",
        background: "var(--willow-wash)",
        border: "1px solid color-mix(in oklab, var(--willow) 26%, transparent)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: source.quote ? 5 : 0,
        }}
      >
        <IconLink size={11} style={{ color: "var(--willow)" }} />
        <span className="eyebrow" style={{ color: "var(--willow)" }}>
          {source.rep_name || "a colleague"}
          {source.play_name && ` · ${source.play_name}`}
        </span>
        {source.call_id && (
          <Link
            href={`/calls/${source.call_id}`}
            className="eyebrow"
            style={{ marginLeft: "auto", color: "var(--ink-3)" }}
          >
            hear it →
          </Link>
        )}
      </div>
      {source.quote && (
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.5 }}>
          “{source.quote.slice(0, 300)}
          {source.quote.length > 300 ? "…" : ""}”
        </p>
      )}
    </div>
  );
}

function LegendItem({
  color,
  label,
  dashed,
}: {
  color: string;
  label: string;
  dashed?: boolean;
}) {
  return (
    <span className="eyebrow" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <i
        style={{
          width: 14,
          height: 0,
          borderTop: `2px ${dashed ? "dashed" : "solid"} ${color}`,
          display: "inline-block",
        }}
      />
      {label}
    </span>
  );
}
