# Architecture

## The shape of the system

```
                                  BROWSER
                    Next.js 15 · React 19 · three.js
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
          REST reads          SSE: pipeline           SSE: dojo turn
              │                      │                      │
              └──────────────────────┼──────────────────────┘
                                     │
                                 FastAPI
                                     │
        ┌────────────────────────────┴────────────────────────────┐
        │                     ANALYSIS DAG                        │
        │                                                         │
        │   ┌───────────────────┐                                 │
        │   │ Transcriptionist  │  Qwen ASR + diarization,         │
        │   │                   │  then decides which voice        │
        │   └─────────┬─────────┘  is the salesperson              │
        │             │                                           │
        │   ┌─────────▼─────────┐                                 │
        │   │    Prosodist      │  NO LLM. Pure arithmetic over    │
        │   │                   │  millisecond timestamps.         │
        │   └─────────┬─────────┘                                 │
        │             │                                           │
        │   ┌─────────▼─────────┐                                 │
        │   │    Anatomist      │  Structure, objections, MEDDIC,  │
        │   │                   │  every claim citing a segment    │
        │   └─────────┬─────────┘                                 │
        │             │                                           │
        │   ┌─────────▼─────────┐        ┌──────────────────┐     │
        │   │    Playwright     │───────▶│  moment index    │     │
        │   │                   │        │  (embeddings)    │     │
        │   └─────────┬─────────┘        └────────┬─────────┘     │
        │             │                           │               │
        │   ┌─────────▼─────────┐        ┌────────▼─────────┐     │
        │   │     Analyst       │        │      Coach       │     │
        │   │  deal trajectory  │        │   RAG retrieval  │     │
        │   │  risk · report    │        │  grounded script │     │
        │   └───────────────────┘        └──────────────────┘     │
        └─────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
            SQLite (local)                    Object storage
            Postgres + pgvector (cloud)       filesystem / OSS
```

Six agents, each with a single job and a typed Pydantic output contract. The
graph is explicit rather than emergent: a single call is inherently sequential
(you cannot read anatomy before you have a transcript), and the real
parallelism is across calls, which `run_batch` fans out under a semaphore
bounded by provider rate limits rather than by CPU.

---

## Layering

Imports flow strictly downward. There are no cycles.

```
schemas/      the contract. depends on nothing.
   ↑
metrics/      deterministic measurement + cross-call aggregation
   ↑
store/        tables, typed repository, vector search
   ↑
providers/    Alibaba Cloud clients behind Protocols, with offline twins
   ↑
agents/       the six specialists + citation enforcement
   ↑
pipeline/     DAG orchestration + the SSE event bus
   ↑
routers/      HTTP
```

`analytics` lives under `metrics` and `evidence` under `agents` for exactly
this reason: putting them in `pipeline` created a cycle between `pipeline` and
`agents`, and the fix was structural rather than a lazy import.

---

## The three decisions that carry the design

### 1. Measurement is arithmetic, not inference

`salix/metrics/engine.py` consults no language model. Everything is computed
from diarized millisecond timestamps, which is what makes the numbers
defensible in a pipeline review — and unit-testable against fixtures computed
by hand.

Three details separate it from a naive implementation:

- **Overlapping speech is unioned, not summed.** People talk over each other.
  Naive summation makes `rep + buyer + silence` exceed the call duration.
- **A backchannel does not end a monologue.** A two-word "mm-hmm" from the
  buyer is an acknowledgement, not a handover. Without this rule,
  longest-monologue collapses to noise on any engaged call — and it is
  precisely the metric that exposes a rep who presents instead of converses.
- **Interruptions are excluded from patience.** A rep cutting in 500ms early
  produces a *negative* gap. Averaging it in would drag the mean toward zero
  and make an interrupter look attentive.

Opinions about those facts live separately, in `scorecard.py`. Retuning a
benchmark never touches measurement code.

### 2. Every claim carries its evidence

`salix/agents/evidence.py` walks any Pydantic object, finds every nested
`EvidenceRef`, and checks the cited segment id against the real transcript.

- Valid citations are **hydrated** with the verbatim quote and timestamp, so
  the UI renders a finding beside its proof without a second lookup.
- Invalid ones are **fabrications**. The agent gets one repair attempt with the
  specific bad ids *and* the list of legal ones — which is far more effective
  than simply retrying.
- Anything still unresolvable is **pruned**, not displayed. A citation the rep
  cannot follow is worse than no citation.

`citation_coverage()` is surfaced on the call page so a reviewer can see how
well grounded an analysis is.

### 3. Failure is per stage, never per page

Only transcription is fatal, because without it there is nothing to analyse.
Everything downstream degrades:

| Stage fails | Result |
|---|---|
| Transcribe | Call marked failed with the reason |
| Anatomy | Transcript + metrics + scorecard still land; no interpretation |
| Plays | Call is complete; contributes nothing to the playbook |
| Trajectory | Call is complete; deal health not refreshed |

Artifacts persist the moment each stage completes, so the call page is useful
while the language models are still working.

---

## Structured output

