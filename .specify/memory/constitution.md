# Voice-RAG Customer Service Bot Constitution

## Core Principles

### I. Phase-Gated, Spec-Driven Development
Every phase (001-rag-base, 002-stt-tts-sequential, 003-streaming-e2e,
004-fallback-escalation, 005-docs-metrics) is specified (`spec.md`), planned
(`plan.md`), and broken into tasks (`tasks.md`) *before* implementation
starts, and is validated against its own acceptance criteria before the next
phase begins. No phase starts implementation while the previous phase's tests
are failing.

### II. No Hallucination (NON-NEGOTIABLE)
The LLM answers only from retrieved context. When retrieval confidence is
below the configured threshold, the system returns an explicit "I don't have
that information" style refusal — never a fabricated financial fact. This is
tested on every phase that touches answer generation via a fixed 10-question
set (5 in-domain / 5 out-of-domain); 0 hallucinations is the only passing
result.

### III. Latency Is Measured, Not Assumed
Every pipeline stage (STT, retrieval, LLM, TTS) is timed and logged
(start/end/first-partial timestamps) for every request. Phase 3's streaming
claim is only valid if backed by a real before/after comparison against the
Phase 2 sequential baseline, generated from actual logged data — never an
estimate.

### IV. Local-First, Provider-Agnostic
The system runs entirely on local/free components by default (Ollama,
ChromaDB, faster-whisper, Piper) — no hosted API key is required to run or
test it. Every stage that talks to a model runtime does so through a thin
wrapper module (`app/llm/client.py`, `app/voice/stt.py`, `app/voice/tts.py`)
so a hosted provider could be swapped in later without touching pipeline or
API code.

### V. English Source, Bilingual Surface (amended v1.1.0)
All code, comments, log messages, tests, documentation, and knowledge base
content are in English — no mixed-language strings in the codebase. The
*user-facing conversation surface* (spoken input, spoken/displayed answers,
fixed refusal/escalation messages, demo-page UI copy) may additionally be
offered in Spanish as an explicit, user-selected mode (Feature 006). The
retrieval pipeline remains English-internal: non-English speech is translated
to English before retrieval so the Principle II gate and its tuned threshold
stay valid — measured evidence: Spanish-query cross-lingual retrieval scored
0.47-0.54 against the English KB, below the 0.62 grounding threshold and
indistinguishable from out-of-domain queries.

*Amendment note (2026-07-09, v1.0.0 → v1.1.0):* the original principle
("English Only, End to End") reflected the source SPEC's MVP non-goal of
multi-language support. The project owner has explicitly requested a
Spanish/English option post-MVP; per this constitution's Governance section
the change is recorded here and implemented through
`specs/006-language-and-theme/`.

### VI. Simplicity and Test-Backed Behavior
Each phase adds the smallest implementation that satisfies its spec's
acceptance criteria — no speculative abstractions for hypothetical future
providers or phases. Every functional requirement implemented has at least
one corresponding automated test (`tests/test_*.py`) that can be run with
`pytest`.

## Technology Constraints

- Python 3.12 (via `uv`), not the system default 3.14 — ML wheel
  compatibility (chromadb, faster-whisper, onnxruntime).
- `av==13.1.0` and `setuptools<81` are pinned; see `architecture.md` Stack
  table for why — do not bump without re-verifying against this machine's
  Windows Application Control policy and the `pkg_resources` removal.
- Backend: FastAPI + WebSockets (`uvicorn`). Frontend: static HTML/JS with
  `MediaRecorder`/WebRTC mic capture — no frontend framework/build step.
- Vector DB: ChromaDB, persisted locally under `data/chroma/`.
- All simulated account/transaction data and FAQ content is synthetic —
  never real customer data (no real telephony, no real auth in v1, per
  `PRD.md` §5 Non-Goals).

## Development Workflow

- Source of truth order: `SPEC_Voice_RAG_Bot.md` (original) →
  `_bmad-output/planning-artifacts/PRD.md` + `architecture.md` (BMAD
  prototyping) → `specs/NNN-*/{spec.md,plan.md,tasks.md}` (spec-kit,
  per-phase) → code. A change to requirements is reflected upstream first.
- Each phase's spec-kit folder is self-contained: `spec.md` (what/why),
  `plan.md` (how, referencing `architecture.md`'s AD-N decisions it applies),
  `tasks.md` (ordered, checkable implementation tasks).
- A phase is "done" when its `tasks.md` items are complete and its dedicated
  `pytest` file passes.

## Governance

This constitution and `architecture.md` govern all phase specs and plans;
where they conflict, `architecture.md`'s Invariants & Rules (AD-N) win for
technical decisions and this constitution wins for process/workflow
decisions. Amendments require updating this file and noting the change in
the relevant phase's `spec.md` if it affects already-written requirements.

**Version**: 1.1.0 | **Ratified**: 2026-07-08 | **Last Amended**: 2026-07-09 (Principle V: bilingual conversation surface)
