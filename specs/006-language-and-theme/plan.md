# Implementation Plan: Spanish/English Language Option + Dark Mode

**Branch**: `006-language-and-theme` | **Date**: 2026-07-09 | **Spec**: `specs/006-language-and-theme/spec.md`

## Summary

Thread an explicit `language` mode ("en"/"es") from a frontend selector
through the WebSocket into the streaming pipeline: Spanish speech is
translated to English by Whisper in one pass (keeping retrieval and the
grounding gate untouched), the LLM is instructed to answer in Spanish, and a
Spanish Piper voice speaks it. Dark mode is a frontend-only Light/Dark
switch. Also carries three audit remediations (R3 fresh latency numbers
deferred-noted, R4 debug-instrumentation cleanup, R5 ghost-turn test).

## Technical Context

**Language/Version**: Python 3.12.12; vanilla JS frontend (no build step)

**Primary Dependencies**: existing stack + two lazily-loaded models:
faster-whisper multilingual `base` (~74MB, downloads on first Spanish turn)
and Piper `es_MX-ald-medium` (downloaded at setup into `data/models/piper/`)

**Storage**: no changes (KB stays English)

**Testing**: `tests/test_language.py` (new), full existing suite as
regression gate, Playwright E2E in Spanish mode

**Constraints**: English mode must be behaviorally identical to pre-006
(FR-006). Lazy-load Spanish models so English-only usage pays zero extra
RAM — this machine has ~2GB free (see 003 change log).

## Constitution Check

- Principle I: this spec/plan/tasks exist before implementation; gates named
  in SC-001/SC-002 run before the feature is called done. ✅
- Principle II: unchanged by design — FR-002 keeps retrieval English-internal
  precisely so the tuned 0.62 threshold and the 10-question gate stay valid;
  SC-002 re-runs the gate anyway. ✅
- Principle III: no latency claims made without measurement; the Spanish path
  E2E run records its own numbers. ✅
- Principle IV: local-only additions (two local model files). ✅
- Principle V (v1.1.0): this feature is the amendment's implementation; code
  and comments stay English, only the conversation surface gains Spanish. ✅
- Principle VI: every new behavior gets a test (SC-001) except the
  CSS-only theme switch, justified in spec Assumptions. ✅

## Project Structure

```text
app/
├── config.py            # + piper_voice_es, whisper_multilingual_model
├── voice/
│   ├── stt.py            # + language param; lazy multilingual model; task=translate for es
│   └── tts.py             # + language param; lazy es_MX voice
├── llm/client.py         # + language param on answer_stream; Spanish refusal; "answer in Spanish" instruction
├── escalation.py          # + Spanish escalation text + Spanish explicit-request phrases
├── pipeline/streaming.py  # + language param; skip partials in es; language-routed texts
└── main.py               # /ws/voice reads ?lang=; passes through

frontend/
├── index.html             # language selector + theme switch; UI strings get ids
├── app.js                  # lang state (reconnect WS), UI string dictionary, theme persistence; remove [audio-debug] (R4)
└── styles.css              # [data-theme="dark"] variables replace the media query as source of truth

tests/test_language.py     # SC-001 cases incl. ghost-turn guard (R5)
```

**Structure Decision**: extends existing modules with a `language` parameter
rather than parallel Spanish variants — AD-3's "same stage modules" rule
applies across languages too.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| English-internal retrieval for Spanish speech | Keeps the Principle II gate and its measured threshold valid | Direct cross-lingual retrieval measured at 0.47-0.54 top-score on in-domain Spanish queries — below threshold, indistinguishable from out-of-domain; a Spanish KB duplicate would double content maintenance and require re-tuning the gate |
| Native Spanish transcription + LLM text translation (two model calls) instead of Whisper's single translate pass | Whisper-small's es→en translate head proved **unstable run-to-run on identical audio** during implementation: "saldo" came out as save/sale/savings/health/fate across runs, "un agente humano" as "a man" — derailing retrieval and escalation unpredictably; regex artifact-patching was a losing whack-a-mole | The single-pass design was tried first (three iterations: base model, +glossary prompt, small model) and abandoned with evidence; native transcription is reliable, and LLM text translation with banking-terms guidance is deterministic at temperature 0 — worth the ~2s extra per Spanish turn |
