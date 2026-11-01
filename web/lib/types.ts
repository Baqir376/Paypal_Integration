/* ---------------------------------------------------------------------------
 * GENERATED FILE -- DO NOT EDIT.
 *
 * Compiled from the Pydantic models in api/salix/schemas by
 * `python api/scripts/gen_types.py`. The backend contract is the single
 * source of truth; if a field changes there, this file changes and the
 * frontend stops compiling until it is reconciled.
 * ------------------------------------------------------------------------- */


/* --- Enumerations -------------------------------------------------------- */

export type SpeakerRole = "rep" | "buyer" | "unknown";
export type CallOutcome = "won" | "lost" | "open";
export type CallStatus = "uploaded" | "transcribing" | "analyzing" | "ready" | "failed";
export type DealStage = "discovery" | "demo" | "proposal" | "negotiation" | "closed_won" | "closed_lost";
export type CallStage = "opener" | "discovery" | "pitch" | "objection" | "negotiation" | "close" | "next_steps";
export type ObjectionCategory = "price" | "timing" | "authority" | "competition" | "status_quo" | "trust" | "fit" | "risk" | "other";
export type PlayKind = "story_arc" | "analogy" | "proof_point" | "reframe" | "question_sequence" | "objection_turn";
export type RiskKind = "unresolved_objection" | "no_next_step" | "single_threaded" | "momentum_decay" | "monologue_dominance" | "champion_silent" | "no_economic_buyer";
export type Severity = "low" | "medium" | "high" | "critical";
export type Emotion = "neutral" | "positive" | "engaged" | "hesitant" | "frustrated" | "skeptical";
export type SkillAxis = "listening" | "discovery" | "storytelling" | "objection_handling" | "pace_and_presence" | "closing";
export type StageKey = "upload" | "transcribe" | "diarize" | "metrics" | "anatomy" | "plays" | "embed" | "trajectory" | "coach" | "done";
export type StageStatus = "pending" | "running" | "ok" | "failed" | "skipped";

/* --- Domain models ------------------------------------------------------- */

/** A pointer into the transcript. `quote` is verbatim so the UI can render     the claim and its proof side by side without a second lookup. */
export interface EvidenceRef {
  /** Segment id, e.g. 's0042' */
  segment_id: string;
  call_id: string | null;
  /** Verbatim text from that segment */
  quote: string;
  start_ms: number | null;
}

export interface Segment {
  /** Stable within a call, e.g. 's0042' */
  id: string;
  index: number;
  /** Raw diarization label from ASR */
  speaker_id: number;
  role: SpeakerRole;
  start_ms: number;
  end_ms: number;
  text: string;
  emotion: Emotion | null;
}

export interface Transcript {
  call_id: string;
  segments: Segment[];
  language: string;
}

export interface Call {
  id: string;
  org_id: string;
  deal_id: string | null;
  rep_id: string;
  title: string;
  account: string;
  occurred_at: string;
  duration_ms: number;
  audio_url: string | null;
  status: CallStatus;
  outcome: CallOutcome;
  error: string | null;
  language: string;
}

export interface Org {
  id: string;
  name: string;
  product: string;
  /** Ideal customer profile, one line */
  icp: string;
  cycle_label: string;
}

export interface Rep {
  id: string;
  org_id: string;
  name: string;
  role: string;
  initials: string;
  quota: number;
  attained: number;
  joined_at: string;
  is_top_performer: boolean;
  archived: boolean;
}

export interface Cycle {
  id: string;
  org_id: string;
  label: string;
  start: string;
  end: string;
  is_current: boolean;
  target: number;
  closed: number;
}

/** One bucket of the talk timeline, used to drive the Conversation Helix. */
export interface TalkSlice {
  start_ms: number;
  end_ms: number;
  rep_ms: number;
  buyer_ms: number;
  rep_share: number;
  /** Normalized speech density */
  energy: number;
}

export interface Monologue {
  speaker_role: string;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  segment_ids: string[];
  opening_words: string;
}

