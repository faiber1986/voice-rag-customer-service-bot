# Implementation Plan: RAG Base (Text Only)

**Branch**: `001-rag-base` | **Date**: 2026-07-08 | **Spec**: `specs/001-rag-base/spec.md`

**Input**: Feature specification from `specs/001-rag-base/spec.md`

## Summary

Build the text-only retrieval + generation pipeline: ingest the JSON knowledge
base into a persistent Chroma collection, retrieve top-k chunks with a
similarity score, and generate a grounded answer via local Ollama, refusing
when retrieval confidence is too low. Exposed as one FastAPI endpoint. No
audio in this phase.

## Technical Context

**Language/Version**: Python 3.12.12 (`.venv` via `uv`)

**Primary Dependencies**: FastAPI, ChromaDB, `ollama` client (`llama3.2:3b` +
`nomic-embed-text`), pydantic-settings

**Storage**: ChromaDB persistent client, `data/chroma/`

**Testing**: pytest (`tests/test_rag_qa.py`)

**Target Platform**: local Windows dev machine, Ollama running as a local
service on `localhost:11434`

**Project Type**: single backend service (FastAPI)

**Performance Goals**: not the focus of this phase (see Phase 3) — retrieval +
LLM call should complete in a few seconds on CPU, logged but not optimized yet.

**Constraints**: zero hosted API keys (Constitution Principle IV); zero
hallucination on out-of-domain queries (Constitution Principle II).

**Scale/Scope**: single demo account, ~12 FAQ entries, ~10 transactions — small
fixed corpus, no scale concerns.

## Constitution Check

*GATE: Must pass before implementation.*

- Principle I (phase-gated): this plan and `tasks.md` exist before code is
  written. ✅
- Principle II (no hallucination): FR-004 implements the refusal branch (AD-4
  in `architecture.md`). ✅
- Principle III (latency measured): FR-006 wires `logging_utils.py` from this
  phase onward, even though optimization is Phase 3's job. ✅
- Principle IV (local-first): Ollama + Chroma only, no hosted keys. ✅
- Principle V (English only): all knowledge base content, code, logs, tests in
  English. ✅

No violations — Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-rag-base/
├── plan.md              # this file
└── spec.md
```

(`research.md` / `data-model.md` / `contracts/` skipped — scope is small
enough that `architecture.md`'s existing Capability → Architecture Map and
this plan's Key Entities section cover it; adding them would be padding per
Constitution Principle VI.)

### Source Code (repository root)

```text
app/
├── config.py              # pydantic-settings: OLLAMA_HOST, LLM_MODEL,
│                           #   EMBEDDING_MODEL, CHROMA_PERSIST_DIR,
│                           #   RETRIEVAL_MIN_SCORE
├── logging_utils.py         # stage_timer() + JSONL writer (AD-2)
├── rag/
│   ├── ingest.py             # loads faqs.json + account_data.json -> Chroma
│   ├── retriever.py          # retrieve(query, k) -> (chunks, top_score)
│   └── knowledge_base/       # faqs.json, account_data.json (already authored)
├── llm/
│   └── client.py              # generate(query, context) -> answer;
│                               #   refusal branch when top_score < threshold
└── main.py                  # FastAPI app, POST /chat/text

tests/
└── test_rag_qa.py           # 10-question in/out-of-domain test set
```

**Structure Decision**: single-project layout (matches `architecture.md`
Structural Seed) — no separate `src/`/`backend/` split needed since this is
one FastAPI service, not a multi-app repo.

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.*
