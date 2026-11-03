"use client";

/**
 * The end-of-cycle report.
 *
 * Laid out as a document rather than a dashboard, because it is meant to be
 * read start to finish and forwarded. The print stylesheet drops the chrome so
 * it comes out clean on paper.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { Sparkline, TalkRatioBar } from "@/components/charts";
import { IconArrow, IconWarning } from "@/components/icons";
import { ErrorState, LoadingState } from "@/components/ui";
import { WorkingScene } from "@/components/Working";
import { popToast } from "@/components/Pop";
import { ApiError, api } from "@/lib/api";
import {
  AXIS_LABELS,
  AXIS_ORDER,
  SEVERITY_CHIP,
  longDate,
  money,
  percent,
  scoreTone,
} from "@/lib/format";
import type { CycleReport, DealCalibration } from "@/lib/types";

export default function ReportPage() {
  const [report, setReport] = useState<CycleReport | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    api
      .latestReport()
      .then(setReport)
      .catch((e: ApiError) => setError(e));
  }, []);

  async function generate() {
    setGenerating(true);
    try {
      setReport(await api.generateReport());
      popToast("Your cycle report is ready");
    } catch {
      // A failed attempt must never take away a report that is already on screen.
      popToast(report ? "Could not regenerate. Your current report is still here." : "The report could not be written. Try again.", "bad");
    } finally {
      setGenerating(false);
    }
  }

  const writing = generating && (
    <div style={{ marginBottom: 22 }}>
      <WorkingScene
        title="Writing the cycle report"
        steps={[
          "Gathering every analysed call in the cycle",
          "Computing the team's numbers",
          "Linking win-rate lift to the plays that were run",
          "Collecting the deals at risk",
          "Writing the story around all of it",
        ]}
      />
    </div>
  );

  if (error) return <ErrorState message={error.detail} status={error.status} />;

  if (!report) {
    return (
      <div data-status="CYCLE REPORT" className="page" style={{ maxWidth: 760 }}>
        <header className="page-head">
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>
              Cycle report
            </div>
            <h1 className="display d2" style={{ margin: 0 }}>
              Nothing generated yet
            </h1>
          </div>
        </header>
        <div className="panel" style={{ padding: 30 }}>
          <p className="prose-body" style={{ marginTop: 0 }}>
            Salix will aggregate every analysed call in the cycle, compute the
            team's numbers, attribute win-rate lift to the plays that were run,
            collect the deals at risk, and write the narrative around all of it.
          </p>
          {writing || (
            <button className="btn btn-primary" onClick={generate}>
              Generate the cycle report
              <IconArrow size={13} />
            </button>
          )}
        </div>
      </div>
    );
  }

  const { team } = report;

  return (
    <div data-status="CYCLE REPORT" className="page" style={{ maxWidth: 980, marginInline: "auto" }}>
      <CalibrationPanel />
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            {report.cycle_label} · {report.period_start} to {report.period_end}
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            Cycle report
          </h1>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 9 }}>
          <button className="btn" onClick={() => window.print()}>
            Print
          </button>
          <button className="btn" onClick={generate} disabled={generating}>
            {generating ? "Regenerating…" : "Regenerate"}
          </button>
        </div>
      </header>
      {writing}

      <p
        className="display d3"
        style={{
          margin: "0 0 30px",
          maxWidth: "26ch",
          borderLeft: "2px solid var(--willow)",
          paddingLeft: 20,
        }}
      >
        {report.headline}
      </p>

      {/* --- Numbers ------------------------------------------------------ */}
      <section
        className="report-numbers"
        style={{
          display: "grid",
          gap: 1,
          background: "var(--rule)",
          border: "1px solid var(--rule)",
          borderRadius: "var(--r-lg)",
          overflow: "hidden",
          marginBottom: 34,
        }}
      >
        <Cell label="Calls" value={String(team.calls_analyzed)} sub={`${team.hours_analyzed}h`} />
        <Cell label="Win rate" value={percent(team.win_rate)} sub={`${team.deals} deals`} />
        <Cell label="Closed" value={money(team.closed_value)} sub={`${money(team.pipeline_value)} open`} />
        <Cell
          label="Talk ratio"
          value={percent(team.avg_talk_ratio)}
          sub="43% benchmark"
          tone={team.avg_talk_ratio > 0.55 ? "var(--ember)" : undefined}
        />
        <Cell
          label="MEDDIC"
          value={percent(team.avg_meddic_coverage)}
          sub="qualification"
        />
        <Cell
          label="Next steps"
          value={percent(team.next_step_rate)}
          sub="of calls"
          tone={team.next_step_rate < 0.6 ? "var(--rose)" : undefined}
        />
      </section>

      {/* --- Narrative ---------------------------------------------------- */}
      <section style={{ marginBottom: 38 }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          The quarter
        </div>
        <div className="prose-body" style={{ fontSize: 15.5, maxWidth: "62ch" }}>
          {report.narrative.split(/\n\n+/).map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
          ))}
        </div>
      </section>

      {/* --- Findings ----------------------------------------------------- */}
      {report.findings.length > 0 && (
        <section style={{ marginBottom: 38 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            What the calls say
          </div>
          {report.findings.map((finding, index) => (
            <div
              key={index}
              style={{
                display: "grid",
                gridTemplateColumns: "30px 1fr",
                gap: 14,
                paddingBottom: 18,
                marginBottom: 18,
                borderBottom:
                  index < report.findings.length - 1 ? "1px solid var(--rule)" : "none",
              }}
            >
              <span className="num" style={{ fontSize: 20, color: "var(--ink-4)" }}>
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <h3 className="display" style={{ fontSize: 20, margin: "0 0 7px" }}>
                  {finding.title}
                </h3>
                <p className="prose-body" style={{ margin: 0, fontSize: 14 }}>
                  {finding.detail}
                </p>
                {finding.impact && (
                  <p
                    style={{
                      margin: "9px 0 0",
                      fontSize: 13,
                      color: "var(--willow)",
                      fontWeight: 500,
                    }}
                  >
                    {finding.impact}
                  </p>
                )}
              </div>
            </div>
          ))}
        </section>
      )}

      {/* --- The team ----------------------------------------------------- */}
      <section style={{ marginBottom: 38 }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          The team
        </div>
        <div className="panel-flush scroll-x">
          <table className="table">
            <thead>
              <tr>
                <th>Rep</th>
                <th style={{ width: 62 }}>Score</th>
                <th style={{ width: 92 }}>Win rate</th>
                <th style={{ width: 60 }}>Calls</th>
                <th>Strongest</th>
                <th>Watch</th>
                <th style={{ width: 58 }}>Trend</th>
              </tr>
            </thead>
            <tbody>
              {report.reps.map((row) => (
                <tr key={row.rep_id}>
                  <td>
                    <Link href={`/reps/${row.rep_id}`} style={{ fontWeight: 500 }}>
                      {row.name}
                    </Link>
                  </td>
                  <td>
                    <span className="num" style={{ color: scoreTone(row.overall_score) }}>
                      {row.overall_score.toFixed(0)}
                    </span>
                  </td>
                  <td className="num">
                    {percent(row.win_rate)}
                    <span style={{ color: "var(--ink-4)", marginLeft: 5, fontSize: 11 }}>
                      {row.won}W/{row.lost}L
                    </span>
                  </td>
                  <td className="num">{row.calls}</td>
                  <td style={{ fontSize: 12.5, color: "var(--sage)" }}>
                    {AXIS_LABELS[row.standout as keyof typeof AXIS_LABELS] ?? row.standout}
                  </td>
                  <td style={{ fontSize: 12.5, color: "var(--ember)" }}>
                    {AXIS_LABELS[row.watch_item as keyof typeof AXIS_LABELS] ?? row.watch_item}
                  </td>
                  <td>
                    <span
                      className="num"
                      style={{
                        fontSize: 12,
                        color: row.trend >= 0 ? "var(--sage)" : "var(--rose)",
                      }}
                    >
                      {row.trend >= 0 ? "+" : ""}
                      {row.trend.toFixed(1)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* --- Risks -------------------------------------------------------- */}
      {report.risks.length > 0 && (
        <section style={{ marginBottom: 38 }}>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            Deals at risk
          </div>
          {report.risks.map((risk, index) => (
            <div
              key={index}
              style={{
                display: "flex",
                gap: 10,
                alignItems: "flex-start",
                padding: "11px 0",
                borderBottom: "1px solid var(--rule)",
              }}
            >
              <IconWarning
                size={13}
                style={{
                  marginTop: 3,
                  flexShrink: 0,
                  color: risk.severity === "high" ? "var(--rose)" : "var(--ember)",
                }}
              />
              <div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontSize: 13.5, fontWeight: 500 }}>{risk.title}</span>
                  <span className={`chip ${SEVERITY_CHIP[risk.severity]}`}>
                    {risk.severity}
                  </span>
                </div>
                <p style={{ margin: "3px 0 0", fontSize: 13, color: "var(--ink-2)" }}>
                  {risk.explanation}
                </p>
              </div>
            </div>
          ))}
        </section>
      )}

      {/* --- Recommendations ---------------------------------------------- */}
      {report.recommendations.length > 0 && (
        <section>
          <div className="eyebrow" style={{ marginBottom: 14 }}>
            What to change
          </div>
          {report.recommendations
            .slice()
            .sort((a, b) => a.priority - b.priority)
            .map((recommendation, index) => (
              <div
                key={index}
                className="panel"
                style={{ padding: "16px 19px", marginBottom: 12 }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 9,
                    marginBottom: 7,
                  }}
                >
                  <span className="chip chip-willow">P{recommendation.priority}</span>
                  <h3 style={{ fontSize: 15, margin: 0, fontWeight: 550 }}>
                    {recommendation.title}
                  </h3>
                  {recommendation.owner && (
                    <span
                      className="eyebrow"
                      style={{ marginLeft: "auto", color: "var(--ink-3)" }}
                    >
                      {recommendation.owner}
                    </span>
                  )}
                </div>
                <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.6 }}>
                  {recommendation.detail}
                </p>
                {recommendation.expected_lift && (
                  <p
                    style={{
                      margin: "8px 0 0",
                      fontSize: 12.5,
                      color: "var(--willow)",
                    }}
                  >
                    Expected: {recommendation.expected_lift}
                  </p>
                )}
              </div>
            ))}
        </section>
      )}

      <footer
        style={{
          marginTop: 44,
          paddingTop: 18,
          borderTop: "1px solid var(--rule)",
          fontSize: 11.5,
          color: "var(--ink-4)",
        }}
      >
        Generated by Salix on {longDate(report.generated_at)} from{" "}
        {team.calls_analyzed} analysed calls. Every figure is computed from
        transcript timestamps, not estimated.
      </footer>
    </div>
  );
}

