# Implementation Plan: Streaming End-to-End

**Branch**: `003-streaming-e2e` | **Date**: 2026-07-08 | **Spec**: `specs/003-streaming-e2e/spec.md`

**Input**: Feature specification from `specs/003-streaming-e2e/spec.md`

## Summary

Add a VAD-driven end-of-turn detector and an async-generator streaming
pipeline that reuses Phase 1/2's stage functions (AD-3) but overlaps them:
periodic partial re-transcription while the user speaks, token-by-token LLM
streaming, and per-sentence TTS synthesis that starts before the LLM
finishes. Exposed over a new WebSocket endpoint. Finishes with a latency
report comparing this phase's logged numbers against Phase 2's baseline.

## Technical Context

**Language/Version**: Python 3.12.12

**Primary Dependencies**: `webrtcvad` (VAD), existing faster-whisper/Piper/
Ollama wrappers, FastAPI `WebSocket`

**Storage**: no new storage; reuses `logs/latency.jsonl` with a new
`pipeline: "streaming"` tag (see `app/logging_utils.py`)

**Testing**: `pytest tests/test_pipeline_streaming.py`, feeding fixture audio
(resampled to 16kHz PCM16 and chunked into 20ms frames) through an async
generator that stands in for live WebSocket frames

**Target Platform**: local Windows dev machine, CPU inference

**Project Type**: single backend service (extends Phase 1/2's FastAPI app)

**Performance Goals**: SM-1 (<1.5s perceived latency target, real number
documented regardless of outcome), SM-2 (streaming verifiable in logs)

**Constraints**: must not duplicate stage logic — `app/pipeline/streaming.py`
calls the same `app/rag`, `app/llm`, `app/voice` functions as
`app/pipeline/sequential.py` (AD-3); faster-whisper has no native incremental
decoder, so "streaming STT" here means periodic re-transcription of a growing
16kHz PCM16 buffer, not token-level incremental decoding — documented as a
Design Decision in the Phase 5 README, not hidden.

**Scale/Scope**: single demo account/knowledge base, unchanged from Phase 1/2.

## Constitution Check

- Principle I (phase-gated): spec/plan/tasks precede implementation. ✅
- Principle II (no hallucination): `answer_stream` reuses the same
  ungrounded-refusal gate as `answer` (001-rag-base AD-4) — no new
  generation logic introduced. ✅
- Principle III (latency measured): FR-006 is this phase's entire point —
  every stage logged with `pipeline: "streaming"` and first-partial
  timestamps for the before/after comparison. ✅
- Principle IV (local-first): webrtcvad + existing local stack, no new
  external dependency. ✅
- Principle V (English only): unchanged. ✅
- Principle VI (simplicity): periodic-re-transcription streaming STT is the
  documented, simpler alternative to a true incremental decoder — justified
  in Complexity Tracking below since it's a deliberate scope trade-off, not
  an oversight.

## Project Structure

### Documentation (this feature)

```text
specs/003-streaming-e2e/
├── plan.md
└── spec.md
```

### Source Code (repository root)

```text
app/
├── voice/
│   ├── vad.py                # EndOfTurnDetector (webrtcvad)
│   ├── audio_utils.py          # PCM16 resample/chunk helpers (wav file <-> 16kHz frames)
│   ├── stt.py                 # + transcribe_pcm16(bytes, sample_rate) for buffer re-transcription
│   └── tts.py                  # + synthesize_bytes(text) -> wav bytes (in-memory, for streaming)
├── pipeline/
│   └── streaming.py           # run_streaming(audio_frames) -> AsyncIterator[dict] (StreamEvent)
└── main.py                   # + WebSocket /ws/voice

scripts/
└── latency_report.py          # logs/latency.jsonl -> before/after report + chart (docs/latency/)

tests/
└── test_pipeline_streaming.py
```

**Structure Decision**: extends the existing single-project layout; no new
top-level components.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| Periodic re-transcription instead of true incremental STT decoding | faster-whisper (chosen in 001/002 for local, CPU-friendly, English STT) has no incremental decoder API | A true incremental decoder (e.g. whisper_streaming-style token-level continuation) is a materially larger undertaking for a portfolio MVP and isn't necessary to prove the project's actual claim (LLM+TTS overlap reduces perceived latency) — documented as a named Design Decision, not silently simplified |
