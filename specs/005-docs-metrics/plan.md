# Implementation Plan: Documentation and Metrics

**Branch**: `005-docs-metrics` | **Date**: 2026-07-08 | **Spec**: `specs/005-docs-metrics/spec.md`

**Input**: Feature specification from `specs/005-docs-metrics/spec.md`

## Summary

Write the final README (the actual portfolio deliverable per SPEC §11), build
the minimal frontend demo page the architecture always assumed, and run the
full test suite as a final gate.

## Technical Context

**Language/Version**: Markdown (README), vanilla HTML/CSS/JS (frontend, no
build step per architecture.md Structural Seed)

**Primary Dependencies**: none new — frontend uses native `WebSocket`,
`MediaRecorder`/`AudioContext`, no framework (matches SPEC §10 "página
mínima")

**Storage**: N/A

**Testing**: full `pytest` run; manual frontend load via the Chrome browser
tool (`mcp__claude-in-chrome__*`)

**Target Platform**: local Windows dev machine; frontend targets any modern
browser with `getUserMedia`/`AudioContext` support

**Project Type**: docs + static frontend, extending the existing FastAPI app

**Performance Goals**: N/A (documentation phase)

**Constraints**: README must be self-contained and English-only; must not
overclaim the Phase 3 latency finding beyond what `docs/latency/report.md`
actually shows (Constitution Principle III).

**Scale/Scope**: single README, one demo HTML page.

## Constitution Check

- Principle I (phase-gated): this is the final phase; spec/plan/tasks exist
  before writing. ✅
- Principle III (latency measured): README latency section is generated
  from `docs/latency/report.md`'s real numbers, not invented ones,
  including the honest negative/nuanced finding. ✅
- Principle V (English only): README, frontend copy, all in English. ✅
- Principle VI (simplicity): frontend is plain JS, no build tooling, matching
  SPEC's "página mínima" framing. ✅

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/005-docs-metrics/
├── plan.md
└── spec.md
```

### Source Code / Docs (repository root)

```text
README.md                      # rewritten in full
frontend/
├── index.html                  # demo UI: record button, transcript/answer display, audio playback
├── app.js                       # mic capture -> PCM16 16kHz frames -> WebSocket -> render events
└── styles.css
```

**Structure Decision**: `frontend/` already existed as an empty placeholder
in the Structural Seed from Phase 0; this phase fills it in. No backend
changes needed — `/ws/voice` (003-streaming-e2e) already implements the
contract the frontend consumes.

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.*
