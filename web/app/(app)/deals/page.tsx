"use client";

/**
 * The risk radar.
 *
 * Sickest deal first. Each row shows the trajectory of buyer engagement across
 * the cycle and the named cause of every flag -- "pricing objection raised on
 * call two, never resolved" rather than a red dot.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { PageNote } from "@/components/Pop";
import { TrajectoryLine } from "@/components/charts";
import { IconArrow, IconWarning } from "@/components/icons";
import { ErrorState, LoadingState } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { SEVERITY_CHIP, money, outcomeChip, scoreTone, shortDate } from "@/lib/format";
import type { DealWithTrajectory } from "@/lib/types";

export default function DealsPage() {
  const [deals, setDeals] = useState<DealWithTrajectory[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [openOnly, setOpenOnly] = useState(true);

  useEffect(() => {
    api
      .deals()
      .then(setDeals)
      .catch((e: ApiError) => setError(e));
  }, []);

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!deals) return <LoadingState />;

  const visible = openOnly
    ? deals.filter((d) => d.deal.outcome === "open")
    : deals;
  const atRisk = deals.filter(
    (d) => d.deal.outcome === "open" && d.trajectory.risks.length > 0,
  );
  const exposed = atRisk.reduce((sum, d) => sum + d.deal.value, 0);

  return (
    <div className="page" data-status="DEALS AT RISK">
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            {atRisk.length} open deals carry a flag · {money(exposed)} exposed
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            What is slipping, and why
          </h1>
          <PageNote>
            Every flag below is derived by rule from what was actually said, so
            it survives being questioned in a pipeline review.
          </PageNote>
        </div>
        <button
          className="btn"
          onClick={() => setOpenOnly((value) => !value)}
        >
          {openOnly ? "Show closed too" : "Open deals only"}
        </button>
      </header>

      <div style={{ display: "grid", gap: 16 }}>
        {visible.map(({ deal, owner_name, trajectory }) => (
          <article key={deal.id} className="panel" style={{ padding: "19px 21px" }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) 260px",
                gap: 24,
                alignItems: "start",
              }}
              className="deal-grid"
            >
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 9,
                    marginBottom: 6,
                    flexWrap: "wrap",
                  }}
                >
                  <h2 className="display" style={{ fontSize: 23, margin: 0 }}>
                    {deal.account}
                  </h2>
                  <span className={`chip ${outcomeChip(deal.outcome)}`}>
                    {deal.stage.replace("_", " ")}
                  </span>
                  <span className="num" style={{ fontSize: 13, color: "var(--ink-3)" }}>
                    {money(deal.value)}
                  </span>
                </div>

                <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginBottom: 12 }}>
                  {owner_name} · opened {shortDate(deal.opened_at)} ·{" "}
                  {deal.contacts.length} contact
                  {deal.contacts.length === 1 ? "" : "s"}
                </div>

                <p
                  style={{
                    fontSize: 14.5,
                    margin: "0 0 14px",
                    color:
                      trajectory.health < 45 ? "var(--rose)" : "var(--ink)",
                  }}
                >
                  {trajectory.verdict}
                </p>

                {trajectory.risks.map((risk, index) => (
                  <div
                    key={index}
                    style={{
                      display: "flex",
                      gap: 9,
                      alignItems: "flex-start",
                      padding: "9px 0",
                      borderTop: "1px solid var(--rule)",
                    }}
                  >
                    <IconWarning
                      size={12}
                      style={{
                        marginTop: 3,
                        flexShrink: 0,
                        color:
                          risk.severity === "high" || risk.severity === "critical"
                            ? "var(--rose)"
                            : "var(--ember)",
                      }}
                    />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 13, fontWeight: 500 }}>
                          {risk.title.replace(`${deal.account}: `, "")}
                        </span>
                        <span className={`chip ${SEVERITY_CHIP[risk.severity]}`}>
                          {risk.severity}
                        </span>
                        {risk.age_days > 0 && (
                          <span className="num" style={{ fontSize: 11, color: "var(--ink-4)" }}>
                            {risk.age_days}d old
                          </span>
                        )}
                      </div>
                      <p
                        style={{
                          fontSize: 12.8,
                          color: "var(--ink-2)",
                          margin: "3px 0 0",
                          lineHeight: 1.55,
                        }}
                      >
                        {risk.explanation}
                      </p>
                      {risk.first_seen_call_id && (
                        <Link
                          href={`/calls/${risk.first_seen_call_id}`}
                          className="eyebrow"
                          style={{ color: "var(--willow)", display: "inline-block", marginTop: 5 }}
                        >
                          Hear where it started →
                        </Link>
                      )}
                    </div>
                  </div>
                ))}

                {trajectory.risks.length === 0 && (
                  <p style={{ fontSize: 13, color: "var(--sage)", margin: 0 }}>
                    No flags. Objections resolved, next step in place.
                  </p>
                )}
              </div>

              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                    marginBottom: 4,
                  }}
                >
                  <span className="eyebrow">Health</span>
                  <span
                    className="num stat-sm"
                    style={{ color: scoreTone(trajectory.health) }}
                  >
                    {Math.round(trajectory.health)}
                  </span>
                </div>
                <div className="meter" style={{ marginBottom: 14 }}>
                  <i
                    style={{
                      width: `${trajectory.health}%`,
                      background: scoreTone(trajectory.health),
                    }}
                  />
                </div>

                <div className="eyebrow" style={{ marginBottom: 4 }}>
                  Trajectory
                </div>
                <TrajectoryLine points={trajectory.points} width={260} height={78} />

                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginTop: 6,
                    fontSize: 11,
                    color: "var(--ink-3)",
                  }}
                >
                  <span className="eyebrow">
                    {trajectory.points.length} call
                    {trajectory.points.length === 1 ? "" : "s"}
                  </span>
                  <span
                    className="num"
                    style={{
                      color:
                        trajectory.momentum >= 0 ? "var(--sage)" : "var(--rose)",
                    }}
                  >
                    momentum {trajectory.momentum >= 0 ? "+" : ""}
                    {trajectory.momentum.toFixed(2)}
                  </span>
                </div>

                <div
                  style={{
                    display: "flex",
                    gap: 12,
                    marginTop: 10,
                    paddingTop: 10,
                    borderTop: "1px solid var(--rule)",
                  }}
                >
                  <LegendDash color="var(--willow)" label="call score" />
                  <LegendDash color="var(--buyer)" label="engagement" dashed />
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>

      {visible.length === 0 && (
        <div className="panel" style={{ padding: 34, textAlign: "center", color: "var(--ink-3)" }}>
          No deals to show.
        </div>
      )}

      <style>{`
        @media (max-width: 860px) {
          .deal-grid { grid-template-columns: minmax(0, 1fr) !important; }
        }
      `}</style>
    </div>
  );
}

function LegendDash({
  color,
  label,
  dashed,
}: {
  color: string;
  label: string;
  dashed?: boolean;
}) {
  return (
    <span className="eyebrow" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <i
        style={{
          width: 12,
          height: 0,
          borderTop: `2px ${dashed ? "dashed" : "solid"} ${color}`,
        }}
      />
      {label}
    </span>
  );
}
