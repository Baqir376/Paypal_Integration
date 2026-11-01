"use client";

/**
 * The Dojo — the voice console.
 *
 * A rep practises by voice against a buyer built from the objections that
 * actually killed their own deals. The workspace is three columns: the
 * persona and its provenance, the live conversation under a neural orb whose
 * scale is driven by real microphone amplitude, and a diagnostics rail that
 * reports what the engine is actually doing.
 *
 * The instruments are meters, not decoration. The orb and the waveform read
 * the microphone through an AnalyserNode; when permission is refused or there
 * is no input device they sit at zero rather than animating over a dead
 * signal. Latency is measured to the first streamed token, not estimated. An
 * interface that animates over nothing is the interface lying about what it
 * knows, and catching exactly that in other people is what this product is
 * for.
 *
 * Speech in uses the browser's Web Speech API by default — instant, no upload,
 * and it cannot fail because of venue wifi. Where a Qwen key is configured the
 * same turn can be routed through Qwen ASR and TTS instead, and the readout is
 * honest about which is in use.
 *
 * Language is a first-class control, not a locale guess. A Pakistani floor runs
 * calls in Urdu, Roman Urdu and English — often inside one sentence — and the
 * Web Speech API has to be *told* which: left on the page language it will
 * transcribe Urdu speech as nonsense English and read Urdu script aloud in an
 * English voice. The picker sets the recognition tag, the synthesis tag and the
 * voice, and the rail reports what it actually resolved rather than what was
 * asked for.
 */

import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { ScoreRing } from "@/components/charts";
import {
  IconArrow,
  IconCheck,
  IconMic,
  IconSpark,
  IconStop,
  IconWarning,
} from "@/components/icons";
import {
  Diagnostics,
  Orb,
  Waveform,
  useAmplitude,
  useTypewriter,
  type OrbState,
} from "@/components/system/Instruments";
import { ErrorState, LoadingState } from "@/components/ui";
import { ApiError, api, streamDojoTurn } from "@/lib/api";
import { AXIS_LABELS, cx, percent } from "@/lib/format";
import {
  AUTO_DIR,
  SPEECH_LANGS,
  isRtl,
  langById,
  replyLanguage,
  loadVoices,
  pickVoice,
  recognitionCtor,
  type SpeechLang,
} from "@/lib/lang";
import { speak as speakAloud, stopSpeaking, type SpokenBy } from "@/lib/speech";
import type {
  CoachNudge,
  DojoSession,
  Health,
  Play,
  RepSnapshot,
} from "@/lib/types";

export default function DojoPage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <Dojo />
    </Suspense>
  );
}