export interface Interruption {
  at_ms: number;
  by_role: string;
  segment_id: string;
  overlap_ms: number;
}

export interface CallMetrics {
  call_id: string;
  duration_ms: number;
  rep_talk_ms: number;
  buyer_talk_ms: number;
  silence_ms: number;
  talk_ratio_rep: number;
  longest_monologue_ms: number;
  longest_monologue_at_ms: number;
  monologues_over_threshold: number;
  monologues: Monologue[];
  /** Mean pause the rep leaves after the buyer stops speaking */
  patience_ms: number;
  switches_per_min: number;
  interruptions_by_rep: number;
  interruptions_by_buyer: number;
  interruptions: Interruption[];
  rep_question_count: number;
  rep_question_rate_per_min: number;
  open_question_ratio: number;
  rep_wpm: number;
  buyer_wpm: number;
  /** Dominant language of the rep's speech: 'en', 'ur' or 'ur-roman'. Pace is judged against a band calibrated for it, because words per minute is not comparable across languages. */
  language: string;
  /** Filler words per 100 rep words */
  filler_rate_rep: number;
  longest_dead_air_ms: number;
  timeline: TalkSlice[];
}

export interface AxisScore {
  axis: SkillAxis;
  score: number;
  /** Top-performer value */
  benchmark: number;
  /** Plain-language reasons for the score */
  drivers: string[];
}

/** Where the deal stands after this call. See metrics/deal.py. */
export interface DealScore {
  score: number;
  /** strong | at risk | weak */
  band: string;
  drivers: string[];
}

/** Metrics translated onto a 0-100 scale against published benchmarks. */
export interface Scorecard {
  call_id: string;
  overall: number;
  axes: AxisScore[];
  deal: DealScore | null;
  /** Why this score should be read with care. Empty when it is sound. */
  caveats: string[];
}

/** Rolled-up view of a rep for the leaderboard and profile header. */
export interface RepSnapshot {
  rep: Rep;
  calls: number;
  deals: number;
  won: number;
  lost: number;
  win_rate: number;
  overall_score: number;
  axes: Record<string, number>;
  team_axes: Record<string, number>;
  trend: number[];
  talk_ratio: number;
  patience_ms: number;
  rank: number;
}

export interface StageSpan {
  stage: CallStage;
  start_ms: number;
  end_ms: number;
  segment_ids: string[];
}

export interface Objection {
  id: string;
  category: ObjectionCategory;
  /** The objection in the buyer's own words */
  text: string;
  raised: EvidenceRef;
  handled: boolean;
  /** 0 = ignored, 5 = turned into a reason to buy */
  handling_quality: number;
  handling: EvidenceRef[];
  note: string;
}

export interface MeddicItem {
  covered: boolean;
  confidence: number;
  evidence: EvidenceRef[];
  note: string;
}

/** MEDDIC qualification coverage. Chosen over BANT because it is the     enterprise standard and its six slots map cleanly onto discoverable     conversational evidence. */
export interface MeddicCoverage {
  metrics: MeddicItem;
  economic_buyer: MeddicItem;
  decision_criteria: MeddicItem;
  decision_process: MeddicItem;
  identify_pain: MeddicItem;
  champion: MeddicItem;
}

export interface Commitment {
  text: string;
  by_role: string;
  evidence: EvidenceRef;
  /** True only if it names a specific action AND a specific time */
  is_concrete: boolean;
}

export interface NextStep {
  text: string;
  evidence: EvidenceRef | null;
  has_date: boolean;
  /** Both sides committed, not just the rep */
  is_mutual: boolean;
}

export interface BuyerSignal {
  /** interest | concern | blocker | buying_signal */
  kind: string;
  text: string;
  evidence: EvidenceRef;
  weight: number;
}

export interface TalkTrackIssue {
  title: string;
  severity: Severity;
  explanation: string;
  evidence: EvidenceRef[];
  /** What a top performer would have said */
  better_move: string;
}

