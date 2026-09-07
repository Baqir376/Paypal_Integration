"use client";

/**
 * The playbook.
 *
 * Presented as a library of named moves rather than a feed of tips, because
 * that is what makes them repeatable. Each card carries who runs it, how often,
 * and the measured win-rate difference against the team's own baseline.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { IconArrow, IconSpark } from "@/components/icons";
import { ErrorState, LoadingState } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { percent } from "@/lib/format";
import type { PlayKind, PlayWithInstance } from "@/lib/types";

const KIND_LABEL: Record<PlayKind, string> = {
  story_arc: "Story",
  analogy: "Analogy",
  proof_point: "Proof",
  reframe: "Reframe",
  question_sequence: "Question sequence",
  objection_turn: "Objection turn",
};

export default function PlaybookPage() {
  const [plays, setPlays] = useState<PlayWithInstance[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    api
      .plays()
      .then(setPlays)
      .catch((e: ApiError) => setError(e));
  }, []);

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!plays) return <LoadingState />;

  return (
    <div className="page" data-status="PLAYBOOK">
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            Winning DNA · {plays.length} plays
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            What your best people
            <br />
            actually do
          </h1>
          <p className="lede" style={{ marginTop: 14, marginBottom: 0 }}>
            Not advice. These are narrative moves lifted out of calls that
            closed, with the transcript to prove each one and the names of the
            people who ran them.
          </p>
        </div>
      </header>

      {plays.length === 0 && (
        <div className="panel" style={{ padding: 34, textAlign: "center" }}>
          <p className="prose-body" style={{ margin: "0 auto" }}>
            The playbook is empty. Analyse a won call and Salix will start
            extracting the moves that made it work.
          </p>
          <Link href="/upload" className="btn btn-primary" style={{ marginTop: 16 }}>
            Analyse a call
          </Link>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))",
          gap: 16,
        }}
      >
        {plays.map((play, index) => (
          <Link
            key={play.id}
            href={`/playbook/${play.id}`}
            className="panel rise"
            style={{
              padding: "20px 21px 18px",
              display: "flex",
              flexDirection: "column",
              animationDelay: `${Math.min(index * 45, 300)}ms`,
              transition: "border-color 160ms ease, transform 160ms ease",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 12,
              }}
            >
              <span className="chip chip-neutral">{KIND_LABEL[play.kind]}</span>
              <span className="num" style={{ marginLeft: "auto", fontSize: 11, color: "var(--ink-4)" }}>
                run {play.usage_count}×
              </span>
            </div>

            <h2
              className="display"
              style={{ fontSize: 26, margin: "0 0 10px", lineHeight: 1.08 }}
            >
              {play.name}
            </h2>

            <p
              style={{
                fontSize: 13.5,
                color: "var(--ink-2)",
                margin: "0 0 14px",
                lineHeight: 1.55,
                flex: 1,
              }}
            >
              {play.thesis}
            </p>

            {play.win_rate_lift != null && play.win_rate_with != null && (
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: 9,
                  padding: "9px 11px",
                  borderRadius: "var(--r)",
                  background: "var(--willow-wash)",
                  marginBottom: 12,
                }}
              >
                <span className="num" style={{ fontSize: 19, color: "var(--willow)", fontWeight: 500 }}>
                  {play.win_rate_lift > 0 ? "+" : ""}
                  {Math.round(play.win_rate_lift * 100)}
                  <span style={{ fontSize: 12 }}>pts</span>
                </span>
                <span style={{ fontSize: 11.5, color: "var(--ink-3)", lineHeight: 1.35 }}>
                  win rate when run
                  <br />
                  {percent(play.win_rate_with)} vs {percent(play.win_rate_without ?? 0)}
                </span>
              </div>
            )}

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                paddingTop: 12,
                borderTop: "1px solid var(--rule)",
              }}
            >
              <IconSpark size={12} style={{ color: "var(--ink-4)" }} />
              <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
                {play.used_by?.slice(0, 2).join(", ") || "unattributed"}
                {(play.used_by?.length ?? 0) > 2 && ` +${play.used_by!.length - 2}`}
              </span>
              <IconArrow size={12} style={{ marginLeft: "auto", color: "var(--ink-4)" }} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
