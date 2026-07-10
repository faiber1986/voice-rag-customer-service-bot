# Tasks: STT/TTS Sequential (No Streaming)

**Input**: `specs/002-stt-tts-sequential/plan.md`, `specs/002-stt-tts-sequential/spec.md`

**Tests**: `tests/test_pipeline_sequential.py` is the phase gate — must pass before Phase 3 starts.

## Tasks

- [X] T001 Download the Piper voice model:
  `python -m piper.download_voices en_US-lessac-medium --download-dir data/models/piper`.
- [X] T002 Create `app/voice/stt.py`: `transcribe(audio_path) -> str` using
  `faster_whisper.WhisperModel(settings.whisper_model_size, device="cpu",
  compute_type="int8")`, loaded once at module scope.
- [X] T003 Create `app/voice/tts.py`: `synthesize(text, output_path) -> Path`
  using `piper.PiperVoice.load(...)` against the downloaded voice model,
  loaded once at module scope.
- [X] T004 Create `app/pipeline/sequential.py`: `run_sequential(audio_path) ->
  PipelineResult`, calling `stt.transcribe` → `retriever.retrieve` →
  `llm.client.answer` → `tts.synthesize` in sequence, each wrapped in
  `stage_timer(request_id, <stage>)`.
- [X] T005 Extend `app/main.py`: `POST /chat/audio` (multipart file upload)
  wiring `run_sequential`, returning transcript/answer/grounded plus the
  output audio (file response or base64).
- [X] T006 Create `scripts/generate_test_audio.py`: uses `app/voice/tts.py`
  to synthesize the 10 Phase 1 test questions into `tests/fixtures/*.wav`.
- [X] T007 Write `tests/test_pipeline_sequential.py`: for each fixture audio
  file, run `run_sequential` and assert the same correctness properties as
  `tests/test_rag_qa.py` (grounded + correct fact, or refusal), plus assert
  `output_audio_path` exists and is a non-trivial `.wav` file.
- [X] T008 Run `pytest tests/test_pipeline_sequential.py -v`; confirm
  `logs/latency.jsonl` contains `stt`/`retrieval`/`llm`/`tts` stage entries
  for every request — this is the Phase 3 baseline.

## Phase gate result

10/10 passed on `tests/test_pipeline_sequential.py` (2026-07-08). Per-request
stage timings (`stt`, `retrieval`, `llm`, `tts`) confirmed present in
`logs/latency.jsonl` — this is the Phase 3 "before" baseline. Typical observed
per-stage cost on this machine: STT ~1.2-1.3s, retrieval ~0.1s, LLM ~1-3s
(varies with answer length), TTS ~0.6-0.8s. Phase 3 may begin.
