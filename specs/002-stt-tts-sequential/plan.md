# Implementation Plan: STT/TTS Sequential (No Streaming)

**Branch**: `002-stt-tts-sequential` | **Date**: 2026-07-08 | **Spec**: `specs/002-stt-tts-sequential/spec.md`

**Input**: Feature specification from `specs/002-stt-tts-sequential/spec.md`

## Summary

Wrap the Phase 1 text pipeline with faster-whisper (audio → text) on the way
in and Piper (text → audio) on the way out, called strictly sequentially. This
is the "before" baseline Phase 3's streaming pipeline will be measured
against (architecture.md AD-3).

## Technical Context

**Language/Version**: Python 3.12.12

**Primary Dependencies**: faster-whisper (`base.en`), `av==13.1.0` (pinned,
see architecture.md Stack), piper-tts (`en_US-lessac-medium`, downloaded to
`data/models/piper/`)

**Storage**: output audio written to `data/audio_out/`; voice model files in
`data/models/piper/` (gitignored, downloaded via
`python -m piper.download_voices`)

**Testing**: pytest (`tests/test_pipeline_sequential.py`) against
self-generated fixture audio (`scripts/generate_test_audio.py` →
`tests/fixtures/`)

**Target Platform**: local Windows dev machine, CPU inference

**Project Type**: single backend service (extends Phase 1's FastAPI app)

**Performance Goals**: none yet — this phase's logged latency *is* the
"sequential/before" number Phase 3 must beat. Do not optimize here.

**Constraints**: no streaming in this phase, even though `app/voice/stt.py`
and `app/voice/tts.py` will later expose streaming-capable functions for
Phase 3 to call (AD-3 — same stage modules, different orchestration).

**Scale/Scope**: same single demo account and knowledge base as Phase 1.

## Constitution Check

- Principle I (phase-gated): spec/plan/tasks exist before implementation. ✅
- Principle II (no hallucination): unchanged from Phase 1 — STT/TTS wrap the
  existing gated pipeline, they don't touch generation logic. ✅
- Principle III (latency measured): FR-003 wraps every stage in
  `stage_timer`, producing this phase's baseline for Phase 3's comparison. ✅
- Principle IV (local-first): faster-whisper + Piper, no hosted STT/TTS. ✅
- Principle V (English only): `base.en` transcription model, English Piper
  voice, per PRD Non-Goals (no multi-language in v1). ✅

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-stt-tts-sequential/
├── plan.md
└── spec.md
```

### Source Code (repository root)

```text
app/
├── voice/
│   ├── stt.py             # transcribe(audio_path) -> str (faster-whisper, base.en)
│   └── tts.py              # synthesize(text, output_path) -> Path (Piper)
├── pipeline/
│   └── sequential.py       # run_sequential(audio_path) -> PipelineResult
└── main.py                # + POST /chat/audio (multipart upload)

scripts/
└── generate_test_audio.py  # Piper self-synthesizes the 10 Phase 1 test
                             #   questions into tests/fixtures/*.wav

tests/
├── fixtures/                # generated .wav files (committed, small)
└── test_pipeline_sequential.py
```

**Structure Decision**: extends the Phase 1 single-project layout; no new
top-level components, matching `architecture.md`'s Structural Seed.

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.*
