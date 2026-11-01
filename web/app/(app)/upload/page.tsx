"use client";

/**
 * Ingest, with the analysis graph running live.
 *
 * Watching the DAG light up stage by stage is the clearest possible statement
 * that there is a real multi-agent system behind the button, and it is the
 * most useful progress indicator we could give: each stage names the agent
 * doing the work and reports what it found.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { IconArrow, IconCheck, IconUpload, IconWarning } from "@/components/icons";
import { ErrorState } from "@/components/ui";
import { ApiError, api, subscribeToPipeline } from "@/lib/api";
import { cx } from "@/lib/format";
import type {
  BillingState,
  PipelineEvent,
  RepSnapshot,
  StageKey,
  StageStatus,
} from "@/lib/types";

/**
 * What the API will accept, mirrored from `ALLOWED_SUFFIXES` and
 * `MAX_UPLOAD_BYTES` in api/salix/routers/calls.py.
 *
 * The server is the authority and rejects the rest with 415 and 413. Checking
 * here as well is not redundant: without it the browser pushes the whole file
 * across the wire before being told no, and a mistaken drop of a two-gigabyte
 * video costs a long upload and an error at the end of it. The `accept`
 * attribute alone does not cover this -- it filters the file picker and has no
 * bearing at all on a file dropped onto the page.
 */
const ACCEPTED_SUFFIXES = [
  ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
  ".mp4", ".mov", ".webm", ".mkv", ".amr",
];
const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;

/** Null when the file is usable, otherwise the reason it is not. */
function rejectionReason(file: File): string | null {
  const dot = file.name.lastIndexOf(".");
  const suffix = dot === -1 ? "" : file.name.slice(dot).toLowerCase();
  if (!ACCEPTED_SUFFIXES.includes(suffix)) {
    return `${file.name} is not a recording Salix can read. Accepted formats: ${ACCEPTED_SUFFIXES.join(", ")}.`;
  }
  if (file.size === 0) {
    return `${file.name} is empty.`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `${file.name} is ${(file.size / 1e6).toFixed(0)} MB. The limit is ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB.`;
  }
  return null;
}

/** The graph, in the order the orchestrator walks it. */
const STAGES: { key: StageKey; label: string; agent: string }[] = [
  { key: "transcribe", label: "Transcribing", agent: "Transcriptionist" },
  { key: "diarize", label: "Separating speakers", agent: "Transcriptionist" },
  { key: "metrics", label: "Measuring conversation", agent: "Prosodist" },
  { key: "anatomy", label: "Reading call anatomy", agent: "Anatomist" },
  { key: "plays", label: "Extracting plays", agent: "Playwright" },
  { key: "embed", label: "Indexing moments", agent: "Playwright" },
  { key: "trajectory", label: "Updating deal trajectory", agent: "Analyst" },
  { key: "coach", label: "Writing the coaching plan", agent: "Coach" },
];

