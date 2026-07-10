# Feature Specification: Documentation and Metrics

**Feature Branch**: `005-docs-metrics`

**Created**: 2026-07-08

**Status**: Implemented (2026-07-08) — see tasks.md Phase gate result

**Input**: PRD.md §6.1 Phase 5; SPEC_Voice_RAG_Bot.md Fase 5 (Documentación y métricas), §9 acceptance criteria

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An interviewer (or Andre) can read the README and understand the whole project (Priority: P1)

Someone opens the GitHub repository cold. The README explains what the
project is, shows the architecture, shows real latency numbers, and
explicitly explains the streaming design decision and why it matters —
without needing to read the source SPEC or ask Andre questions first.

**Why this priority**: This is literally the deliverable the SPEC was
written to produce (SPEC §11) — a defensible artifact for a specific
interview question.

**Independent Test**: Read `README.md` top to bottom with no other context
and confirm it answers: what is this, how is it built, how fast is it, why
does streaming matter, what would change for production.

**Acceptance Scenarios**:

1. **Given** the finished repository, **When** README.md is read, **Then**
   it contains an architecture diagram, a latency metrics section with real
   numbers, and an explicit "Design Decisions" section covering streaming.
2. **Given** the finished repository, **When** `pytest` is run from a clean
   checkout (after `uv sync` and `python -m app.rag.ingest`), **Then** all
   phase test suites pass.

---

### User Story 2 - The demo page loads and a WebSocket handshake succeeds (Priority: P2)

Someone runs `uvicorn app.main:app` and opens `frontend/index.html` in a
browser. The page loads, shows the demo UI, and successfully opens a
WebSocket connection to `/ws/voice` — proving the frontend/backend contract
works, even though live microphone testing itself is a manual follow-up
(PRD Open Question 1).

**Why this priority**: Confirms the "simple frontend with mic capture"
requirement (SPEC §10) is real and wired, not just described.

**Independent Test**: Load the page via the Chrome browser tool and confirm
no console errors and a successful WebSocket connection.

**Acceptance Scenarios**:

1. **Given** the FastAPI server running locally, **When**
   `frontend/index.html` is opened, **Then** the page renders without
   console errors and the WebSocket status indicator shows "connected."

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `README.md` MUST be entirely in English and MUST include: a
  project overview, an architecture diagram (Mermaid), setup/run
  instructions, the latency metrics table/chart from
  `docs/latency/report.md`, a "Design Decisions" section explaining
  streaming's value using this project's own numbers (including the honest
  STT-confound finding from 003-streaming-e2e), and a "Future Work" section
  covering real telephony/hosted-provider integration (PRD §5/§6.2 Non-Goals).
- **FR-002**: A minimal static frontend (`frontend/index.html`, `app.js`,
  `styles.css`) MUST exist, capturing microphone audio via
  `MediaRecorder`/`getUserMedia`, resampling/chunking it to 16kHz PCM16
  frames, and streaming them to `/ws/voice`, rendering partial transcripts,
  streamed answer text, and playing back streamed audio chunks as they
  arrive.
- **FR-003**: The full automated test suite (`tests/test_rag_qa.py`,
  `tests/test_pipeline_sequential.py`, `tests/test_pipeline_streaming.py`,
  `tests/test_escalation.py`) MUST pass together as the final project gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `pytest` (full suite) passes.
- **SC-002**: `uvicorn app.main:app` starts without error and
  `frontend/index.html`, opened in a real browser, connects to `/ws/voice`
  without console errors (verified manually with the Chrome browser tool in
  this environment).
- **SC-003**: README review checklist (architecture diagram present, latency
  numbers present and sourced from `docs/latency/report.md`, Design
  Decisions section present, Future Work section present, entirely English).

## Assumptions

- Live browser microphone capture cannot be exercised end-to-end by an
  automated agent in this environment (no way to grant OS/browser mic
  permission programmatically); SC-002 verifies the page loads and the
  WebSocket handshake succeeds, and the README explicitly tells Andre this is
  a manual follow-up step for him to try locally.
