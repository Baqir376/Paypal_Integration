"""Compile the Pydantic contract into TypeScript.

Run from the repository root:

    python api/scripts/gen_types.py

The output is `web/lib/types.ts`. Nothing in the frontend defines its own shape
for a backend object, so a field renamed in Python breaks `npm run typecheck`
rather than breaking a page at runtime in front of a judge.

Generation walks the models' JSON Schema rather than their Python annotations,
because the schema is what actually crosses the wire -- computed fields
included, aliases resolved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

API_DIR = Path(__file__).resolve().parent.parent
REPO = API_DIR.parent
sys.path.insert(0, str(API_DIR))

from pydantic import BaseModel  # noqa: E402

from salix import schemas  # noqa: E402

OUTPUT = REPO / "web" / "lib" / "types.ts"

HEADER = """\
/* ---------------------------------------------------------------------------
 * GENERATED FILE -- DO NOT EDIT.
 *
 * Compiled from the Pydantic models in api/salix/schemas by
 * `python api/scripts/gen_types.py`. The backend contract is the single
 * source of truth; if a field changes there, this file changes and the
 * frontend stops compiling until it is reconciled.
 * ------------------------------------------------------------------------- */

"""

# Extra response shapes that live in routers rather than in schemas/.
EXTRA = """
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
  events_url: string;
}
"""

# Emitted in dependency order so the file reads top-down.
MODELS: list[type[BaseModel]] = [
    schemas.EvidenceRef,
    schemas.Segment,
    schemas.Transcript,
    schemas.Call,
    schemas.Org,
    schemas.Rep,
    schemas.Cycle,
    schemas.TalkSlice,
    schemas.Monologue,
    schemas.Interruption,
    schemas.CallMetrics,
    schemas.AxisScore,
    schemas.Scorecard,
    schemas.RepSnapshot,
    schemas.StageSpan,
    schemas.Objection,
    schemas.MeddicItem,
    schemas.MeddicCoverage,
    schemas.Commitment,
    schemas.NextStep,
    schemas.BuyerSignal,
    schemas.TalkTrackIssue,
    schemas.CallAnalysis,
    schemas.PlayInstance,
    schemas.Play,
    schemas.PlayCandidate,
    schemas.SourceRef,
    schemas.SkillGap,
    schemas.ScriptLine,
    schemas.ScriptSection,
    schemas.GeneratedScript,
    schemas.Drill,
    schemas.CoachingPlan,
    schemas.Deal,
    schemas.Risk,
    schemas.TrajectoryPoint,
    schemas.DealTrajectory,
    schemas.PersonaObjection,
    schemas.BuyerPersona,
    schemas.DojoTurn,
    schemas.CoachNudge,
    schemas.DojoScore,
    schemas.DojoSession,
    schemas.RepRow,
    schemas.TeamMetrics,
    schemas.Finding,
    schemas.Recommendation,
    schemas.CycleReport,
    schemas.PipelineEvent,
]

ENUMS = [
    schemas.SpeakerRole,
    schemas.CallOutcome,
    schemas.CallStatus,
    schemas.DealStage,
    schemas.CallStage,
    schemas.ObjectionCategory,
    schemas.PlayKind,
    schemas.RiskKind,
    schemas.Severity,
    schemas.Emotion,
    schemas.SkillAxis,
    schemas.StageKey,
    schemas.StageStatus,
]


def ts_type(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    """Translate one JSON Schema node into a TypeScript type."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]

    for key in ("anyOf", "oneOf"):
        if key in schema:
            parts = [ts_type(s, defs) for s in schema[key]]
            # Optional[X] arrives as anyOf[X, null]; collapse it.
            parts = list(dict.fromkeys(parts))
            return " | ".join(parts)

    if "enum" in schema:
        return " | ".join(f'"{v}"' for v in schema["enum"])

    kind = schema.get("type")
    if kind == "array":
        return f"{ts_type(schema.get('items', {}), defs)}[]"
    if kind == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            return f"Record<string, {ts_type(extra, defs)}>"
        return "Record<string, unknown>"
    if kind == "string":
        return "string"
    if kind in ("number", "integer"):
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "null":
        return "null";

    return "unknown"


def emit_interface(model: type[BaseModel], defs: dict[str, Any]) -> str:
    schema = model.model_json_schema(ref_template="#/$defs/{model}")
    defs.update(schema.get("$defs", {}))

    lines = []

    doc = (model.__doc__ or "").strip().split("\n\n")[0].replace("\n", " ").strip()
    if doc:
        lines.append(f"/** {doc} */")
    lines.append(f"export interface {model.__name__} {{")

    # Every property is emitted as required. JSON Schema marks a field optional
    # when it has a default, but `model_dump()` serializes defaults too -- so
    # the field is always present on the wire. Nullability is already carried
    # by `| null` on genuinely Optional fields. Marking defaulted fields `?`
    # would force the frontend to null-check values that can never be missing.
    for name, prop in schema.get("properties", {}).items():
        rendered = ts_type(prop, defs)
        description = prop.get("description")
        if description:
            lines.append(f"  /** {description} */")
        lines.append(f"  {name}: {rendered};")

    lines.append("}")
    return "\n".join(lines)


def emit_enum(enum_type) -> str:
    values = " | ".join(f'"{m.value}"' for m in enum_type)
    return f"export type {enum_type.__name__} = {values};"


def main() -> None:
    defs: dict[str, Any] = {}
    blocks = [HEADER]

    blocks.append("/* --- Enumerations -------------------------------------------------------- */\n")
    blocks.extend(emit_enum(e) for e in ENUMS)

    blocks.append("\n/* --- Domain models ------------------------------------------------------- */\n")
    seen: set[str] = set()
    for model in MODELS:
        if model.__name__ in seen:
            continue
        seen.add(model.__name__)
        blocks.append(emit_interface(model, defs))
        blocks.append("")

    blocks.append(EXTRA)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(blocks), encoding="utf-8")

    interfaces = len(seen)
    print(f"wrote {OUTPUT.relative_to(REPO)}: {interfaces} interfaces, {len(ENUMS)} enums")


if __name__ == "__main__":
    main()
