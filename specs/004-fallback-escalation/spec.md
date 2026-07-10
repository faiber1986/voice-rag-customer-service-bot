# Feature Specification: Fallback and Escalation

**Feature Branch**: `004-fallback-escalation`

**Created**: 2026-07-08

**Status**: Implemented (2026-07-08) — 13/13 on `tests/test_escalation.py`

**Input**: PRD.md FR-2, FR-6, SM-4; SPEC_Voice_RAG_Bot.md Fase 4 (Manejo de fallback y escalamiento)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Explicit request for a human is always honored (Priority: P1)

At any point, if the user says something like "let me talk to a human" or
"I want a real person", the system stops trying to answer from the knowledge
base and immediately offers a simulated handoff, regardless of whether the
underlying question was actually answerable.

**Why this priority**: This is the user's explicit override — the system
must never argue with a direct request to escalate (UJ-2 edge case in PRD).

**Independent Test**: Send a transcript containing an explicit human-request
phrase (even one about an in-domain topic) and confirm the response is the
escalation message, not a normal generated answer, and that an escalation
event was logged.

**Acceptance Scenarios**:

1. **Given** a transcript "I want to talk to a human about my balance",
   **When** processed by either pipeline, **Then** the response is the fixed
   escalation message and a `logs/escalations.jsonl` entry is written with
   `reason: "explicit_request"`.

---

### User Story 2 - Low-confidence (ungrounded) queries still escalate (Priority: P2)

The existing ungrounded-retrieval refusal (001-rag-base AD-4) is now also
logged as an escalation event, so it's visible in the same escalation log as
explicit requests — both are "the bot couldn't help, here's what happened."

**Why this priority**: Completes RF-06's "confidence baja o solicitud
explícita" pairing from the source SPEC; lower priority than P1 because the
user-facing refusal text itself is unchanged (001-rag-base already covers
correctness here) — this story is about the *logging*.

**Independent Test**: Send an out-of-domain query and confirm both the
existing refusal behavior (unchanged) and a new `logs/escalations.jsonl`
entry with `reason: "ungrounded_retrieval"`.

**Acceptance Scenarios**:

1. **Given** an out-of-domain transcript, **When** processed by either
   pipeline, **Then** the response is unchanged from 001-rag-base's
   `REFUSAL_TEXT` and an escalation event is logged.

---

### Edge Cases

- What happens when a query is both out-of-domain *and* contains an explicit
  human-request phrase? → `explicit_request` takes precedence as the logged
  reason (it's checked first) since it's the stronger, unambiguous signal.
- What happens when intent classification (FR-2) disagrees with itself run to
  run on the exact same input? → out of scope to guarantee determinism beyond
  the LLM's own greedy-decoding determinism already relied on in
  001-rag-base; intent confidence is logged for observability but does not
  by itself gate escalation (see Assumptions — a deliberate scope
  refinement of FR-6).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST classify a transcript's intent into one of
  `balance_inquiry`, `transaction_inquiry`, `faq`, `complaint_or_escalation`,
  `out_of_domain`, with an associated confidence value, via a short LLM
  prompt (`app/llm/intent.py::classify_intent`).
- **FR-002**: System MUST detect an explicit human-agent request in the
  transcript via keyword matching (`app/escalation.py`).
- **FR-003**: System MUST expose a single escalation decision point,
  `should_escalate(transcript, retrieval_result) -> EscalationResult(escalate,
  reason)`, called identically by both the sequential and streaming pipelines
  (architecture.md AD-5) — reason is one of `"explicit_request"` or
  `"ungrounded_retrieval"`.
- **FR-004**: When `reason == "explicit_request"`, the system MUST return the
  fixed escalation message without calling the LLM for open-ended
  generation, and MUST skip retrieval/generation entirely once the explicit
  request is detected.
- **FR-005**: When `reason == "ungrounded_retrieval"`, the system MUST behave
  exactly as 001-rag-base's existing refusal path (no change to that user-
  facing text or logic).
- **FR-006**: Every escalation (either reason) MUST append one JSON line to
  `logs/escalations.jsonl` with `request_id`, `reason`, `transcript`, and a
  timestamp — the "simulated handoff" the source SPEC calls for.

### Key Entities

- **IntentResult**: `label` (str, one of the five intents), `confidence`
  (float 0-1).
- **EscalationResult**: `escalate` (bool), `reason` (`"explicit_request"` |
  `"ungrounded_retrieval"` | `None`).
- **EscalationLogEntry**: one line in `logs/escalations.jsonl`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `pytest tests/test_escalation.py` passes: explicit-request
  transcripts always escalate with the correct reason and message; the
  existing 001-rag-base 10-question set's out-of-domain half now also
  produces an `ungrounded_retrieval` escalation log entry without changing
  its answer text; in-domain questions do not escalate.
- **SC-002**: Intent classification runs and logs a label+confidence for
  every request (observability), without blocking correct in-domain answers
  when retrieval is strongly grounded (see Assumptions).

## Assumptions

- **Scope refinement of PRD FR-6**: the PRD's original wording ties
  escalation to "intent-classification confidence below a documented
  threshold, OR explicit request." Building this and testing it against the
  existing question set showed that gating on intent confidence alone (when
  retrieval is strongly grounded) would risk blocking correct, answerable
  queries over a categorization ambiguity that has nothing to do with
  whether the system actually knows the answer. This phase implements
  escalation on the two conditions with direct evidence of a real problem —
  ungrounded retrieval (the system doesn't know) and explicit user request
  (the user doesn't want the bot) — and logs intent confidence for
  observability rather than using it as a silent third trigger. Documented
  here rather than silently diverging from the PRD.
