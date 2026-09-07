"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { IconArrow, IconQuote } from "@/components/icons";
import { ErrorState, LoadingState, SectionHead } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { outcomeChip, percent, shortDate } from "@/lib/format";
import type { PlayDetail } from "@/lib/types";

export default function PlayPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [play, setPlay] = useState<PlayDetail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    api
      .play(id)
      .then(setPlay)
      .catch(setError);
  }, [id]);

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!play) return <LoadingState />;

  return (
    <div data-status="PLAY" className="page" style={{ maxWidth: 980 }}>
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            <Link href="/playbook" style={{ color: "var(--ink-3)" }}>
              Playbook
            </Link>
            {" / "}
            {play.kind.replace("_", " ")}
          </div>
          <h1 className="display d1" style={{ margin: 0, fontSize: "clamp(2.6rem, 6vw, 4.4rem)" }}>
            {play.name}
          </h1>
        </div>
      </header>

      <p className="lede" style={{ marginTop: 0, marginBottom: 30, fontSize: "1.28rem" }}>
        {play.thesis}
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 12,
          marginBottom: 30,
        }}
      >
        <MiniStat label="Times run" value={String(play.usage_count)} />
        <MiniStat
          label="Won with it"
          value={String(play.instances.filter((i) => i.outcome === "won").length)}
        />
        {play.win_rate_with != null && (
          <MiniStat label="Win rate when run" value={percent(play.win_rate_with)} />
        )}
        {play.win_rate_lift != null && (
          <MiniStat
            label="Lift vs baseline"
            value={`${play.win_rate_lift > 0 ? "+" : ""}${Math.round(play.win_rate_lift * 100)}pts`}
            tone="var(--willow)"
          />
        )}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
          gap: 22,
          alignItems: "start",
        }}
        className="play-grid"
      >
        <section className="panel-flush">
          <SectionHead title="How it runs" hint={play.when_to_use} />
          <div style={{ padding: "16px 19px 20px" }}>
            {play.beats.map((beat, index) => (
              <div
                key={index}
                style={{
                  display: "flex",
                  gap: 13,
                  paddingBottom: 15,
                  marginBottom: 15,
                  borderBottom:
                    index < play.beats.length - 1 ? "1px solid var(--rule)" : "none",
                }}
              >
                <span
                  className="num"
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: 999,
                    display: "grid",
                    placeItems: "center",
                    fontSize: 10.5,
                    flexShrink: 0,
                    background: "var(--willow-wash)",
                    color: "var(--willow)",
                    fontWeight: 500,
                  }}
                >
                  {index + 1}
                </span>
                <span style={{ fontSize: 14, lineHeight: 1.55 }}>{beat}</span>
              </div>
            ))}

            {play.template && (
              <div
                style={{
                  marginTop: 4,
                  padding: "14px 16px",
                  borderRadius: "var(--r)",
                  background: "var(--paper)",
                  border: "1px solid var(--rule)",
                }}
              >
                <div className="eyebrow" style={{ marginBottom: 8 }}>
                  Say it like this
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: 14,
                    lineHeight: 1.65,
                    color: "var(--ink-2)",
                  }}
                >
                  {play.template}
                </p>
              </div>
            )}
          </div>
        </section>

        <section className="panel-flush">
          <SectionHead
            title="Where it worked"
            hint={`${play.instances.length} recorded uses`}
          />
          <div style={{ padding: "6px 19px 18px" }}>
            {play.instances.map((instance) => (
              <div
                key={instance.id}
                style={{ padding: "14px 0", borderBottom: "1px solid var(--rule)" }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 8,
                    flexWrap: "wrap",
                  }}
                >
                  <span style={{ fontSize: 13, fontWeight: 500 }}>
                    {instance.rep_name}
                  </span>
                  <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
                    {instance.account}
                  </span>
                  <span className={`chip ${outcomeChip(instance.outcome)}`}>
                    {instance.outcome}
                  </span>
                  <span
                    className="num"
                    style={{ marginLeft: "auto", fontSize: 11, color: "var(--ink-4)" }}
                  >
                    {shortDate(instance.occurred_at)}
                  </span>
                </div>

                {instance.quote && (
                  <p className="quote" style={{ fontSize: 13.2, margin: "0 0 9px", lineHeight: 1.62 }}>
                    <IconQuote
                      size={11}
                      style={{ color: "var(--ink-4)", marginRight: 5, verticalAlign: -1 }}
                    />
                    {instance.quote}
                  </p>
                )}

                <Link
                  href={`/calls/${instance.call_id}`}
                  className="eyebrow"
                  style={{ color: "var(--willow)", display: "inline-flex", alignItems: "center", gap: 5 }}
                >
                  {instance.call_title || "Open the call"}
                  <IconArrow size={11} />
                </Link>
              </div>
            ))}
          </div>
        </section>
      </div>

      <style>{`
        @media (max-width: 900px) {
          .play-grid { grid-template-columns: minmax(0, 1fr) !important; }
        }
      `}</style>
    </div>
  );
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="panel" style={{ padding: "13px 15px" }}>
      <div className="eyebrow" style={{ marginBottom: 7 }}>
        {label}
      </div>
      <div className="num stat-sm" style={{ color: tone ?? "var(--ink)" }}>
        {value}
      </div>
    </div>
  );
}
