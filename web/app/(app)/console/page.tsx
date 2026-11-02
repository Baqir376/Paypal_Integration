"use client";

/**
 * The command centre.
 *
 * Progressive disclosure: the one number that answers "is the team okay?"
 * comes first, then what is at risk, then who needs help, then the detail.
 * Everything on this page is a doorway to a specific call.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { ScoreRing, Sparkline, Stat, TalkRatioBar } from "@/components/charts";
import { IconArrow, IconWarning } from "@/components/icons";
import { Avatar, ErrorState, LoadingState, SectionHead } from "@/components/ui";
import { FirstRun } from "@/components/FirstRun";
import { ApiError, api } from "@/lib/api";
import {
  SEVERITY_CHIP,
  clock,
  initials,
  money,
  outcomeChip,
  percent,
  scoreTone,
  shortDate,
} from "@/lib/format";
import type { Overview } from "@/lib/types";

/** Read in the browser only: the server does not know what time it is for them. */
function greeting(name: string): string {
  const hour = typeof window === "undefined" ? 12 : new Date().getHours();
  const part = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  return name ? `${part}, ${name}` : part;
}

export default function ConsolePage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [firstName, setFirstName] = useState("");

  useEffect(() => {
    api
      .overview()
      .then(setData)
      .catch((e: ApiError) => setError(e));
    api
      .me()
      .then((me) => setFirstName(me.user?.name.split(" ")[0] ?? ""))
      .catch(() => {});
  }, []);

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!data) return <LoadingState />;

  const { team, reps, risks, recent_calls, top_plays, org } = data;
  const struggling = reps[reps.length - 1];
  const leader = reps[0];

  if (team.calls_analyzed === 0) {
    return (
      <div className="page" data-status="COMMAND CENTRE" style={{ maxWidth: 820 }}>
        <header className="page-head">
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>
              {org.name}
            </div>
            <h1 className="display d2" style={{ margin: 0 }}>
              {firstName ? `Welcome, ${firstName}` : "Welcome to Salix"}
            </h1>
          </div>
        </header>
        <FirstRun teamSize={reps.length} />
      </div>
    );
  }

  return (
    <div className="page" data-status="COMMAND CENTRE">
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            {[org.name, org.cycle_label].filter(Boolean).join(" · ")}
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            {greeting(firstName)}
          </h1>
          <p
            className="lede"
            style={{ marginTop: 12, marginBottom: 0, maxWidth: "46ch" }}
          >
            {team.calls_analyzed} {team.calls_analyzed === 1 ? "call" : "calls"} · {team.hours_analyzed} hours
          </p>
        </div>
        <Link href="/upload" className="btn btn-primary" style={{ flexShrink: 0 }}>
          Analyse a call
          <IconArrow size={13} />
        </Link>
      </header>

      {/* --- The four numbers that matter --------------------------------- */}
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(198px, 1fr))",
          gap: 12,
          marginBottom: 30,
        }}
      >
        <Stat
          label="Win rate"
          count={team.win_rate}
          format={percent}
          hint={`${team.deals} deals in the cycle`}
          tone={scoreTone(team.win_rate * 140)}
        />
        <Stat
          label="Closed"
          count={team.closed_value}
          format={money}
          hint={`${money(team.pipeline_value)} still open`}
        />
        <Stat
          label="Average talk ratio"
          count={team.avg_talk_ratio}
          format={percent}
          hint={
            <span>
              Benchmark is 43%.{" "}
              <span style={{ color: team.avg_talk_ratio > 0.5 ? "var(--ember)" : "var(--sage)" }}>
                {team.avg_talk_ratio > 0.5 ? "The team talks too much." : "On target."}
              </span>
            </span>
          }
          tone={team.avg_talk_ratio > 0.55 ? "var(--ember)" : undefined}
        />
        <Stat
          label="Calls with a next step"
          count={team.next_step_rate}
          format={percent}
          hint="A call without one stalls by default"
          tone={team.next_step_rate < 0.6 ? "var(--rose)" : undefined}
        />
      </section>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.55fr) minmax(0, 1fr)",
          gap: 22,
          alignItems: "start",
        }}
        className="console-grid"
      >
        {/* --- Leaderboard ----------------------------------------------- */}
        <section className="panel-flush">
          <SectionHead
            title="The team"
            hint={`${leader?.rep.name.split(" ")[0]} sets the ceiling everyone else is measured against`}
          />
          <div className="scroll-x">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 34 }} />
                  <th>Rep</th>
                  <th style={{ width: 76 }}>Score</th>
                  <th style={{ width: 128 }}>Talk ratio</th>
                  <th style={{ width: 74 }}>Win rate</th>
                  <th style={{ width: 104 }}>Trend</th>
                </tr>
              </thead>
              <tbody>
                {reps.map((snapshot) => (
                  <tr key={snapshot.rep.id}>
                    <td>
                      <Avatar name={snapshot.rep.name} top={snapshot.rep.is_top_performer} />
                    </td>
                    <td>
                      <Link href={`/reps/${snapshot.rep.id}`} style={{ fontWeight: 500 }}>
                        {snapshot.rep.name}
                      </Link>
                      <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 1 }}>
                        {snapshot.calls} {snapshot.calls === 1 ? "call" : "calls"} · {snapshot.won}W / {snapshot.lost}L
                      </div>
                    </td>
                    <td>
                      <span
                        className="num stat-sm"
                        style={{ color: scoreTone(snapshot.overall_score) }}
                      >
                        {snapshot.overall_score.toFixed(0)}
                      </span>
                    </td>
                    <td>
                      <TalkRatioBar ratio={snapshot.talk_ratio} height={6} />
                      <div className="num" style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}>
                        {percent(snapshot.talk_ratio)}
                      </div>
                    </td>
                    <td className="num">{percent(snapshot.win_rate)}</td>
                    <td>
                      <Sparkline values={snapshot.trend} label={`${snapshot.rep.name} trend`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* --- Risk radar ------------------------------------------------- */}
        <section className="panel-flush">
          <SectionHead
            title="Needs attention"
            hint="Open deals with a named, evidenced cause"
          />
          {/* Capped and scrolled. The risk list is unbounded and would
              otherwise run far past the leaderboard beside it, leaving a
              column of dead space. */}
          <div
            style={{
              padding: "4px 16px 16px",
              maxHeight: 470,
              overflowY: "auto",
            }}
          >
            {risks.length === 0 && (
              <p style={{ fontSize: 13, color: "var(--ink-3)", margin: "10px 0" }}>
                Nothing flagged. Every open deal has a next step and no
                unresolved objections.
              </p>
            )}
            {risks.slice(0, 6).map((risk, index) => (
              <div
                key={`${risk.kind}-${index}`}
                style={{
                  paddingBottom: 12,
                  marginBottom: 12,
                  borderBottom:
                    index < Math.min(5, risks.length - 1) ? "1px solid var(--rule)" : "none",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
                  <IconWarning
                    size={12}
                    style={{
                      color:
                        risk.severity === "high" || risk.severity === "critical"
                          ? "var(--rose)"
                          : "var(--ember)",
                    }}
                  />
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{risk.title}</span>
                  <span className={`chip ${SEVERITY_CHIP[risk.severity]}`} style={{ marginLeft: "auto" }}>
                    {risk.severity}
                  </span>
                </div>
                <p style={{ fontSize: 12.5, color: "var(--ink-2)", margin: 0, lineHeight: 1.5 }}>
                  {risk.explanation}
                </p>
                {risk.first_seen_call_id && (
                  <Link
                    href={`/calls/${risk.first_seen_call_id}`}
                    className="eyebrow"
                    style={{ display: "inline-block", marginTop: 6, color: "var(--willow)" }}
                  >
                    Listen to the call →
                  </Link>
                )}
              </div>
            ))}
            <Link href="/deals" className="btn btn-sm" style={{ width: "100%", justifyContent: "center" }}>
              Every deal and its trajectory
            </Link>
          </div>
        </section>
      </div>

      {/* --- Coaching prompt --------------------------------------------- */}
      {struggling && leader && struggling.rep.id !== leader.rep.id && (
        <section
          className="panel"
          style={{
            marginTop: 22,
            padding: "20px 22px",
            display: "flex",
            gap: 20,
            alignItems: "center",
            flexWrap: "wrap",
            borderColor: "color-mix(in oklab, var(--willow) 40%, var(--rule))",
            background:
              "linear-gradient(100deg, var(--willow-wash), var(--paper-2) 62%)",
          }}
        >
          <ScoreRing score={struggling.overall_score} size={58} caption="score" />
          <div style={{ flex: 1, minWidth: 260 }}>
            <div className="eyebrow" style={{ marginBottom: 5 }}>
              Biggest opportunity
            </div>
            <p style={{ margin: 0, fontSize: 15, lineHeight: 1.5 }}>
              <strong>{struggling.rep.name}</strong> is{" "}
              <span className="num">
                {(leader.overall_score - struggling.overall_score).toFixed(0)}
              </span>{" "}
              points behind {leader.rep.name.split(" ")[0]}, and holds{" "}
              <span className="num">{percent(struggling.talk_ratio)}</span> of the
              conversation against a 43% benchmark. Salix has already found the
              plays that close the gap.
            </p>
          </div>
          <Link href={`/reps/${struggling.rep.id}`} className="btn btn-primary">
            Build the coaching plan
            <IconArrow size={13} />
          </Link>
        </section>
      )}

      {/* --- Recent calls + plays ---------------------------------------- */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.55fr) minmax(0, 1fr)",
          gap: 22,
          marginTop: 22,
          alignItems: "start",
        }}
        className="console-grid"
      >
        <section className="panel-flush">
          <SectionHead title="Recent calls" hint="Newest first" />
          <div className="scroll-x">
            <table className="table">
              <tbody>
                {recent_calls.map((call) => (
                  <tr key={call.id}>
                    <td style={{ width: 46 }}>
                      <ScoreRing score={call.score} size={34} thickness={3} />
                    </td>
                    <td>
                      <Link href={`/calls/${call.id}`} style={{ fontWeight: 500 }}>
                        {call.title}
                      </Link>
                      <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 2 }}>
                        {call.rep_name} · {shortDate(call.occurred_at)} ·{" "}
                        {clock(call.duration_ms)}
                      </div>
                      {call.headline && (
                        <div
                          style={{
                            fontSize: 12.5,
                            color: "var(--ink-2)",
                            marginTop: 4,
                            maxWidth: "52ch",
                          }}
                        >
                          {call.headline}
                        </div>
                      )}
                    </td>
                    <td style={{ width: 92 }}>
                      <span className={`chip ${outcomeChip(call.outcome)}`}>
                        {call.outcome}
                      </span>
                    </td>
                    <td style={{ width: 100 }}>
                      {call.talk_ratio_rep != null && (
                        <>
                          <TalkRatioBar ratio={call.talk_ratio_rep} height={5} />
                          <div className="num" style={{ fontSize: 10.5, color: "var(--ink-3)", marginTop: 3 }}>
                            {percent(call.talk_ratio_rep)}
                          </div>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel-flush">
          <SectionHead title="Winning DNA" hint="Mined from calls that closed" />
          <div style={{ padding: "2px 16px 16px" }}>
            {top_plays.length === 0 && (
              <p style={{ fontSize: 13, color: "var(--ink-3)" }}>
                No plays extracted yet. Analyse a won call to start the playbook.
              </p>
            )}
            {top_plays.map((play) => (
              <Link
                key={play.id}
                href={`/playbook/${play.id}`}
                style={{
                  display: "block",
                  padding: "11px 0",
                  borderBottom: "1px solid var(--rule)",
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span className="display" style={{ fontSize: 17 }}>
                    {play.name}
                  </span>
                  <span className="num" style={{ fontSize: 11, color: "var(--ink-4)", marginLeft: "auto" }}>
                    {play.usage_count}×
                  </span>
                </div>
                <p
                  style={{
                    margin: "3px 0 0",
                    fontSize: 12.5,
                    color: "var(--ink-3)",
                    lineHeight: 1.45,
                  }}
                >
                  {play.thesis}
                </p>
              </Link>
            ))}
            <Link
              href="/playbook"
              className="btn btn-sm"
              style={{ width: "100%", justifyContent: "center", marginTop: 14 }}
            >
              Open the playbook
            </Link>
          </div>
        </section>
      </div>

      <style>{`
        @media (max-width: 1100px) {
          .console-grid { grid-template-columns: minmax(0, 1fr) !important; }
        }
      `}</style>
    </div>
  );
}