export interface CallAnalysis {
  call_id: string;
  /** Three sentences, no filler, no praise */
  summary: string;
  /** The one thing that decided this call */
  headline: string;
  stages: StageSpan[];
  objections: Objection[];
  meddic: MeddicCoverage;
  commitments: Commitment[];
  next_step: NextStep | null;
  buyer_signals: BuyerSignal[];
  issues: TalkTrackIssue[];
  /** Same shape; `better_move` holds why it worked */
  strengths: TalkTrackIssue[];
}

/** One observed use of a play in a real call. */
export interface PlayInstance {
  id: string;
  play_id: string;
  call_id: string;
  rep_id: string;
  rep_name: string;
  account: string;
  outcome: string;
  /** The verbatim passage where the play lands */
  quote: string;
  evidence: EvidenceRef[];
  /** How well it worked here, judged on the buyer's response */
  effectiveness: number;
}

export interface Play {
  id: string;
  org_id: string;
  /** Short, memorable, title-cased. e.g. 'The Compounding Cost' */
  name: string;
  kind: PlayKind;
  /** One sentence: what this move does to a buyer */
  thesis: string;
  when_to_use: string;
  /** The structural steps, in order */
  beats: string[];
  /** A say-this-way rendering, with [BRACKETED] slots */
  template: string;
  origin_rep_id: string | null;
  origin_rep_name: string;
  instances: PlayInstance[];
  usage_count: number;
  win_rate_with: number | null;
  win_rate_without: number | null;
}

/** Raw Playwright output before dedup against the existing library. */
export interface PlayCandidate {
  name: string;
  kind: PlayKind;
  thesis: string;
  when_to_use: string;
  beats: string[];
  template: string;
  quote: string;
  segment_ids: string[];
  effectiveness: number;
}

export interface SourceRef {
  play_id: string | null;
  play_name: string;
  call_id: string | null;
  segment_id: string | null;
  rep_name: string;
  quote: string;
}

export interface SkillGap {
  axis: SkillAxis;
  rep_value: number;
  top_value: number;
  delta: number;
  severity: string;
  /** Concrete and specific, never generic */
  explanation: string;
  evidence_call_ids: string[];
}

export interface ScriptLine {
  /** rep | buyer_expected */
  speaker: string;
  text: string;
  /** Delivery guidance, kept short */
  note: string;
  source: SourceRef | null;
}

export interface ScriptSection {
  label: string;
  purpose: string;
  lines: ScriptLine[];
}

export interface GeneratedScript {
  id: string;
  rep_id: string;
  title: string;
  /** The exact situation this script is for */
  scenario: string;
  sections: ScriptSection[];
  grounded_in: SourceRef[];
}

export interface Drill {
  title: string;
  axis: SkillAxis;
  instruction: string;
  success_criteria: string;
  /** Seeds the Dojo buyer for this drill */
  persona_hint: string;
}

export interface CoachingPlan {
  id: string;
  rep_id: string;
  rep_name: string;
  generated_at: string;
  /** The single sentence a manager would say */
  diagnosis: string;
  gaps: SkillGap[];
  prescribed_play_ids: string[];
  prescription_rationale: Record<string, string>;
  script: GeneratedScript | null;
  drills: Drill[];
  source_call_id: string | null;
}

export interface Deal {
  id: string;
  org_id: string;
  name: string;
  account: string;
  owner_id: string;
  value: number;
  stage: DealStage;
  outcome: CallOutcome;
  opened_at: string;
  closed_at: string | null;
  contacts: string[];
}

export interface Risk {
  kind: RiskKind;
  severity: Severity;
  title: string;
  /** Names the cause, not the symptom. Cites which call. */
  explanation: string;
  evidence: EvidenceRef[];
  first_seen_call_id: string | null;
  age_days: number;
}

export interface TrajectoryPoint {
  call_id: string;
  occurred_at: string;
  title: string;
  score: number;
  buyer_engagement: number;
  open_objections: number;
  had_next_step: boolean;
  meddic_coverage: number;
}

