# Feature Specification: STT/TTS Sequential (No Streaming)

**Feature Branch**: `002-stt-tts-sequential`

**Created**: 2026-07-08

**Status**: Implemented (2026-07-08) — 10/10 on `tests/test_pipeline_sequential.py`

**Input**: PRD.md FR-1, FR-5; SPEC_Voice_RAG_Bot.md Fase 2 (Agregar STT/TTS sin streaming)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Full audio-in, audio-out round trip (Priority: P1)

A user's recorded question (as an audio file — self-generated or later a real
mic recording) goes in one end, and a spoken audio answer comes out the other,
using the Phase 1 RAG pipeline in between. No streaming yet — each stage
completes fully before the next starts.

**Why this priority**: Proves the whole pipeline shape works end to end before
Phase 3 adds the harder streaming requirement on top of it.

**Independent Test**: Feed a `.wav` file into the sequential pipeline function
and check the output is a valid `.wav` file whose transcript-and-answer chain
matches what Phase 1's text pipeline would produce for the same question text.

**Acceptance Scenarios**:

1. **Given** a `.wav` recording of an in-domain question, **When** it is run
   through the sequential pipeline, **Then** the output audio, when
   transcribed back, states the correct fact.
2. **Given** a `.wav` recording of an out-of-domain question, **When** it is
   run through the sequential pipeline, **Then** the output audio states the
   refusal.

---

### Edge Cases

- What happens when STT produces an empty/near-empty transcript (silence or
  noise)? → treat as an empty query per Phase 1's existing handling (asks for
  clarification), does not call the LLM with nothing.
- What happens when the input audio is not 16kHz mono (browser mic capture
  formats vary)? → STT stage resamples/converts as needed before transcription.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST transcribe a `.wav` audio file to text using
  faster-whisper (`base.en`), non-streaming (full-file transcription).
- **FR-002**: System MUST synthesize a text answer to a `.wav` audio file
  using Piper (`en_US-lessac-medium`), non-streaming (full-text synthesis).
- **FR-003**: System MUST expose a sequential pipeline function
  `run_sequential(audio_path) -> PipelineResult(transcript, answer_text,
  grounded, output_audio_path)` that calls STT → Phase 1 retrieval → Phase 1
  LLM → TTS in strict sequence, each stage wrapped in `stage_timer`.
- **FR-004**: System MUST expose the sequential pipeline via a FastAPI REST
  endpoint (`POST /chat/audio`, multipart file upload) returning the answer
  text and a link/bytes to the output audio.

### Key Entities

- **PipelineResult**: `transcript` (str), `answer_text` (str), `grounded`
  (bool), `output_audio_path` (str) — one full request's worth of results.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Self-generated test audio for all 10 Phase 1 questions
  (`scripts/generate_test_audio.py`, via Piper) produces correct/refused
  answers when run through `run_sequential`, matching Phase 1's text-pipeline
  behavior (`tests/test_pipeline_sequential.py`).
- **SC-002**: Every request's STT/retrieval/LLM/TTS stage timings are present
  in `logs/latency.jsonl` — this is the Phase 3 before/after baseline.

## Assumptions

- Real browser microphone capture is not exercised by the automated test
  suite in this environment (no way to grant mic permission programmatically);
  self-generated audio via Piper stands in for it, per PRD Open Question 1.
  Live mic testing against the demo frontend is a manual follow-up.
- `base.en` is accurate enough for this project's short, domain-specific
  utterances; no fine-tuning planned.
