# Feature Specification: Spanish/English Language Option + Dark Mode

**Feature Branch**: `006-language-and-theme`

**Created**: 2026-07-09

**Status**: Implemented (2026-07-09) — 15/15 gate + Spanish E2E PASS; see tasks.md Phase gate result

**Input**: Project owner request (2026-07-09): "me gustaría tener la opción de
español o inglés además de un modo oscuro". Requires constitution amendment
v1.1.0 (Principle V), recorded in `.specify/memory/constitution.md`.

**Clarifications (asked and answered — the previously-skipped spec-kit
`clarify` step, run properly this time):**
1. Transcript display in Spanish mode → **hide the transcript panel** (single
   Whisper pass, no extra latency, no mixed-language display).
2. Spanish TTS accent → **es_MX (Mexican/LATAM Spanish)**.
3. Dark mode → **simple Light/Dark switch** (2-state, persisted in the
   browser; initial state seeded from the OS preference).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A Spanish speaker talks to the bot in Spanish (Priority: P1)

The user selects "Español" on the demo page, holds the button, asks
"¿Cuál es el saldo de mi cuenta de cheques?", and hears a spoken Spanish
answer with the correct balance.

**Why this priority**: it's the headline request, and the project owner is a
Spanish speaker demoing to Spanish-speaking audiences.

**Independent Test**: synthesize a Spanish question to audio (Spanish Piper
voice), run it through the streaming pipeline with `language="es"`, assert
the turn is grounded and the answer contains the correct balance figure.

**Acceptance Scenarios**:

1. **Given** Spanish mode, **When** the user asks for their checking balance
   in Spanish, **Then** the answer is grounded, contains the correct figure,
   and both the displayed and spoken answer are in Spanish.
2. **Given** Spanish mode, **When** the user asks something out of domain,
   **Then** the fixed refusal message is delivered in Spanish.
3. **Given** Spanish mode, **When** the user explicitly asks for a human
   ("quiero hablar con un humano"), **Then** the escalation message is
   delivered in Spanish and the handoff is logged.

---

### User Story 2 - Dark mode toggle (Priority: P2)

The user clicks a theme switch on the demo page and the UI flips between
light and dark; the choice persists across reloads.

**Independent Test**: manual/visual — toggle and reload. (Frontend-only
behavior; no automated test, consistent with the existing frontend's testing
approach — documented under Assumptions.)

---

### Edge Cases

- Language switched mid-session → takes effect on the next turn (the
  WebSocket reconnects with the new language parameter); the current turn is
  unaffected.
- Spanish speech in English mode (or vice versa) → out of scope: mode is
  explicit, no auto-detection in this feature. Wrong-language speech will
  transcribe poorly, same as any STT mismatch.
- Ghost turn (trailing silence) in either language → ends quietly with no
  spoken output (regression test added here per audit item R5 — the guard
  shipped untested during the post-Phase-5 hotfix wave).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The demo page MUST offer an explicit English/Español selector;
  the selection is passed to the voice WebSocket as a query parameter
  (`/ws/voice?lang=es`) and persists in the browser.
- **FR-002**: In Spanish mode, the system MUST transcribe-and-translate the
  user's Spanish speech to English in a single Whisper pass (multilingual
  `base` model, `task="translate"`), so retrieval and the Principle II
  grounding gate operate unchanged on English text. *Design evidence:
  direct Spanish-query retrieval scored 0.47-0.54 against the English KB —
  below the 0.62 threshold and indistinguishable from out-of-domain — so
  cross-lingual retrieval is not viable.*
- **FR-003**: In Spanish mode, grounded answers MUST be generated in Spanish
  (LLM instruction), and the fixed refusal and escalation messages MUST use
  their Spanish variants.
- **FR-004**: In Spanish mode, TTS MUST use a Spanish (es_MX) Piper voice.
- **FR-005**: In Spanish mode, the transcript panel is hidden and partial
  transcriptions are skipped server-side (they exist only to feed that
  panel; skipping them also removes their STT cost).
- **FR-006**: English mode MUST behave exactly as before this feature —
  byte-identical pipeline path, all existing tests still passing.
- **FR-007**: The demo page MUST offer a Light/Dark switch, defaulting to
  the OS preference on first visit, persisted in `localStorage`.
- **FR-008** *(audit R5)*: A pure-silence turn MUST end quietly (empty
  answer, no audio chunks) — regression test for the ghost-turn guard.

### Key Entities

- **Language mode**: `"en" | "es"`, per-connection (WebSocket query param).
- **Theme**: `"light" | "dark"`, browser-local only, never sent to the server.

## Success Criteria *(mandatory)*

- **SC-001**: `pytest tests/test_language.py` passes — Spanish in-domain
  question grounded with correct figure, Spanish refusal for out-of-domain,
  Spanish escalation for explicit request, ghost-turn guard.
- **SC-002**: Full existing suite still passes (FR-006 regression check),
  most critically `tests/test_rag_qa.py` 10/10.
- **SC-003**: Playwright end-to-end run in Spanish mode (Spanish audio in →
  Spanish answer out) succeeds.

## Assumptions

- The REST endpoints (`/chat/text`, `/chat/audio`) remain English-only; this
  feature scopes bilingual support to the streaming voice demo, which is the
  project's showcase path.
- llama3.2:3b generates adequate conversational Spanish (verified during
  implementation).
- Theme has no automated test: it is pure CSS/localStorage with no backend
  contract, consistent with the existing frontend's manual-verification
  approach (spec 005).
