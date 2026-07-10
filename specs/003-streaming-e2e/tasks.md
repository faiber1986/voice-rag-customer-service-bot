# Tasks: Streaming End-to-End

**Input**: `specs/003-streaming-e2e/plan.md`, `specs/003-streaming-e2e/spec.md`

**Tests**: `tests/test_pipeline_streaming.py` is the phase gate — must pass before Phase 4 starts.

## Tasks

- [X] T001 Create `app/voice/audio_utils.py`: `wav_file_to_pcm16(path,
  target_rate=16000) -> bytes` (mono/16-bit/resampled via `audioop`) and
  `chunk_pcm16(pcm_bytes, sample_rate, frame_ms=20) -> list[bytes]`.
- [X] T002 Create `app/voice/vad.py`: `EndOfTurnDetector` wrapping
  `webrtcvad.Vad`, tracking trailing silence across 20ms frames, with a
  documented max-utterance-duration safety cap.
- [X] T003 Extend `app/voice/stt.py`: `transcribe_pcm16(pcm_bytes,
  sample_rate=16000) -> str`, converting PCM16 bytes to a float32 numpy array
  and calling the same loaded `WhisperModel`.
- [X] T004 Extend `app/voice/tts.py`: `synthesize_bytes(text) -> bytes`
  (in-memory WAV, no file write) for per-sentence-chunk streaming synthesis.
- [X] T005 Add `pipeline` tag to `app/logging_utils.py::StageTimer`/
  `stage_timer` (default `"sequential"`); tag Phase 2 calls `"sequential"`
  and `/chat/text` calls `"text"`.
- [X] T006 Create `app/pipeline/streaming.py`: `run_streaming(audio_frames) ->
  AsyncIterator[dict]` — VAD-gated partial re-transcription, final
  transcription on end-of-turn, retrieval, token-streamed LLM answer split
  into sentence chunks fed to per-chunk TTS as they complete, all stages
  logged with `pipeline="streaming"` and `first_partial_ts` where applicable.
- [X] T007 Extend `app/main.py`: `WebSocket` endpoint `/ws/voice` looping
  `run_streaming` over frames received from the client, forwarding each
  StreamEvent as JSON (`audio_chunk` base64-encoded).
- [X] T008 Write `tests/test_pipeline_streaming.py`: for each of the 10
  fixture audio files, resample+chunk via `audio_utils`, feed through
  `run_streaming` via an async generator, collect events, and assert the same
  correctness properties as Phase 1/2 on the reassembled final answer.
- [X] T009 Create `scripts/latency_report.py`: reads `logs/latency.jsonl`,
  computes per-stage and time-to-first-byte statistics grouped by `pipeline`,
  writes `docs/latency/report.md` (table) and `docs/latency/comparison.png`
  (bar chart) comparing `sequential` vs `streaming`.
- [X] T010 Run `pytest tests/test_pipeline_streaming.py -v`, then
  `python -m scripts.latency_report`; confirm the report shows a measurable
  time-to-first-audio improvement for streaming vs. sequential.

## Phase gate result

11/11 passed on `tests/test_pipeline_streaming.py` (2026-07-08), including
partial-transcript, incremental-token, and audio-before-full-answer
assertions. `python -m scripts.latency_report` produced
`docs/latency/report.md` + `comparison.png` from 10 sequential + 7 streaming
real requests on this machine.

**Honest result, not a clean win:** top-line time-to-first-audio was actually
*higher* for streaming (13598ms vs. 8294ms sequential) on this project's
short (~2s) test questions. Root cause, diagnosed and documented in
`docs/latency/report.md`: this project's streaming STT (periodic
re-transcription of a growing buffer — faster-whisper has no incremental
decoder, a deliberate, pre-declared trade-off in this spec's plan.md
Complexity Tracking) re-transcribes the audio roughly twice, which costs more
on short single-utterance clips than the LLM/TTS overlap saves back.

The isolated, STT-independent metrics *do* show the real claim holds: LLM
first-token arrives 42.5% sooner than the full answer, and the first TTS
audio chunk 9.2% sooner than all chunks — i.e., streaming genuinely delivers
audio to the user before the full response is ready, which is the
architectural property FR-003/FR-004 require. This nuance (and why it matters
more for longer/multi-turn conversations than this project's short test
questions) is carried into the Phase 5 README's Design Decisions section
rather than overclaiming a clean win the data doesn't support.

Task T009's bonus script `scripts/_collect_streaming_latency.py` (ad hoc data
collection, not test coverage) was used once to top up the sample and then
deleted — not part of the permanent codebase.

Phase 4 may begin.

## Post-implementation change log (2026-07-09 — recorded by the SDD audit)

Live-microphone debugging and latency work done after Phase 5 without going
through this spec first (Principle I violation documented in
`docs/sdd-compliance-audit.md`):

- WebSocket mid-turn inactivity timeout (2s) + indefinite first-frame wait
  (`app/main.py`) — the original endpoint hung forever if the client stopped
  sending frames without disconnecting.
- Ghost-turn guard (`app/pipeline/streaming.py`): trailing silence after a
  turn no longer starts a phantom turn that speaks an unprompted refusal.
- Implicit end-of-turn on frame-source exhaustion (was silently dropping the
  buffered audio).
- Two-tier STT (`app/voice/stt.py`): greedy `beam_size=1` for live-caption
  partials, full `beam_size=5` for the final transcription that drives the
  answer.
- Partial re-transcription cadence 1000ms → 3000ms (the 1s cadence made STT
  cost quadratic in utterance length: 6-43s measured on real turns).
- Model warm-up on server startup; favicon route; WebSocket send-after-close
  hardening; temporary `[stt-debug]`/`[audio-debug]` instrumentation (removal
  tracked in specs/006 tasks).
