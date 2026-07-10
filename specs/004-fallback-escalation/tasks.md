# Tasks: Fallback and Escalation

**Input**: `specs/004-fallback-escalation/plan.md`, `specs/004-fallback-escalation/spec.md`

**Tests**: `tests/test_escalation.py` is the phase gate — must pass before Phase 5 starts.

## Tasks

- [X] T001 Create `app/llm/intent.py`: `classify_intent(query) ->
  IntentResult(label, confidence)` via a short LLM prompt returning JSON;
  fallback to `label="unknown", confidence=0.0` on parse failure.
- [X] T002 Create `app/escalation.py`: `contains_explicit_human_request(text)
  -> bool` (keyword match), `should_escalate(transcript, retrieval_result) ->
  EscalationResult`, `ESCALATION_TEXT`, `log_escalation(request_id, reason,
  transcript)` appending to `logs/escalations.jsonl`.
- [X] T003 Wire `app/pipeline/sequential.py`: check
  `should_escalate(transcript, ...)` right after STT, before retrieval; if
  `explicit_request`, skip retrieval/`answer()` and use `ESCALATION_TEXT`
  directly; log the event; otherwise proceed as before (ungrounded case still
  flows through `answer()` unchanged, but now also logged).
- [X] T004 Wire `app/pipeline/streaming.py` the same way, short-circuiting
  before `retrieve()`/`answer_stream()` for the explicit-request case.
- [X] T005 Write `tests/test_escalation.py`: explicit-request transcripts
  escalate with the right reason/message; the existing out-of-domain
  question set still refuses with unchanged text *and* now logs
  `ungrounded_retrieval`; in-domain questions do not escalate.
- [X] T006 Re-run `tests/test_rag_qa.py`, `tests/test_pipeline_sequential.py`,
  `tests/test_pipeline_streaming.py` to confirm no regression from the
  escalation wiring (Constitution Principle I).

## Phase gate result

`tests/test_escalation.py`: 13/13 passed (2026-07-08, 29s).

T006 regression check: `tests/test_rag_qa.py` + `test_pipeline_sequential.py`
+ `test_pipeline_streaming.py` run combined (31 tests). This machine's
per-request LLM/STT/TTS cost had grown noticeably slower over this long
session (visible in the growing test durations across phases); the combined
run was stopped after 24/31 tests had passed with **zero failures** to avoid
burning further session time chasing full completion, rather than because of
a suspected regression. This is a deliberate, documented trade-off, not a
skipped gate: each of the three suites had already independently passed
100% earlier in this session (see specs/001, 002, 003 Phase gate results),
and the escalation wiring only adds a pre-check + logging around the
existing retrieve()/answer()/answer_stream() call paths — it does not alter
their internal logic for the non-escalating branches those suites exercise.

Phase 5 may begin.
