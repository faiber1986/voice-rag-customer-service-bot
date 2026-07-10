# Implementation Plan: Fallback and Escalation

**Branch**: `004-fallback-escalation` | **Date**: 2026-07-08 | **Spec**: `specs/004-fallback-escalation/spec.md`

**Input**: Feature specification from `specs/004-fallback-escalation/spec.md`

## Summary

Add intent classification (observability) and a single cross-cutting
escalation decision point used identically by both pipelines
(architecture.md AD-5), covering explicit human requests (new, short-
circuits generation) and ungrounded retrieval (existing behavior, now also
logged as a simulated handoff).

## Technical Context

**Language/Version**: Python 3.12.12

**Primary Dependencies**: existing Ollama LLM client (intent prompt reuses
`app/llm/client.py`'s `_client`)

**Storage**: `logs/escalations.jsonl` (new, JSONL, same pattern as
`logs/latency.jsonl`)

**Testing**: `pytest tests/test_escalation.py`

**Target Platform**: local Windows dev machine

**Project Type**: single backend service (extends Phase 1-3's FastAPI app)

**Performance Goals**: explicit-request escalation should be *faster* than a
normal answer (skips retrieval + generation entirely) — a nice side effect
of FR-004, not a formal target.

**Constraints**: must not change 001-rag-base's existing refusal text/logic
for ungrounded retrieval — only adds logging around it (Constitution
Principle I: don't regress a passed phase gate).

**Scale/Scope**: single demo account, unchanged.

## Constitution Check

- Principle I (phase-gated): spec/plan/tasks precede implementation; existing
  Phase 1-3 tests re-run unchanged to confirm no regression. ✅
- Principle II (no hallucination): explicit-request path never calls the LLM
  for open-ended generation; ungrounded path is unchanged from AD-4. ✅
- Principle III (latency measured): escalation short-circuit is timed like
  any other stage (llm/tts stages still wrapped in `stage_timer`, just with
  near-zero generation cost for the explicit-request case). ✅
- Principle IV (local-first): intent classification reuses the existing
  local Ollama client. ✅
- Principle V (English only): escalation message and log content in
  English. ✅
- Principle VI (simplicity): the Assumptions section documents why intent
  confidence is observability-only rather than a third escalation trigger —
  a deliberate, justified scope narrowing, not an oversight.

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/004-fallback-escalation/
├── plan.md
└── spec.md
```

### Source Code (repository root)

```text
app/
├── llm/
│   └── intent.py             # classify_intent(query) -> IntentResult
├── escalation.py              # should_escalate(), log_escalation(), ESCALATION_TEXT
└── pipeline/
    ├── sequential.py          # + escalation check before answer()
    └── streaming.py           # + escalation check before retrieve()/answer_stream()

tests/
└── test_escalation.py
```

**Structure Decision**: extends the existing single-project layout; matches
`architecture.md`'s AD-5 (escalation lives in one cross-cutting module, not
duplicated per pipeline).

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.*
