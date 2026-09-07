"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ScoreRing, TalkRatioBar } from "@/components/charts";
import { IconArrow } from "@/components/icons";
import { ErrorState, LoadingState } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { clock, cx, outcomeChip, percent, shortDate } from "@/lib/format";
import type { CallSummary, RepSnapshot } from "@/lib/types";

type Sort = "recent" | "score" | "talk";

export default function CallsPage() {
  const [calls, setCalls] = useState<CallSummary[] | null>(null);
  const [reps, setReps] = useState<RepSnapshot[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [repFilter, setRepFilter] = useState<string>("");
  const [outcomeFilter, setOutcomeFilter] = useState<string>("");
  const [sort, setSort] = useState<Sort>("recent");

  useEffect(() => {
    Promise.all([api.calls({ limit: 200 }), api.reps()])
      .then(([c, r]) => {
        setCalls(c);
        setReps(r);
      })
      .catch((e: ApiError) => setError(e));
  }, []);

  const visible = useMemo(() => {
    if (!calls) return [];
    const filtered = calls.filter(
      (c) =>
        (!repFilter || c.call.rep_id === repFilter) &&
        (!outcomeFilter || c.call.outcome === outcomeFilter),
    );
    const sorted = [...filtered];
    if (sort === "score") sorted.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    if (sort === "talk")
      sorted.sort((a, b) => (b.talk_ratio_rep ?? 0) - (a.talk_ratio_rep ?? 0));
    return sorted;
  }, [calls, repFilter, outcomeFilter, sort]);

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!calls) return <LoadingState />;

  return (
    <div className="page" data-status="CALLS">
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            {calls.length} analysed conversations
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            Every call, measured
          </h1>
        </div>
        <Link href="/upload" className="btn btn-primary">
          Analyse a call
          <IconArrow size={13} />
        </Link>
      </header>

      <div
        style={{
          display: "flex",
          gap: 9,
          marginBottom: 18,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <FilterGroup
          label="Rep"
          value={repFilter}
          onChange={setRepFilter}
          options={[
            { value: "", label: "Everyone" },
            ...reps.map((r) => ({ value: r.rep.id, label: r.rep.name.split(" ")[0] })),
          ]}
        />
        <FilterGroup
          label="Outcome"
          value={outcomeFilter}
          onChange={setOutcomeFilter}
          options={[
            { value: "", label: "All" },
            { value: "won", label: "Won" },
            { value: "lost", label: "Lost" },
            { value: "open", label: "Open" },
          ]}
        />
        <FilterGroup
          label="Sort"
          value={sort}
          onChange={(v) => setSort(v as Sort)}
          options={[
            { value: "recent", label: "Recent" },
            { value: "score", label: "Score" },
            { value: "talk", label: "Talk ratio" },
          ]}
        />
        <span className="eyebrow" style={{ marginLeft: "auto" }}>
          {visible.length} shown
        </span>
      </div>

      <section className="panel-flush">
        <div className="scroll-x">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 54 }}>Score</th>
                <th>Call</th>
                <th style={{ width: 92 }}>Outcome</th>
                <th style={{ width: 132 }}>Talk ratio</th>
                <th style={{ width: 108 }}>Monologue</th>
                <th style={{ width: 84 }}>Open</th>
              </tr>
            </thead>
            <tbody>
              {visible.map(({ call, ...summary }) => (
                <tr key={call.id}>
                  <td>
                    <ScoreRing score={summary.score} size={36} thickness={3} />
                  </td>
                  <td>
                    <Link href={`/calls/${call.id}`} style={{ fontWeight: 500 }}>
                      {call.title}
                    </Link>
                    <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 2 }}>
                      {summary.rep_name} · {shortDate(call.occurred_at)} ·{" "}
                      {clock(call.duration_ms)}
                    </div>
                    {summary.headline && (
                      <div
                        style={{
                          fontSize: 12.5,
                          color: "var(--ink-2)",
                          marginTop: 4,
                          maxWidth: "54ch",
                        }}
                      >
                        {summary.headline}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className={`chip ${outcomeChip(call.outcome)}`}>
                      {call.outcome}
                    </span>
                  </td>
                  <td>
                    {summary.talk_ratio_rep != null && (
                      <>
                        <TalkRatioBar ratio={summary.talk_ratio_rep} height={6} />
                        <div
                          className="num"
                          style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 4 }}
                        >
                          {percent(summary.talk_ratio_rep)}
                        </div>
                      </>
                    )}
                  </td>
                  <td
                    className="num"
                    style={{
                      color:
                        (summary.longest_monologue_ms ?? 0) > 150_000
                          ? "var(--rose)"
                          : "var(--ink-2)",
                    }}
                  >
                    {summary.longest_monologue_ms != null
                      ? clock(summary.longest_monologue_ms)
                      : "--"}
                  </td>
                  <td>
                    {summary.open_objections > 0 ? (
                      <span className="chip chip-ember">
                        {summary.open_objections} objection
                        {summary.open_objections > 1 ? "s" : ""}
                      </span>
                    ) : (
                      <span style={{ color: "var(--ink-4)", fontSize: 12 }}>--</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {visible.length === 0 && (
          <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>
            No calls match these filters.
          </div>
        )}
      </section>
    </div>
  );
}

function FilterGroup({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    // `minWidth: 0` lets the group shrink inside the wrapping filter bar; with
    // the default `auto` the rep strip stays at its full width and takes the
    // page sideways on a phone.
    <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0, maxWidth: "100%" }}>
      <span className="eyebrow">{label}</span>
      <div
        style={{
          display: "flex",
          // Six reps do not fit on one line at 375px, so the segmented control
          // tiles onto a second row instead of overflowing.
          flexWrap: "wrap",
          minWidth: 0,
          border: "1px solid var(--rule)",
          borderRadius: "var(--r)",
          overflow: "hidden",
        }}
      >
        {options.map((option) => (
          <button
            key={option.value}
            onClick={() => onChange(option.value)}
            className={cx("btn-sm")}
            style={{
              border: "none",
              borderRadius: 0,
              padding: "0 10px",
              height: 28,
              fontSize: 12,
              cursor: "pointer",
              fontFamily: "inherit",
              background: value === option.value ? "var(--paper-3)" : "var(--paper-2)",
              color: value === option.value ? "var(--ink)" : "var(--ink-3)",
              fontWeight: value === option.value ? 500 : 400,
            }}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