export default function UploadPage() {
  const router = useRouter();
  const [reps, setReps] = useState<RepSnapshot[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [callId, setCallId] = useState<string | null>(null);
  const [events, setEvents] = useState<Map<StageKey, PipelineEvent>>(new Map());
  const [failure, setFailure] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);
  const [salesperson, setSalesperson] = useState("");
  const [repId, setRepId] = useState<string | null>(null);
  const [billing, setBilling] = useState<BillingState | null>(null);
  /**
   * Whether real audio can actually be transcribed right now.
   *
   * This page promises six agents will transcribe the recording and separate
   * the speakers. With transcription on the offline twin that is not true:
   * the audio is stored and a stand-in conversation is analysed in its place.
   * The stand-in says so in its own first line, but only somebody who reads
   * the transcript finds out -- after uploading their call and watching seven
   * stages of what looks like real work.
   *
   * A promise the configuration cannot keep has to be withdrawn before the
   * upload, not confessed after it.
   */
  const [canTranscribe, setCanTranscribe] = useState<boolean | null>(null);
  const unsubscribe = useRef<(() => void) | null>(null);

  /** The one way a file is accepted, whether it was picked or dropped. */
  function chooseFile(candidate: File | null) {
    if (!candidate) {
      setFile(null);
      return;
    }
    const reason = rejectionReason(candidate);
    if (reason) {
      setFile(null);
      setFailure(reason);
      return;
    }
    setFailure(null);
    setFile(candidate);
  }

  useEffect(() => {
    api
      .reps()
      .then(setReps)
      .catch((e: ApiError) => setError(e));

    api
      .billing()
      .then(setBilling)
      .catch(() => setBilling(null));

    // Separate from the rep list: a failure here must not blank the page, it
    // must only leave the promise unqualified.
    api
      .health()
      .then((h) => setCanTranscribe(h.providers?.transcription !== "offline twin"))
      .catch(() => setCanTranscribe(null));
    return () => unsubscribe.current?.();
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;

    const form = new FormData(event.currentTarget);
    form.set("file", file);
    form.set("salesperson", salesperson);

    setSubmitting(true);
    setFailure(null);
    try {
      const response = await api.upload(form);
      setCallId(response.call_id);
      setRepId(response.rep_id);
      unsubscribe.current = subscribeToPipeline(
        response.call_id,
        (pipelineEvent) => {
          setEvents((current) => {
            const next = new Map(current);
            next.set(pipelineEvent.stage, pipelineEvent);
            return next;
          });
          // A failed stage is not the end of the graph, only of the run: the
          // pipeline finishes what it can and says so in its last event.
          if (pipelineEvent.stage === "done" && pipelineEvent.status === "failed") {
            setFailure(pipelineEvent.detail);
          }
        },
        () => setFinished(true),
      );
    } catch (e) {
      setFailure((e as ApiError).detail);
      setSubmitting(false);
      // Out of credits, or someone else took the last one: show what is true now.
      if ((e as ApiError).status === 402) api.billing().then(setBilling).catch(() => {});
    }
  }

  if (error && !reps.length) return <ErrorState message={error.detail} status={error.status} />;

  const done = events.get("done");
  const degraded = (done?.payload?.failed_stages as string[] | undefined) ?? [];
  const outOfCredits = !!billing?.enforced && billing.balance < billing.call_cost;
  const typed = salesperson.trim().replace(/(['’]s)?\s+call$/i, "").toLowerCase();
  const known = reps.some(
    ({ rep }) =>
      rep.name.toLowerCase() === typed ||
      (!typed.includes(" ") && rep.name.split(" ")[0].toLowerCase() === typed),
  );

  return (
    <div data-status="ANALYSE A CALL" className="page" style={{ maxWidth: 940 }}>
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            Ingest
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            Analyse a call
          </h1>
          <p className="lede" style={{ marginTop: 12, marginBottom: 0 }}>
            {canTranscribe === false
              ? "Six agents will measure the conversation, read its anatomy, and mine it for reusable moves — but not yours, in this configuration. See below."
              : "Drop a recording in and say whose call it is. English, Urdu or Roman Urdu is detected for you, and you get a score and a coaching plan back."}
          </p>
        </div>
      </header>

      {canTranscribe === false && (
        <div
          className="panel"
          style={{ padding: "16px 18px", marginBottom: 20, borderColor: "var(--rose)" }}
        >
          <div className="eyebrow" style={{ color: "var(--rose)", marginBottom: 8 }}>
            Real audio cannot be transcribed right now
          </div>
          <p className="prose-body" style={{ fontSize: 13.5, margin: "0 0 10px" }}>
            Your recording will be stored, but not listened to. Speech-to-text
            with speaker separation needs a provider that offers it, and the one
            configured here does not — so the pipeline below will run against a
            <em> stand-in conversation</em>, and everything it reports will be
            about that, not about your call.
          </p>
          <p className="prose-body" style={{ fontSize: 13.5, margin: 0 }}>
            Everything else is genuinely live. The Dojo, the coaching plans and
            the search all work on real inference — it is only transcription
            that is missing. Set <code className="num">DASHSCOPE_API_KEY</code>,
            or wire in another provider with diarization, and this notice goes
            away.
          </p>
        </div>
      )}

      {billing?.enforced && !callId && (
        <div
          className="panel"
          style={{
            padding: "12px 15px",
            marginBottom: 20,
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            borderColor: outOfCredits ? "var(--rose)" : "var(--rule)",
            fontSize: 13,
          }}
        >
          <span style={{ flex: 1, minWidth: 200 }}>
            {outOfCredits ? (
              "You are out of credits. Each recording uses one."
            ) : (
              <>
                <span className="num">{billing.balance}</span>{" "}
                {billing.balance === 1 ? "credit" : "credits"} left. This uses one,
                and it is returned if the analysis fails.
              </>
            )}
          </span>
          <Link href="/billing" className={outOfCredits ? "btn btn-primary btn-sm" : "btn btn-sm"}>
            Buy credits
          </Link>
        </div>
      )}

      {!callId ? (
        <form onSubmit={submit}>
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              // A dropped file never passed through `accept`, so it is
              // validated here like any other.
              chooseFile(e.dataTransfer.files?.[0] ?? null);
            }}
            className="panel"
            style={{
              display: "grid",
              placeItems: "center",
              padding: "46px 24px",
              marginBottom: 20,
              cursor: "pointer",
              borderStyle: "dashed",
              borderWidth: 1.5,
              borderColor: dragging ? "var(--willow)" : "var(--rule-strong)",
              background: dragging ? "var(--willow-wash)" : "var(--paper-2)",
              transition: "border-color 150ms ease, background 150ms ease",
            }}
          >
            <input
              type="file"
              name="file"
              accept={ACCEPTED_SUFFIXES.join(",")}
              hidden
              onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
            />
            <IconUpload size={26} style={{ color: "var(--ink-3)", marginBottom: 12 }} />
            {file ? (
              <>
                <div style={{ fontSize: 15, fontWeight: 500 }}>{file.name}</div>
                <div className="num" style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
                  {(file.size / 1e6).toFixed(1)} MB
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 15 }}>Drop a recording, or click to choose</div>
                <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 5 }}>
                  mp3, wav, m4a, mp4, webm · up to 200 MB
                </div>
              </>
            )}
          </label>

          <div style={{ marginBottom: 16 }}>
            <Field label="Salesperson">
              <input
                className="field"
                required
                list="team-names"
                maxLength={90}
                autoComplete="off"
                placeholder="Bilal's Call"
                value={salesperson}
                onChange={(e) => setSalesperson(e.target.value)}
              />
              <datalist id="team-names">
                {reps.map(({ rep }) => (
                  <option key={rep.id} value={rep.name} />
                ))}
              </datalist>
            </Field>
            {typed && !known && (
              <p style={{ fontSize: 12.5, color: "var(--ink-3)", margin: "7px 0 0" }}>
                New name: they will be added to your team.
              </p>
            )}
          </div>

          {/* Everything here has a sensible default. Outcome is the one worth
              giving: only won calls become evidence in colleagues' coaching. */}
          <details style={{ marginBottom: 20 }}>
            <summary style={{ fontSize: 13, color: "var(--ink-2)", cursor: "pointer" }}>
              More details (optional)
            </summary>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
                gap: 14,
                marginTop: 12,
              }}
            >
              <Field label="Call title">
                <input name="title" className="field" placeholder="Discovery with Northwind" />
              </Field>
              <Field label="Account">
                <input name="account" className="field" placeholder="Northwind Logistics" />
              </Field>
              <Field label="Outcome">
                <select name="outcome" className="field" defaultValue="open">
                  <option value="open">Still open</option>
                  <option value="won">Won</option>
                  <option value="lost">Lost</option>
                </select>
              </Field>
            </div>
          </details>

          {failure && (
            <div
              className="panel"
              style={{
                padding: "12px 15px",
                marginBottom: 16,
                borderColor: "var(--rose)",
                color: "var(--rose)",
                fontSize: 13,
              }}
            >
              {failure}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={!file || !salesperson.trim() || submitting || outOfCredits}
          >
            {submitting ? "Uploading…" : "Start the analysis"}
            {!submitting && <IconArrow size={13} />}
          </button>
        </form>
      ) : (
        <>
          <section className="panel" style={{ padding: "22px 24px", marginBottom: 20 }}>
            <div className="eyebrow" style={{ marginBottom: 16 }}>
              Analysis graph
            </div>

            <div style={{ display: "grid", gap: 3 }}>
              {STAGES.map((stage, index) => {
                const event = events.get(stage.key);
                const status: StageStatus = event?.status ?? "pending";
                return (
                  <StageRow
                    key={stage.key}
                    index={index}
                    label={stage.label}
                    agent={stage.agent}
                    status={status}
                    detail={event?.detail}
                    elapsed={event?.elapsed_ms}
                    last={index === STAGES.length - 1}
                  />
                );
              })}
            </div>
          </section>

          {failure && (
            <div
              className="panel"
              style={{
                padding: "16px 19px",
                marginBottom: 18,
                borderColor: "var(--rose)",
              }}
            >
              <div style={{ display: "flex", gap: 9, alignItems: "center", marginBottom: 6 }}>
                <IconWarning size={14} style={{ color: "var(--rose)" }} />
                <strong style={{ fontSize: 14 }}>The analysis failed</strong>
              </div>
              <p style={{ margin: 0, fontSize: 13, color: "var(--ink-2)" }}>{failure}</p>
              {billing?.enforced && (
                <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--ink-3)" }}>
                  Your credit has been returned.
                </p>
              )}
            </div>
          )}

          {finished && !failure && (
            <div
              className="panel rise"
              style={{
                padding: "20px 22px",
                display: "flex",
                gap: 16,
                alignItems: "center",
                flexWrap: "wrap",
                background: "linear-gradient(100deg, var(--willow-wash), var(--paper-2) 60%)",
                borderColor: "color-mix(in oklab, var(--willow) 40%, var(--rule))",
              }}
            >
              <IconCheck size={20} style={{ color: "var(--willow)" }} />
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontSize: 15, fontWeight: 500 }}>
                  {degraded.length ? "Finished, with gaps" : "Analysis complete"}
                </div>
                {done?.detail && (
                  <div style={{ fontSize: 13, color: "var(--ink-2)", marginTop: 2 }}>
                    {done.detail}
                    {degraded.length > 0 && ` · could not finish: ${degraded.join(", ")}`}
                  </div>
                )}
              </div>
              {repId && events.get("coach")?.status === "ok" && (
                <Link href={`/reps/${repId}`} className="btn">
                  See the coaching plan
                </Link>
              )}
              <button
                className="btn btn-primary"
                onClick={() => router.push(`/calls/${callId}`)}
              >
                Open the call
                <IconArrow size={13} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */

function StageRow({
  index,
  label,
  agent,
  status,
  detail,
  elapsed,
  last,
}: {
  index: number;
  label: string;
  agent: string;
  status: StageStatus;
  detail?: string;
  elapsed?: number;
  last: boolean;
}) {
  const tone =
    status === "ok"
      ? "var(--sage)"
      : status === "failed"
        ? "var(--rose)"
        : status === "running"
          ? "var(--willow)"
          : status === "skipped"
            ? "var(--ink-4)"
            : "var(--ink-4)";

  return (
    <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
      {/* The connector line makes it read as a graph, not a checklist. */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          alignSelf: "stretch",
        }}
      >
        <span
          className={cx(status === "running" && "pulse")}
          style={{
            width: 9,
            height: 9,
            borderRadius: 999,
            marginTop: 9,
            flexShrink: 0,
            background: status === "pending" ? "transparent" : tone,
            border: `1.5px solid ${status === "pending" ? "var(--rule-strong)" : tone}`,
          }}
        />
        {!last && (
          <span
            style={{
              width: 1.5,
              flex: 1,
              minHeight: 18,
              background:
                status === "ok" ? "var(--sage)" : "var(--rule)",
              opacity: status === "ok" ? 0.4 : 1,
            }}
          />
        )}
      </div>

      <div
        className={cx(status === "running" && "running")}
        style={{
          flex: 1,
          padding: "7px 12px",
          borderRadius: "var(--r)",
          marginBottom: 3,
          background: status === "running" ? "var(--paper-3)" : "transparent",
          opacity: status === "pending" ? 0.5 : 1,
          transition: "opacity 300ms ease, background 300ms ease",
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
          <span style={{ fontSize: 13.5, fontWeight: status === "running" ? 550 : 450 }}>
            {label}
          </span>
          <span className="eyebrow">{agent}</span>
          {elapsed != null && elapsed > 0 && (
            <span
              className="num"
              style={{ marginLeft: "auto", fontSize: 11, color: "var(--ink-4)" }}
            >
              {(elapsed / 1000).toFixed(1)}s
            </span>
          )}
        </div>
        {detail && (
          <div style={{ fontSize: 12.5, color: "var(--ink-2)", marginTop: 3 }}>
            {detail}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label style={{ display: "block" }}>
      <span className="eyebrow" style={{ display: "block", marginBottom: 6 }}>
        {label}
      </span>
      {children}
    </label>
  );
}
