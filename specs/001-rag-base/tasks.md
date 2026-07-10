# Tasks: RAG Base (Text Only)

**Input**: `specs/001-rag-base/plan.md`, `specs/001-rag-base/spec.md`

**Tests**: `tests/test_rag_qa.py` is the phase gate (Constitution Principle I) — must pass 10/10 before Phase 2 starts.

## Tasks

- [X] T001 Create `app/config.py` (pydantic-settings): `OLLAMA_HOST`,
  `LLM_MODEL`, `EMBEDDING_MODEL`, `CHROMA_PERSIST_DIR`, `RETRIEVAL_MIN_SCORE`,
  reading from `.env` with the defaults in `.env.example`.
- [X] T002 Create `app/logging_utils.py`: `stage_timer(request_id, stage)`
  context manager that appends one JSONL record to `logs/latency.jsonl` per
  stage (AD-2).
- [X] T003 Create `app/rag/ingest.py`: load `faqs.json` (one chunk per entry)
  and `account_data.json` (one chunk per account balance summary + one per
  transaction), embed via `nomic-embed-text` through Ollama, upsert into a
  persistent Chroma collection at `CHROMA_PERSIST_DIR`. Runnable as
  `python -m app.rag.ingest`.
- [X] T004 Create `app/rag/retriever.py`: `retrieve(query, k=4) ->
  RetrievalResult(chunks, top_score)` querying the Chroma collection.
- [X] T005 Create `app/llm/client.py`: `answer(query, retrieval_result) ->
  AnswerResult(text, grounded)`. If `top_score < settings.retrieval_min_score`,
  return the fixed refusal string without calling the LLM (FR-004/AD-4).
  Otherwise call Ollama `llama3.2:3b` with retrieved chunks as context.
- [X] T006 Create `app/main.py`: FastAPI app with `POST /chat/text` wiring
  retriever + llm client, wrapped in `stage_timer` for `retrieval` and `llm`
  stages, returning `{answer, grounded, top_score}`.
- [X] T007 [P] Write `tests/test_rag_qa.py`: fixed 10-question set (5
  in-domain referencing real FAQ/account facts, 5 out-of-domain), asserting
  correct grounded answers and correct refusals respectively.
- [X] T008 Run `python -m app.rag.ingest`, then `pytest tests/test_rag_qa.py
  -v`; tune `RETRIEVAL_MIN_SCORE` in `.env`/`app/config.py` until 10/10 pass.
  Record the final threshold value and why in a short comment in
  `app/config.py`.
- [X] T009 (unplanned, found during manual testing beyond the fixed 10-question
  set) Fix a balance-recomputation hallucination: the LLM added/subtracted
  visible transaction amounts into the stated balance even though it was
  fabricating a materially wrong answer the fixed test set didn't happen to
  catch. Fixed via: (a) dropping per-transaction chunks in favor of one
  aggregated per-account transaction chunk (`app/rag/ingest.py`), (b)
  `temperature=0` greedy decoding for factual QA (`app/llm/client.py`), (c)
  grouping context into headed sections by chunk type instead of one flat
  blob (`app/llm/client.py::_build_context`), (d) an `account_kind`
  metadata filter so a "checking" query can no longer retrieve "savings"
  chunks and vice versa (`app/rag/ingest.py`, `app/rag/retriever.py`).
  Re-verified 10/10 on `tests/test_rag_qa.py` after each change.

## Phase gate result

10/10 passed on `tests/test_rag_qa.py` (2026-07-08). Phase 2 may begin.

## Post-implementation change log (2026-07-09 — recorded by the SDD audit)

Latency-optimization changes made after Phase 5 without going through this
spec first (a Principle I violation documented in
`docs/sdd-compliance-audit.md`):

- `SYSTEM_PROMPT` compressed (~200 → ~90 tokens) — CPU time-to-first-token
  scales with prompt length.
- Balance-chunk defensive text compressed; transactions chunk restructured
  as a numbered newline list (the semicolon-joined original caused a garbled
  answer that failed the re-run gate 9/10 — see audit R1).
- `retrieval_top_k` 4 → 3.
- Ollama `keep_alive=30m` on chat + embedding calls; `num_ctx` 2048;
  `temperature=0`, `num_predict=200`.
- Gate re-verified after all of the above: **10/10 (2026-07-09)**.
