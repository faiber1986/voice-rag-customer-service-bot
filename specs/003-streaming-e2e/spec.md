# Feature Specification: Streaming End-to-End

**Feature Branch**: `003-streaming-e2e`

**Created**: 2026-07-08

**Status**: Implemented (2026-07-08) — 11/11 on `tests/test_pipeline_streaming.py`; see tasks.md Phase gate result for the honest latency finding

**Input**: PRD.md FR-1, FR-4, FR-5, SM-1, SM-2; SPEC_Voice_RAG_Bot.md Fase 3 (Streaming end-to-end)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The bot starts speaking before it's finished thinking (Priority: P1)

A user asks a question over the WebSocket voice endpoint. Instead of waiting
for STT to fully finish, then retrieval, then the complete LLM answer, then
the complete TTS audio — each stage starts producing output as soon as it has
enough input, and downstream stages consume it incrementally. The user hears
the first words of the answer while the rest is still being generated.

**Why this priority**: This is the project's headline claim (SPEC §11) — it
must be demonstrably true with real numbers, not just architecturally present.

**Independent Test**: Feed the same audio fixture used in Phase 2 through the
streaming pipeline and the sequential pipeline, and compare logged
time-to-first-audio-byte between the two using `scripts/latency_report.py`.

**Acceptance Scenarios**:

1. **Given** an in-domain question audio fixture, **When** run through the
   streaming pipeline, **Then** partial transcripts are emitted before
   end-of-turn, LLM tokens are emitted incrementally, and audio chunks are
   emitted per completed sentence before the full answer text is generated.
2. **Given** the same audio fixture run through both Phase 2 (sequential) and
   Phase 3 (streaming) pipelines, **When** comparing logged
   `time_to_first_partial_ms` for the `tts` stage, **Then** streaming's value
   is measurably lower than sequential's total `stt`+`retrieval`+`llm`+`tts`
   duration before any audio existed.

---

### Edge Cases

- What happens when the LLM response has no sentence-ending punctuation
  before the stream ends (e.g. a very short answer)? → the trailing partial
  sentence is flushed to TTS when the LLM stream completes, not dropped.
- What happens when VAD never detects a clear end-of-turn (continuous noise)?
  → a maximum utterance duration cap forces end-of-turn (documented constant),
  preventing an unbounded wait — matches RNF-03's "does not wait excessively."
  guidance from the source spec.
- What happens when retrieval is ungrounded? → the refusal path (FR-004 in
  001-rag-base) still applies; `answer_stream` yields the refusal text as a
  single chunk rather than token-by-token, and it is still synthesized and
  streamed back as one audio chunk.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST detect end-of-turn from a stream of audio frames
  using VAD (`webrtcvad`), not a fixed oversized silence timeout, per
  Constitution/RNF-03.
- **FR-002**: System MUST produce partial transcripts from the growing audio
  buffer at a bounded interval while the user is still speaking, before
  end-of-turn is declared.
- **FR-003**: System MUST stream LLM tokens as they are generated
  (`app/llm/client.py::answer_stream`, already built in 001-rag-base).
- **FR-004**: System MUST synthesize and emit TTS audio per completed sentence
  chunk of the LLM's streamed output, before the full response text is
  available — reusing `app/voice/tts.py`'s per-chunk synthesis, not waiting
  for the complete answer.
- **FR-005**: System MUST expose this pipeline over a FastAPI WebSocket
  endpoint (`/ws/voice`) that accepts binary PCM16 16kHz mono audio frames and
  emits JSON events: `partial_transcript`, `final_transcript`, `answer_token`,
  `audio_chunk` (base64 WAV bytes), `done`.
- **FR-006**: System MUST log every stage (`stt`, `retrieval`, `llm`, `tts`)
  with `pipeline: "streaming"` and, where applicable, `first_partial_ts`
  distinct from `end_ts`, so `scripts/latency_report.py` can compute the
  before/after comparison against Phase 2's `pipeline: "sequential"` records.

### Key Entities

- **StreamEvent**: one JSON message sent to the client — `type` plus
  type-specific payload (`text`, `audio_base64`, `grounded`, `top_score`).
- **EndOfTurnDetector**: stateful VAD wrapper tracking trailing silence
  duration across frames to decide when a turn has ended.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `pytest tests/test_pipeline_streaming.py` passes for all 10
  fixture questions, matching Phase 1/2's correctness properties (grounded +
  correct fact, or refusal) when reassembling the full streamed answer.
- **SC-002**: `scripts/latency_report.py` produces a report/chart showing
  streaming's time-to-first-audio-byte is measurably lower than sequential's
  time-to-any-audio, using real logged data from this project's own test
  runs — this is SPEC §9/§11's central interview artifact.
- **SC-003**: Perceived latency (SM-1) is documented even if it misses the
  <1.5s target on this CPU-only local stack — the real number, not an
  estimate.

## Assumptions

- Real-time pacing of incoming audio frames is not required for the automated
  test (frames are fed as fast as the test can produce them) — the streaming
  *architecture* is what's under test, not wall-clock realism of a live mic.
  Live mic testing against the frontend is a manual follow-up (PRD Open
  Question 1), validated separately in Phase 5 by confirming the frontend
  loads and the WebSocket handshake succeeds.
- A maximum utterance duration cap (documented constant in
  `app/voice/vad.py`) exists as a safety net if VAD never detects silence.