function Dojo() {
  const search = useSearchParams();
  const [reps, setReps] = useState<RepSnapshot[]>([]);
  const [repId, setRepId] = useState(search.get("rep") ?? "");
  /** Opened from a coaching plan: the same room, but this one has a verdict. */
  const closingTest = search.get("test") === "1";
  const [difficulty, setDifficulty] = useState(2);
  const [error, setError] = useState<ApiError | null>(null);
  /** A limitation of this browser or its permissions -- not a fault in
      Salix, and shown as advice rather than as an error. */
  const [notice, setNotice] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  const [session, setSession] = useState<DojoSession | null>(null);
  const [plays, setPlays] = useState<Play[]>([]);
  const [opening, setOpening] = useState("");
  const [nudges, setNudges] = useState<CoachNudge[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [finished, setFinished] = useState(false);

  /** Time to the first streamed token of the last turn. Measured, not guessed. */
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  /* --- Language ------------------------------------------------------ */

  const [langId, setLangId] = useState("en-PK");
  const lang = langById(langId);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [canDictate, setCanDictate] = useState(true);

  // The voice list is populated asynchronously in Chrome and synchronously in
  // Safari. Handling only one of those is why voice pickers so often come up
  // empty on a first load.
  useEffect(() => loadVoices(setVoices), []);
  useEffect(() => setCanDictate(!!recognitionCtor()), []);

  const voice = pickVoice(lang, voices);

  /** How the last line was actually spoken. Reported, never assumed. */
  const [spokenBy, setSpokenBy] = useState<SpokenBy | null>(null);

  const turnStart = useRef<number | null>(null);
  const sessionStart = useRef<number>(0);
  const recognition = useRef<any>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .reps()
      .then((snapshots) => {
        setReps(snapshots);
        if (!repId && snapshots.length) {
          // Default to whoever most needs the practice.
          setRepId(snapshots[snapshots.length - 1].rep.id);
        }
      })
      .catch((e: ApiError) => setError(e));
    api.health().then(setHealth).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [session?.turns.length, streaming]);

  /* --- Speech in ---------------------------------------------------- */

  const startListening = useCallback(() => {
    const SpeechRecognition = recognitionCtor();
    if (!SpeechRecognition) {
      setNotice(
        "This browser has no speech recognition — it is a Chrome and Edge feature. Type your turn instead; everything else, including the scoring, works exactly the same.",
      );
      return;
    }

    const instance = new SpeechRecognition() as any;
    instance.continuous = true;
    instance.interimResults = true;
    // The chosen language, not the page's. Left at the default, Urdu speech
    // comes back as nonsense English and the rep blames themselves.
    instance.lang = lang.tag;

    let finalText = "";
    turnStart.current = Date.now();

    instance.onresult = (event: any) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const chunk = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += chunk + " ";
        else interim += chunk;
      }
      setDraft((finalText + interim).trim());
    };
    instance.onerror = (event: any) => {
      setListening(false);
      // `language-not-supported` is the one worth explaining: it means the
      // browser has no acoustic model for this tag, which is a real and common
      // outcome for ur-PK, and the rep needs to know to type instead.
      if (event?.error === "language-not-supported") {
        setNotice(
          `This browser cannot recognise ${lang.label} (${lang.tag}) speech. Type the turn instead, or switch to English — the scoring is identical either way.`,
        );
      } else if (event?.error === "not-allowed") {
        setNotice("Microphone permission was refused. Type your turn instead.");
      }
    };
    instance.onend = () => setListening(false);

    try {
      instance.start();
      recognition.current = instance;
      setListening(true);
    } catch {
      setListening(false);
    }
  }, [lang]);

  function stopListening() {
    recognition.current?.stop();
    setListening(false);
  }

  /* --- Speech out --------------------------------------------------- */

  /**
   * Read the buyer's line aloud.
   *
   * Delegates to lib/speech, which uses the neural voice and only falls back
   * to a locally installed one if that is unreachable. The buyer is a woman,
   * and the default English voice on Windows is Microsoft David, who is not --
   * so preferring a local voice meant a male buyer on most machines in the
   * country, however carefully the neural voices had been chosen.
   *
   * The language is taken from the *text*, not the session. The offline twin
   * answers in English even when the rep is speaking Urdu, and an English
   * sentence routed to an Urdu voice is as wrong as the reverse.
   */
  function speak(text: string) {
    // Both offered languages are Latin script and both read correctly with a
    // Pakistani-English voice, so the session's language is simply right --
    // no need to sniff the script the way there was when Urdu script was an
    // option and the buyer might answer in either.
    void speakAloud(text, lang, voices).then(setSpokenBy);
  }

  /* --- Session lifecycle -------------------------------------------- */

  async function start() {
    setError(null);
    setBusy(true);
    setFinished(false);
    setNudges([]);
    try {
      const response = closingTest
        ? await api.roleplay.start(repId, replyLanguage(langId))
        : await api.dojo.start(repId, difficulty, "", replyLanguage(langId));
      setSession(response.session);
      setPlays(response.plays);
      setOpening(response.opening);
      sessionStart.current = Date.now();
      speak(response.opening);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!session || !draft.trim() || busy) return;
    const text = draft.trim();
    setDraft("");
    setBusy(true);
    setStreaming("");
    stopListening();

    const now = Date.now();
    const startMs = (turnStart.current ?? now) - sessionStart.current;
    const endMs = now - sessionStart.current;
    turnStart.current = null;

    // Time to first token. The rail reports this rather than a nominal figure,
    // because a latency number nobody measured is a decoration.
    const sent = performance.now();
    let firstToken = true;

    let reply = "";
    try {
      await streamDojoTurn(
        session,
        text,
        { start_ms: Math.max(0, startMs), end_ms: Math.max(startMs + 500, endMs) },
        {
          onDelta: (chunk) => {
            if (firstToken) {
              firstToken = false;
              setLatencyMs(Math.round(performance.now() - sent));
            }
            reply += chunk;
            setStreaming(reply);
          },
          onNudge: (nudge) => setNudges((current) => [...current, nudge as CoachNudge]),
          // A quota, not a conversation. Shown as advice rather than let the
          // buyer say "sorry, could you say that again?" on every turn, which
          // reads as a broken product instead of a limit that clears shortly.
          onThrottled: (detail) => setNotice(detail),
          onSession: (updated) => {
            setSession(updated);
            setStreaming("");
          },
        },
      );
      if (reply.trim()) speak(reply.trim());
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!session) return;
    setBusy(true);
    try {
      const scored = await api.dojo.end(session);
      setSession(scored);
      setFinished(true);
      stopSpeaking();
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  /* --- Instruments --------------------------------------------------- */

  // The microphone is opened when the rep starts speaking and released the
  // moment they stop. Holding it open because the page might want it later is
  // how a browser ends up showing a recording indicator over an idle tab.
  const amplitude = useAmplitude(listening);
  const typed = useTypewriter(streaming);

  const orbState: OrbState = listening
    ? "listening"
    : streaming
      ? "speaking"
      : busy
        ? "thinking"
        : "idle";

  /* --- Render -------------------------------------------------------- */

  if (error && !session && reps.length === 0) return <ErrorState message={error.detail} status={error.status} />;

  const rep = reps.find((r) => r.rep.id === repId);
  const repTurns = session?.turns.filter((t) => t.speaker === "rep") ?? [];
  const spokenWords = repTurns.reduce(
    (total, turn) => total + turn.text.trim().split(/\s+/).filter(Boolean).length,
    0,
  );

  return (
    <div className="page" data-status="THE DOJO">
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            {closingTest ? "Closing test" : "The Dojo"}
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            {closingTest ? (
              <>
                Can you close it now?
              </>
            ) : (
              <>
                Practise against the buyer
                <br />
                who actually beat you
              </>
            )}
          </h1>
          {closingTest && (
            <p className="lede" style={{ marginTop: 12, marginBottom: 0 }}>
              Use what your coaching plan taught you. The buyer only commits once
              you have shown it, and you have to ask.
            </p>
          )}
          <p className="lede" style={{ marginTop: 12, marginBottom: 0 }}>
            This persona is not invented. Its objections are lifted from the
            calls in this rep's own lost and stalled deals, weighted by how
            badly each one was handled.
          </p>
        </div>
      </header>

      {!session ? (
        /* ================================================================
           BRIEFING — the console before it is running
           ============================================================== */
        <div className="dojo-briefing">
          <div className="panel" style={{ padding: 26 }}>
            <div style={{ marginBottom: 18 }}>
              {/* A real label rather than a styled span: it names the control
                  for a screen reader and makes the caption itself clickable. */}
              <label
                className="eyebrow"
                htmlFor="dojo-rep"
                style={{ display: "block", marginBottom: 7 }}
              >
                Who is practising
              </label>
              <select
                id="dojo-rep"
                className="field"
                value={repId}
                onChange={(e) => setRepId(e.target.value)}
              >
                {reps.map((snapshot) => (
                  <option key={snapshot.rep.id} value={snapshot.rep.id}>
                    {snapshot.rep.name} — score {snapshot.overall_score.toFixed(0)}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: 20 }}>
              <span className="eyebrow" style={{ display: "block", marginBottom: 7 }}>
                What language is this call in
              </span>
              <LanguageSwitch value={langId} onChange={setLangId} />
              <p style={{ fontSize: 11.5, color: "var(--ink-3)", margin: "8px 0 0", lineHeight: 1.5 }}>
                {canDictate ? (
                  <>
                    Dictation will listen for{" "}
                    <code className="num">{lang.tag}</code>. The buyer answers
                    in a <b>neural voice</b>
                    {langId === "roman"
                      ? " that reads Roman Urdu phonetically"
                      : ""}
                    , the same one on every machine — not whatever this
                    computer happens to have installed.
                  </>
                ) : (
                  <>
                    This browser has no dictation (it is a Chrome and Edge
                    feature). Type your turns instead; the scoring is identical,
                    and the buyer is still read aloud.
                  </>
                )}
              </p>
            </div>

            <div style={{ marginBottom: 22 }}>
              <span className="eyebrow" style={{ display: "block", marginBottom: 7 }}>
                How hard should they hold the line
              </span>
              <div style={{ display: "flex", gap: 7 }}>
                {[
                  { value: 1, label: "Warm up" },
                  { value: 2, label: "Realistic" },
                  { value: 3, label: "Brutal" },
                ].map((option) => (
                  <button
                    key={option.value}
                    onClick={() => setDifficulty(option.value)}
                    className="btn"
                    style={{
                      flex: 1,
                      justifyContent: "center",
                      borderColor:
                        difficulty === option.value ? "var(--willow)" : "var(--rule-strong)",
                      background:
                        difficulty === option.value ? "var(--willow-wash)" : "var(--paper-2)",
                      color: difficulty === option.value ? "var(--willow)" : "var(--ink-2)",
                    }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {notice && (
              <p style={{ color: "var(--ink-3)", fontSize: 13, marginBottom: 14 }}>{notice}</p>
            )}
            {error && (
              <p style={{ color: "var(--rose)", fontSize: 13, marginBottom: 14 }}>{error.detail}</p>
            )}

            <button
              className="btn btn-primary"
              onClick={start}
              disabled={!repId || busy}
              style={{ width: "100%", justifyContent: "center" }}
            >
              {busy ? "Building the buyer…" : "Start the session"}
              {!busy && <IconArrow size={13} />}
            </button>

            {rep && (
              <p style={{ fontSize: 12.5, color: "var(--ink-3)", margin: "14px 0 0" }}>
                Salix will read {rep.rep.name.split(" ")[0]}'s calls, pull out the
                objections that were never resolved, and build an opponent around
                them.
              </p>
            )}
          </div>

          {/* The orb idles here so the console is recognisably the same
              instrument before and after the session starts. */}
          <div className="dojo-stage" style={{ minHeight: 340 }}>
            <Orb state="idle" />
            <div className="sx-tag" style={{ marginTop: 22 }}>
              [ ENGINE IDLE · AWAITING PERSONA ]
            </div>
          </div>
        </div>
      ) : (
        /* ================================================================
           THE CONSOLE
           ============================================================== */
        <div className="dojo-grid">
          {/* --- Persona dossier ---------------------------------------- */}
          <section className="panel" style={{ padding: "18px 19px" }}>
            <div className="eyebrow" style={{ marginBottom: 12 }}>
              Your buyer
            </div>
            <h2 className="display" style={{ fontSize: 25, margin: "0 0 3px" }}>
              {session.persona.name}
            </h2>
            <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginBottom: 12 }}>
              {session.persona.title} · {session.persona.company}
            </div>
            <p style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.55, margin: "0 0 16px" }}>
              {session.persona.disposition}.
            </p>

            <div className="eyebrow" style={{ marginBottom: 8 }}>
              They will push on
            </div>
            {session.persona.objections.map((objection, index) => (
              <div key={index} style={{ padding: "9px 0", borderTop: "1px solid var(--rule)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span className="chip chip-ember">
                    {objection.category.replace("_", " ")}
                  </span>
                  <span
                    className="num"
                    style={{ fontSize: 10, color: "var(--ink-4)", marginLeft: "auto" }}
                  >
                    {Math.round(objection.hardness * 100)}%
                  </span>
                </div>
                <p
                  dir={AUTO_DIR}
                  className={isRtl(objection.text) ? "urdu-prose" : undefined}
                  style={{
                    margin: 0,
                    fontSize: 12.3,
                    color: "var(--ink-2)",
                    lineHeight: isRtl(objection.text) ? undefined : 1.5,
                  }}
                >
                  {objection.text}
                </p>
                {objection.from_call_id && (
                  <Link
                    href={`/calls/${objection.from_call_id}`}
                    className="eyebrow"
                    style={{ color: "var(--willow)", display: "inline-block", marginTop: 5 }}
                  >
                    from a real call →
                  </Link>
                )}
              </div>
            ))}

            {session.persona.derived_from_call_ids.length > 0 && (
              <p
                style={{
                  fontSize: 11.5,
                  color: "var(--ink-4)",
                  marginTop: 14,
                  paddingTop: 12,
                  borderTop: "1px solid var(--rule)",
                }}
              >
                Built from {session.persona.derived_from_call_ids.length} of your
                own calls.
              </p>
            )}
          </section>

          {/* --- The stage ---------------------------------------------- */}
          <section className="panel-flush" style={{ display: "flex", flexDirection: "column" }}>
            <div className="dojo-stage">
              <Orb state={orbState} level={amplitude.level} />

              <div style={{ width: "100%", maxWidth: 460, marginTop: 18 }}>
                <Waveform
                  bands={amplitude.bands}
                  live={listening}
                  voice={orbState === "speaking" ? "buyer" : "rep"}
                />
              </div>

              <div
                className="sx-tag"
                style={{
                  marginTop: 14,
                  color:
                    orbState === "listening"
                      ? "var(--voice-rep)"
                      : orbState === "speaking"
                        ? "var(--voice-buyer)"
                        : undefined,
                }}
              >
                [{" "}
                {orbState === "listening"
                  ? "CAPTURING · WEB SPEECH API"
                  : orbState === "speaking"
                    ? `${session.persona.name.toUpperCase()} SPEAKING`
                    : orbState === "thinking"
                      ? "COMPOSING REPLY"
                      : "READY · SPEAK OR TYPE"}{" "}
                ]
              </div>
            </div>

            {/* --- Live transcription --------------------------------- */}
            <div className="dojo-scene" ref={scrollRef}>
              {opening && (
                <Bubble speaker="buyer" text={opening} name={session.persona.name} />
              )}
              {session.turns.map((turn) => (
                <Bubble
                  key={turn.index}
                  speaker={turn.speaker as "rep" | "buyer"}
                  text={turn.text}
                  name={turn.speaker === "rep" ? "You" : session.persona.name}
                />
              ))}
              {streaming && (
                /* Typed rather than dumped. The typewriter runs behind the
                   stream and never types a character the server has not sent,
                   so it cannot claim words the model did not produce. */
                <Bubble
                  speaker="buyer"
                  text={typed}
                  name={session.persona.name}
                  live
                />
              )}
              {listening && draft && (
                <Bubble speaker="rep" text={draft} name="You" interim />
              )}
            </div>

            {!finished && (
              <div style={{ borderTop: "1px solid var(--rule)", padding: 14 }}>
                <div style={{ display: "flex", gap: 9, alignItems: "flex-end" }}>
                  <textarea
                    className="field"
                    // The browser picks direction from the first strong
                    // character, so an Urdu turn right-aligns itself and an
                    // English one does not, with no mode to switch.
                    dir={AUTO_DIR}
                    lang={lang.rtl ? "ur" : "en"}
                    value={draft}
                    onChange={(e) => {
                      if (turnStart.current === null) turnStart.current = Date.now();
                      setDraft(e.target.value);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        send();
                      }
                    }}
                    placeholder={
                      listening
                        ? langId === "roman"
                          ? "Sun rahe hain…"
                          : "Listening…"
                        : langId === "roman"
                          ? "Boliye, ya apni baat likh kar Enter dabaiye"
                          : "Speak, or type your turn and press Enter"
                    }
                    rows={2}
                    style={{ flex: 1, resize: "none" }}
                    disabled={busy}
                  />
                  <button
                    className={cx("btn", listening && "pulse")}
                    onClick={listening ? stopListening : startListening}
                    disabled={!canDictate}
                    title={
                      !canDictate
                        ? "This browser has no speech recognition — type your turn instead"
                        : listening
                          ? "Stop recording"
                          : `Speak your turn in ${lang.label} (${lang.tag})`
                    }
                    style={{
                      borderColor: listening ? "var(--willow)" : undefined,
                      color: listening ? "var(--willow)" : undefined,
                    }}
                  >
                    {listening ? <IconStop size={14} /> : <IconMic size={14} />}
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={send}
                    disabled={busy || !draft.trim()}
                  >
                    {busy ? "…" : "Send"}
                  </button>
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginTop: 9,
                  }}
                >
                  <span className="eyebrow">{repTurns.length} turns taken</span>
                  <button className="btn btn-ghost btn-sm" onClick={finish} disabled={busy}>
                    End and score
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* --- Diagnostics and coach ---------------------------------- */}
          <section style={{ display: "grid", gap: 16, alignContent: "start" }}>
            <Diagnostics
              title="System"
              rows={[
                {
                  label: "[ Engine ]",
                  // The model that answered, and who served it. With a
                  // bring-your-own endpoint configured these differ from the
                  // defaults, and a rail that showed the configured name
                  // rather than the resolved one would be decoration.
                  value: health?.models.reasoning ?? "offline twin",
                  tone: health?.providers?.reasoning === "offline twin" ? "gold" : "signal",
                },
                {
                  label: "[ Served by ]",
                  value: health?.providers?.reasoning ?? "unknown",
                  tone: health?.providers?.reasoning === "offline twin" ? "gold" : "muted",
                },
                {
                  label: "[ Latency ]",
                  value: latencyMs == null ? "—" : `${latencyMs}ms`,
                },
                { label: "[ Transport ]", value: "SSE · one turn, one request" },
                {
                  label: "[ Language ]",
                  value: `${lang.label} · ${lang.tag}`,
                  tone: "gold",
                },
                {
                  label: "[ Voice ]",
                  // The route that actually played, not the one requested. A
                  // readout that reports its own input hides the case where
                  // nothing matched.
                  value:
                    spokenBy?.via === "local"
                      ? `${spokenBy.voice.slice(0, 20)} · local`
                      : spokenBy?.via === "network"
                        ? `network · ${spokenBy.lang}`
                        : spokenBy?.via === "none"
                          ? "unavailable"
                          : voice
                            ? `${voice.name.slice(0, 20)} · local`
                            : "network · on demand",
                  tone: spokenBy?.via === "none" ? "gold" : "muted",
                },
                {
                  label: "[ Capture ]",
                  value: !canDictate
                    ? "unavailable in this browser"
                    : listening
                      ? `web-speech · ${lang.tag}`
                      : "idle",
                  tone: listening ? "signal" : "muted",
                },
                {
                  label: "[ Amplitude ]",
                  value: amplitude.level.toFixed(2),
                  tone: "muted",
                },
                { label: "[ Difficulty ]", value: ["", "warm", "realistic", "brutal"][difficulty] },
                { label: "[ Turns ]", value: String(repTurns.length) },
                { label: "[ Words spoken ]", value: String(spokenWords) },
                {
                  label: "[ Objections ]",
                  value: `${session.persona.objections.length} loaded`,
                  tone: "gold",
                },
              ]}
              foot={
                <div
                  style={{
                    padding: "9px 13px",
                    borderTop: "1px solid var(--line)",
                    color: "var(--text-quaternary)",
                    lineHeight: 1.6,
                  }}
                >
                  Scored on the same engine that measures real recordings, so
                  practice and reality are comparable.
                </div>
              }
            />

            {finished && session.score ? (
              <>
                {session.assessment && <ClosingPanel session={session} />}
                <ScorePanel session={session} onRestart={() => setSession(null)} />
              </>
            ) : (
              <>
                <div className="panel" style={{ padding: "16px 17px" }}>
                  <div className="eyebrow" style={{ marginBottom: 12 }}>
                    Live coach
                  </div>
                  {nudges.length === 0 && (
                    <p style={{ fontSize: 12.5, color: "var(--ink-3)", margin: 0, lineHeight: 1.55 }}>
                      Nothing to flag yet. Ask an open question and let the
                      silence do the work.
                    </p>
                  )}
                  {nudges
                    .slice()
                    .reverse()
                    .slice(0, 5)
                    .map((nudge, index) => (
                      <div
                        key={`${nudge.at_turn}-${nudge.title}-${index}`}
                        className="rise"
                        style={{
                          padding: "10px 12px",
                          marginBottom: 9,
                          borderRadius: "var(--r)",
                          background:
                            nudge.kind === "praise"
                              ? "var(--sage-wash)"
                              : nudge.kind === "play"
                                ? "var(--willow-wash)"
                                : "var(--ember-wash)",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                            marginBottom: 4,
                          }}
                        >
                          {nudge.kind === "praise" ? (
                            <IconCheck size={11} style={{ color: "var(--sage)" }} />
                          ) : nudge.kind === "play" ? (
                            <IconSpark size={11} style={{ color: "var(--willow)" }} />
                          ) : (
                            <IconWarning size={11} style={{ color: "var(--ember)" }} />
                          )}
                          <span style={{ fontSize: 12.5, fontWeight: 550 }}>
                            {nudge.title}
                          </span>
                        </div>
                        <p style={{ margin: 0, fontSize: 12, color: "var(--ink-2)", lineHeight: 1.5 }}>
                          {nudge.detail}
                        </p>
                      </div>
                    ))}
                </div>

                {plays.length > 0 && (
                  <div className="panel" style={{ padding: "16px 17px" }}>
                    <div className="eyebrow" style={{ marginBottom: 11 }}>
                      Plays to reach for
                    </div>
                    {plays.slice(0, 4).map((play) => (
                      <div
                        key={play.id}
                        style={{ padding: "9px 0", borderTop: "1px solid var(--rule)" }}
                      >
                        <div className="display" style={{ fontSize: 15 }}>
                          {play.name}
                        </div>
                        <p style={{ margin: "3px 0 0", fontSize: 12, color: "var(--ink-3)", lineHeight: 1.45 }}>
                          {play.when_to_use}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */

/**
 * The call's language.
 *
 * Four buttons rather than a `<select>`: this is the control that decides
 * whether dictation works at all, and burying it in a dropdown is how it ends
 * up never being touched. Each option carries its own name in its own script,
 * because a rep looking for Urdu is looking for "اردو".
 */
function LanguageSwitch({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="lang-switch" role="group" aria-label="Call language">
      {SPEECH_LANGS.map((option: SpeechLang) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onChange(option.id)}
          aria-pressed={value === option.id}
          lang={option.rtl ? "ur" : "en"}
          dir={option.rtl ? "rtl" : "ltr"}
        >
          <span>{option.label}</span>
          <small dir="ltr">{option.native}</small>
        </button>
      ))}
    </div>
  );
}

function Bubble({
  speaker,
  text,
  name,
  live,
  interim,
}: {
  speaker: "rep" | "buyer";
  text: string;
  name: string;
  live?: boolean;
  /** The rep's own speech, still being recognised. Shown dimmed so it is
      clearly a draft rather than a turn that has been taken. */
  interim?: boolean;
}) {
  const isRep = speaker === "rep";
  const rtl = isRtl(text);
  return (
    <div
      style={{
        marginBottom: 16,
        display: "flex",
        justifyContent: isRep ? "flex-end" : "flex-start",
        opacity: interim ? 0.55 : 1,
      }}
    >
      <div style={{ maxWidth: "82%" }}>
        <div
          className="eyebrow"
          style={{ marginBottom: 5, textAlign: isRep ? "right" : "left" }}
        >
          {name}
          {interim && " · recognising"}
        </div>
        {/* `dir="auto"` per turn rather than per column: the rep may be
            speaking Urdu while the buyer answers in English, and both sit in
            the same thread. The Urdu face is applied only when the turn is
            actually Urdu, because it needs more leading than a Latin one. */}
        <div
          dir={AUTO_DIR}
          lang={rtl ? "ur" : undefined}
          className={rtl ? "urdu-prose" : undefined}
          style={{
            padding: "11px 14px",
            borderRadius: isRep ? "12px 12px 3px 12px" : "12px 12px 12px 3px",
            background: isRep ? "var(--rep-soft)" : "var(--paper-3)",
            border: `1px solid ${isRep ? "transparent" : "var(--rule)"}`,
            fontSize: 14,
            lineHeight: rtl ? undefined : 1.58,
            color: "var(--ink)",
          }}
        >
          {text}
          {(live || interim) && <span className="sx-caret" />}
        </div>
      </div>
    </div>
  );
}

function ClosingPanel({ session }: { session: DojoSession }) {
  const result = session.assessment!;
  return (
    <div
      className="panel rise"
      style={{
        padding: "18px 19px",
        marginBottom: 14,
        borderColor: result.ready ? "var(--sage)" : "var(--ember)",
      }}
    >
      <div className="eyebrow" style={{ marginBottom: 8 }}>
        Closing test
      </div>
      <div className="display d3" style={{ margin: "0 0 8px" }}>
        {result.ready ? "You closed it" : result.deal_closed ? "Closed, with gaps" : "Not closed"}
      </div>
      <p style={{ fontSize: 13, margin: "0 0 12px", color: "var(--ink-2)", lineHeight: 1.55 }}>
        {result.summary}
      </p>
      {result.close_evidence && (
        <p style={{ fontSize: 12.5, margin: "0 0 12px", color: "var(--ink-3)", fontStyle: "italic" }} dir="auto">
          &ldquo;{result.close_evidence}&rdquo;
        </p>
      )}
      {result.gaps.map((gap) => (
        <div key={gap.axis} style={{ padding: "8px 0", borderTop: "1px solid var(--rule)", fontSize: 12.8 }}>
          <span className={`chip ${gap.passed ? "chip-sage" : "chip-rose"}`} style={{ marginRight: 8 }}>
            {gap.passed ? "shown" : "not shown"}
          </span>
          <strong style={{ fontWeight: 550 }}>{AXIS_LABELS[gap.axis]}</strong>
          {gap.feedback && (
            <div style={{ marginTop: 4, color: "var(--ink-2)" }}>{gap.feedback}</div>
          )}
          {gap.evidence && (
            <div style={{ marginTop: 3, color: "var(--ink-3)", fontStyle: "italic" }} dir="auto">
              &ldquo;{gap.evidence}&rdquo;
            </div>
          )}
        </div>
      ))}
      {result.next_focus && (
        <p style={{ fontSize: 12.8, margin: "10px 0 0" }}>
          <strong style={{ fontWeight: 550 }}>Next: </strong>
          {result.next_focus}
        </p>
      )}
      {result.judged_by === "measurements" && (
        <p style={{ fontSize: 11.5, margin: "10px 0 0", color: "var(--ink-3)" }}>
          Judged from measurements only, so this cannot confirm a close.
        </p>
      )}
    </div>
  );
}

function ScorePanel({
  session,
  onRestart,
}: {
  session: DojoSession;
  onRestart: () => void;
}) {
  const score = session.score!;
  return (
    <div className="panel rise" style={{ padding: "20px 19px" }}>
      <div style={{ display: "grid", placeItems: "center", marginBottom: 16 }}>
        <ScoreRing score={score.overall} size={86} caption="session" />
      </div>

      <p
        style={{
          fontSize: 14,
          lineHeight: 1.55,
          textAlign: "center",
          margin: "0 0 18px",
          color: "var(--ink)",
        }}
      >
        {score.verdict}
      </p>

      <Row
        label="Objections handled"
        value={`${score.objections_handled} / ${score.objections_faced}`}
        tone={
          score.objections_handled === score.objections_faced
            ? "var(--sage)"
            : "var(--ember)"
        }
      />
      <Row label="Talk ratio" value={percent(score.talk_ratio_rep)} />
      {Object.entries(score.axes)
        .slice(0, 4)
        .map(([axis, value]) => (
          <Row
            key={axis}
            label={AXIS_LABELS[axis as keyof typeof AXIS_LABELS]}
            value={value.toFixed(0)}
          />
        ))}

      {score.plays_landed.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div className="eyebrow" style={{ marginBottom: 7 }}>
            Landed
          </div>
          {score.plays_landed.map((name) => (
            <span key={name} className="chip chip-sage" style={{ marginRight: 5, marginBottom: 5 }}>
              {name}
            </span>
          ))}
        </div>
      )}

      <button
        className="btn btn-primary"
        onClick={onRestart}
        style={{ width: "100%", justifyContent: "center", marginTop: 14 }}
      >
        Go again
      </button>
    </div>
  );
}

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        padding: "7px 0",
        borderTop: "1px solid var(--rule)",
        fontSize: 13,
      }}
    >
      <span style={{ color: "var(--ink-2)" }}>{label}</span>
      <span className="num" style={{ color: tone ?? "var(--ink)" }}>
        {value}
      </span>
    </div>
  );
}