export interface DealTrajectory {
  deal_id: string;
  deal_name: string;
  account: string;
  owner_name: string;
  value: number;
  stage: DealStage;
  points: TrajectoryPoint[];
  risks: Risk[];
  /** Slope of buyer engagement across the last three calls */
  momentum: number;
  health: number;
  verdict: string;
}

export interface PersonaObjection {
  category: ObjectionCategory;
  text: string;
  from_call_id: string | null;
  hardness: number;
}

export interface BuyerPersona {
  id: string;
  name: string;
  title: string;
  company: string;
  /** e.g. guarded, time-poor, data-driven */
  disposition: string;
  /** What they know and want going in */
  context: string;
  objections: PersonaObjection[];
  /** TTS voice id */
  voice: string;
  /** Prosody control passed to Qwen TTS */
  voice_instruction: string;
  derived_from_call_ids: string[];
  difficulty: number;
}

export interface DojoTurn {
  index: number;
  /** rep | buyer */
  speaker: string;
  text: string;
  start_ms: number;
  end_ms: number;
  audio_url: string | null;
}

/** A live hint on the coach rail. Fired mid-session, never after. */
export interface CoachNudge {
  at_turn: number;
  /** play | warning | praise */
  kind: string;
  title: string;
  detail: string;
  play_id: string | null;
}

export interface DojoScore {
  overall: number;
  axes: Record<string, number>;
  objections_faced: number;
  objections_handled: number;
  plays_landed: string[];
  plays_missed: string[];
  verdict: string;
  talk_ratio_rep: number;
}

export interface GapResult {
  axis: SkillAxis;
  passed: boolean;
  evidence: string;
  feedback: string;
}

/** Could this rep close the deal now? */
export interface ClosingAssessment {
  ready: boolean;
  deal_closed: boolean;
  close_evidence: string;
  gaps: GapResult[];
  next_focus: string;
  summary: string;
  judged_by: string;
}

export interface DojoSession {
  id: string;
  rep_id: string;
  persona: BuyerPersona;
  language: string;
  scenario: string;
  started_at: string;
  ended_at: string | null;
  turns: DojoTurn[];
  nudges: CoachNudge[];
  score: DojoScore | null;
  mode: string;
  plan_id: string | null;
  brief: string;
  assessment: ClosingAssessment | null;
}

export interface RepRow {
  rep_id: string;
  name: string;
  calls: number;
  deals: number;
  won: number;
  lost: number;
  win_rate: number;
  revenue: number;
  overall_score: number;
  axes: Record<string, number>;
  /** Score delta vs. previous cycle */
  trend: number;
  standout: string;
  watch_item: string;
}

export interface TeamMetrics {
  calls_analyzed: number;
  hours_analyzed: number;
  deals: number;
  win_rate: number;
  pipeline_value: number;
  closed_value: number;
  avg_talk_ratio: number;
  avg_patience_ms: number;
  avg_meddic_coverage: number;
  objection_resolution_rate: number;
  next_step_rate: number;
}

export interface Finding {
  title: string;
  detail: string;
  /** Quantified where the data supports it */
  impact: string;
  supporting_call_ids: string[];
}

export interface Recommendation {
  title: string;
  detail: string;
  owner: string;
  expected_lift: string;
  priority: number;
}

export interface CycleReport {
  id: string;
  org_id: string;
  cycle_label: string;
  period_start: string;
  period_end: string;
  /** One line a VP would forward */
  headline: string;
  /** The story of the cycle, in prose */
  narrative: string;
  team: TeamMetrics;
  reps: RepRow[];
  findings: Finding[];
  top_play_ids: string[];
  risks: Risk[];
  recommendations: Recommendation[];
  generated_at: string;
}

export interface PipelineEvent {
  call_id: string;
  stage: StageKey;
  status: StageStatus;
  label: string;
  agent: string;
  detail: string;
  progress: number;
  elapsed_ms: number;
  payload: Record<string, unknown> | null;
}


/* --- Response envelopes (see api/salix/routers) -------------------------- */