Getting reliable typed output from a language model needs three things, all in
`providers/dashscope_llm.py`:

1. The JSON Schema in the prompt, plus `response_format={"type":"json_object"}`
   so decoding is constrained at generation time.
2. Tolerant extraction — models still wrap JSON in prose or a markdown fence.
3. A **repair loop that hands the model the validator's own complaint**. In
   practice this converts most first-attempt failures into second-attempt
   successes.

---

## Retrieval

Moments — a play landing, an objection well handled, a run of discovery
questions, a close — are embedded with `text-embedding-v4` and stored with
enough denormalised context to be useful straight out of a search result.

The Coach's queries do the interesting work:

```python
await repo.search_moments(
    session, org_id, embedding,
    kind="objection_handling",
    outcome="won",            # only learn from calls that closed
    exclude_rep_id=rep.id,    # never teach a rep their own habits back
    k=4, diversify=True,      # MMR, not plain top-k
)
```

MMR matters more than it looks. A rep who is good at something is good at it
repeatedly, so plain top-k returns five paraphrases of one moment. MMR trades a
little relevance for coverage and returns five *different* ways the objection
was handled.

### Why brute-force cosine

A sales org's entire history is tens of thousands of moments. A 20k × 1024
float32 matrix is 80 MB and numpy scores it in single-digit milliseconds.
Filtering happens in SQL *before* scoring, so the candidate set is already
narrow. An approximate index would add operational weight and recall loss to
solve a problem nobody here has. `store/vectors.py` is the seam — swapping in
pgvector's `<=>` for the cloud deployment changes that module and nothing else.

---

## Storage

Rich nested objects are persisted as JSON documents validated by their Pydantic
model, with only the columns actually queried promoted and indexed.

This is a deliberate trade. A call analysis is six levels deep; mapping it onto
relational tables would create a second schema that drifts from the first. One
contract is worth more here than third normal form. `store/repo.py` takes and
returns Pydantic models exclusively, so the decision stays inside that module.

The `moments` table is the vector store: a BLOB of float32 on SQLite, a
`vector(1024)` column on Postgres, identical bytes either way.

---

## The provider seam

Nothing in `agents/` or `pipeline/` imports an SDK. Everything goes through a
`Protocol` in `providers/base.py`, and `build_providers()` picks the
implementation once at startup:

| `SALIX_PROVIDER_MODE` | Behaviour |
|---|---|
| `auto` (default) | Live if `DASHSCOPE_API_KEY` is present, offline otherwise |
| `live` | Always Alibaba Cloud |
| `mock` | Always offline, no network |

The offline twins are not stubs. `MockLLM.structured()` walks any Pydantic
model and constructs a schema-valid instance respecting enums, numeric bounds
and required list lengths — so a *new* schema can never break offline mode —
and for the schemas where realism matters it reads the actual transcript and
produces something a person would recognise. `MockEmbeddings` are hash-derived,
deterministic and correctly normalised, so the whole retrieval path is
exercisable and testable with no network.

---

## The Conversation Helix

`web/components/helix/geometry.ts` maps three properties of the conversation
onto three properties of a ribbon:

| Ribbon | Conversation |
|---|---|
| Drift (vertical) | Rises when the rep holds the floor, falls when the buyer does |
| Twist | Rotates in proportion to how often the floor changes hands |
| Width | Follows speech density; silence pinches to a thread |

Colour lerps between the rep and buyer hues along the same axis.

The consequence is that a three-minute feature monologue and a real discovery
call are distinguishable across a room: one is a flat plank pinned to the
ceiling, the other corkscrews along the axis. That is the argument for 3D here
— it solves a comprehension problem rather than decorating one.

WebGL is not assumed. `HelixFlat` renders the same three signals in SVG and
takes over when a context is unavailable or lost, and it is what prints.

---

## Type safety across the boundary

`api/scripts/gen_types.py` compiles the Pydantic models into
`web/lib/types.ts` by walking their JSON Schema — which is what actually
crosses the wire, computed fields included.

Every property is emitted as **required**. JSON Schema marks a field optional
when it has a default, but `model_dump()` serializes defaults too, so the field
is always present on the wire; nullability is already carried by `| null`.
Marking defaulted fields `?` would force the frontend to null-check values that
can never be missing.

---

## Testing

185 tests, weighted toward the parts where correctness is checkable:

| Area | What is pinned |
|---|---|
| Metrics engine | Every value against hand-computed fixtures; backchannel and interruption edge cases |
| Vector search | Cosine correctness, dimension mismatch, MMR diversity |
| Providers | Offline mode produces a valid instance for *any* schema |
| Persistence | Typed round-trips, idempotent upserts, filtered retrieval |
| Pipeline | The full DAG end to end; per-stage degradation |
| Coach attribution | A shared play cited without a call resolves to nothing rather than to the wrong colleague |
| API | Every endpoint against a really-seeded database |

Two tests exist purely to protect the demo's honesty: the designated top
performer must measure best, and the struggling rep must measure worst. If an
edit to the seed corpus inverted that, the suite fails rather than the product
quietly asserting the opposite of the truth.
