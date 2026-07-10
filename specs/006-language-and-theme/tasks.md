# Tasks: Spanish/English Language Option + Dark Mode

**Input**: `specs/006-language-and-theme/plan.md`, `spec.md`

**Tests**: `tests/test_language.py` + full existing suite (FR-006 regression) are the feature gate.

## Tasks

- [X] T001 Download the Spanish Piper voice (`es_MX-ald-medium`) into
  `data/models/piper/`; add `piper_voice_es` + `whisper_multilingual_model`
  to `app/config.py`.
- [X] T002 `app/voice/stt.py`: add `language` param to `transcribe_pcm16`;
  Spanish uses a lazily-loaded multilingual model with `task="translate"`
  (Spanish speech → English text, one pass). *Iterated during T012: `base`
  mangled domain terms ("cuenta de cheques" → "Czech account"); a banking
  glossary `initial_prompt` helped but wasn't enough; upgraded to `small`.*
- [X] T003 `app/voice/tts.py`: add `language` param to `synthesize_bytes`;
  Spanish uses the lazily-loaded es_MX voice.
- [X] T004 `app/llm/client.py`: `REFUSAL_TEXT_ES`; `answer_stream(...,
  language)` appends a respond-in-Spanish instruction for grounded answers
  and yields the Spanish refusal when ungrounded.
- [X] T005 `app/escalation.py`: `ESCALATION_TEXT_ES` + Spanish
  explicit-request phrases (defense-in-depth; the translate pass normally
  yields English keywords anyway).
- [X] T006 `app/pipeline/streaming.py`: `run_streaming(..., language="en")`;
  skip partial transcriptions in Spanish mode (FR-005); route final STT, LLM,
  TTS, and fixed texts through the language.
- [X] T007 `app/main.py`: `/ws/voice` reads `?lang=` (default `en`,
  whitelist `en|es`) and passes it to `run_streaming`.
- [X] T008 Frontend: language selector (persisted, reconnects the WS with
  `?lang=`), bilingual UI strings, transcript panel hidden in Spanish mode;
  Light/Dark switch seeded from OS preference, persisted in `localStorage`
  (`styles.css` moves dark palette to `[data-theme="dark"]`).
- [X] T009 (audit R4) Removed the `[audio-debug]` console instrumentation
  from `frontend/app.js` (mic signal confirmed healthy). The server-side
  `[stt-debug]` line was removed 2026-07-09 after the owner confirmed
  Spanish-mode live-mic quality — audit remediation R4 fully closed.
- [X] T010 (audit R5) `tests/test_language.py`: ghost-turn guard test — pure
  silence in, expect quiet `done` (empty answer, zero audio chunks).
- [X] T011 `tests/test_language.py`: Spanish in-domain question (synthesized
  with the es_MX voice) → grounded, correct figure; Spanish out-of-domain →
  `REFUSAL_TEXT_ES`; Spanish explicit human request → `ESCALATION_TEXT_ES` +
  logged handoff. *Plus retriever account-kind hints extended with Spanish/
  translation-variant tokens ("cheques", "current account", "ahorro").*
- [X] T012 Run `pytest tests/test_language.py` + `pytest tests/test_rag_qa.py`
  (Principle II gate) + Playwright E2E in Spanish mode; record results below.
- [ ] T013 (audit R3, deferred note) `logs/latency.jsonl` now mixes pre- and
  post-optimization records; a fresh measurement session is needed before
  regenerating `docs/latency/report.md` and refreshing README numbers.
  Deferred until the owner's next full demo session provides clean data.

## Phase gate result

**15/15 passed** (2026-07-09): `tests/test_language.py` 5/5 +
`tests/test_rag_qa.py` 10/10 (Principle II gate re-verified). Spanish
Playwright E2E: **PASS** — spoken Spanish question in, Spanish spoken/written
answer out with the correct figure ("Tu saldo actual es $2483.17 USD"),
transcript panel hidden, zero console errors.

### What implementation actually took (recorded per Constitution Principle I)

The Spanish path went through a documented design pivot and surfaced two real
hallucination incidents, both now structurally defended:

1. **Whisper translate instability** (5 iterations): the es→en translate
   head produced different garbled translations of the *same audio* across
   runs ("saldo" → save/sale/savings/health/fate; "un agente humano" →
   "a man"). Tried: `base` model → glossary initial_prompt → `small` model →
   artifact-normalization regexes — all whack-a-mole. **Pivot**: native
   Spanish transcription (reliable) + LLM text translation with banking-terms
   guidance (deterministic). See plan.md Complexity Tracking.
2. **Fabricated figures caught by the new tests**: with degraded queries the
   LLM invented balances ("$500" lifted from the fees FAQ, "$1,200" from
   nowhere). Structural defenses added, all language-independent:
   - Guaranteed-context rule (`app/rag/retriever.py`): a named account's
     balance chunk is always included in context.
   - Per-sentence figure guard (`app/llm/client.py`,
     `app/pipeline/streaming.py`): every number in an answer must exist in
     the retrieved context, checked *before* that sentence's audio is
     synthesized — a fabricated figure is never spoken.
   - Grounding threshold recalibrated 0.62 → 0.68 after the KB re-embed
     (in-domain 0.717-0.901 vs out-of-domain 0.507-0.644, measured).
3. **Spanish phonetic ambiguity**: "un agente humano" ≡ "una gente mano" in
   spoken Spanish; fixed with an in-language STT context prompt plus
   phonetic-twin escalation keywords.

Regression: `tests/test_escalation.py` + `tests/test_pipeline_sequential.py`
re-run after all changes — **23/23 passed** (2026-07-09). Combined with the
15/15 gate and the Spanish E2E PASS, the feature is complete with zero
regressions on the English paths.