export interface Health {
  status: string;
  provider_mode: "live" | "mock";
  /** The models actually being called, after any bring-your-own override. */
  models: Record<string, string>;
  /**
   * Which service is behind each capability: "reasoning", "transcription",
   * "embedding", "speech". A mixed setup is possible -- a Gemini key can drive
   * the reasoning while transcription stays on the offline twin -- so one
   * "live" badge for all four would be a lie.
   */
  providers: Record<string, string>;
  seeded: boolean;
  calls: number;
  plays: number;
  moments: number;
}

export interface Overview {
  org: Org;
  team: TeamMetrics;
  reps: RepSnapshot[];
  recent_calls: CallListItem[];
  risks: Risk[];
  top_plays: Play[];
}

export interface CallListItem extends Call {
  rep_name: string;
  score: number | null;
  talk_ratio_rep: number | null;
  longest_monologue_ms?: number | null;
  headline: string;
}

export interface CallSummary {
  call: Call;
  rep_name: string;
  score: number | null;
  talk_ratio_rep: number | null;
  longest_monologue_ms: number | null;
  headline: string;
  open_objections: number;
}

export interface CallDetailResponse {
  call: Call;
  rep_name: string;
  deal: Deal | null;
  transcript: Transcript | null;
  metrics: CallMetrics | null;
  scorecard: Scorecard | null;
  analysis: CallAnalysis | null;
  plays: PlayWithInstance[];
  citation_coverage: number;
}

export interface PlayWithInstance extends Play {
  instance?: PlayInstance;
  win_rate_lift?: number | null;
  used_by?: string[];
  won_with?: number;
  my_instances?: PlayInstance[];
}

export interface PlayDetail extends Play {
  win_rate_lift: number | null;
  instances: (PlayInstance & {
    rep_name: string;
    call_title: string;
    occurred_at: string | null;
  })[];
}

export interface RepProfile {
  snapshot: RepSnapshot;
  calls: CallListItem[];
  coaching_plan: CoachingPlan | null;
  plays_used: PlayWithInstance[];
  dojo_sessions: DojoSession[];
}

export interface DealWithTrajectory {
  deal: Deal;
  owner_name: string;
  trajectory: DealTrajectory;
  calls?: Call[];
}

export interface SearchHit {
  moment: Record<string, unknown> & {
    id: string;
    call_id: string;
    rep_id: string;
    kind: string;
    outcome: string;
    text: string;
  };
  score: number;
}

export interface DojoStartResponse {
  session: DojoSession;
  rep_name: string;
  plays: Play[];
  opening: string;
}

export interface UploadResponse {
  call_id: string;
  status: string;
  bytes: number;
  rep_id: string;
  events_url: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  picture: string;
  role: "owner" | "member";
  rep_id: string | null;
  org_id: string;
  org_name: string;
}

export interface Me {
  auth_required: boolean;
  google_enabled: boolean;
  user: User | null;
}

export interface TeamInvite {
  id: string;
  email: string;
  role: string;
  rep_id: string | null;
  email_sent: boolean;
}

export interface TeamState {
  members: User[];
  invites: TeamInvite[];
  can_manage: boolean;
  mail_enabled: boolean;
}

export interface DealCalibration {
  decided: number;
  won: number;
  lost: number;
  separation: number | null;
  reliable: boolean;
  verdict: string;
  bands: { band: string; calls: number; won: number; win_rate: number | null }[];
}

export interface CreditPack {
  id: string;
  label: string;
  credits: number;
  price: string;
  currency: string;
}

export interface CreditEntry {
  id: string;
  delta: number;
  reason: string;
  created_at: string;
}

export interface BillingState {
  enforced: boolean;
  can_purchase: boolean;
  can_buy: boolean;
  simulated: boolean;
  provider: "paypal" | "braintree" | "simulator" | null;
  environment: string;
  balance: number;
  call_cost: number;
  packs: CreditPack[];
  history: CreditEntry[];
}

export interface OrderResult {
  order_id: string;
  status: "created" | "pending" | "completed" | "failed" | "review" | "refunded";
  credits: number;
  balance: number;
  detail: string;
}