function Cell({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: string;
}) {
  return (
    <div style={{ background: "var(--paper-2)", padding: "15px 16px" }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>
        {label}
      </div>
      <div className="num stat-sm" style={{ color: tone ?? "var(--ink)" }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 4 }}>{sub}</div>
      )}
    </div>
  );
}

/**
 * Whether the deal score predicts this team's real outcomes.
 *
 * Its weights were chosen by judgement, and the threshold for coaching rests on them,
 * so the evidence for or against sits where a manager can see it.
 */
function CalibrationPanel() {
  const [data, setData] = useState<DealCalibration | null>(null);

  useEffect(() => {
    api.dealCalibration().then(setData).catch(() => setData(null));
  }, []);

  if (!data) return null;

  return (
    <section className="panel no-print" style={{ padding: "14px 17px", marginBottom: 22, fontSize: 13 }}>
      <div className="eyebrow" style={{ marginBottom: 7 }}>
        Is the deal score right for your team?
      </div>
      <p style={{ margin: 0, color: data.reliable ? "var(--ink)" : "var(--ink-2)" }}>{data.verdict}</p>
      {data.separation != null && (
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 9, fontSize: 12, color: "var(--ink-3)" }}>
          <span className="num">{Math.round(data.separation * 100)}% separation</span>
          {data.bands
            .filter((band) => band.calls > 0)
            .map((band) => (
              <span key={band.band} className="num">
                {band.band}: {band.won}/{band.calls} won
              </span>
            ))}
        </div>
      )}
    </section>
  );
}
