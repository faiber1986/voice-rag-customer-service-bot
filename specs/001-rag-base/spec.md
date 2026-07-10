# Feature Specification: RAG Base (Text Only)

**Feature Branch**: `001-rag-base`

**Created**: 2026-07-08

**Status**: Implemented (2026-07-08) — 10/10 on `tests/test_rag_qa.py`

**Input**: PRD.md FR-3, FR-4, SM-3; SPEC_Voice_RAG_Bot.md Fase 1 (RAG base, sin voz)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - In-domain financial question answered correctly (Priority: P1)

A user submits a text question about their account (e.g. "What's my checking
balance?") or a general financial FAQ (e.g. "How long do external transfers
take?"). The system retrieves the relevant passage from the knowledge base and
generates a correct, grounded answer.

**Why this priority**: This is the core value of the whole project — without
correct retrieval, nothing downstream (voice, streaming, escalation) matters.

**Independent Test**: Send a text query to the retrieval+LLM pipeline (no
audio involved) and check the answer contains the correct fact from
`app/rag/knowledge_base/`.

**Acceptance Scenarios**:

1. **Given** the knowledge base is ingested into Chroma, **When** the user asks
   "What is my checking account balance?", **Then** the response states the
   correct balance from `account_data.json`.
2. **Given** the knowledge base is ingested, **When** the user asks "What
   interest rate do savings accounts earn?", **Then** the response states
   2.5% APY as in `faqs.json` (faq-007).

---

### User Story 2 - Out-of-domain question is refused, not hallucinated (Priority: P1)

A user asks something the knowledge base has no answer for (e.g. "What's the
weather tomorrow?" or "Can I get a mortgage with you?" — not in the FAQ set).
The system explicitly says it doesn't have that information instead of
inventing an answer.

**Why this priority**: This is the project's core anti-hallucination claim
(PRD SM-3, Constitution Principle II) — equally critical to P1 above.

**Independent Test**: Send an out-of-domain text query and confirm the
response is a refusal, not a fabricated fact, and that retrieval's top
similarity score was below `RETRIEVAL_MIN_SCORE`.

**Acceptance Scenarios**:

1. **Given** the knowledge base is ingested, **When** the user asks "What's
   the weather like tomorrow?", **Then** the response explicitly states the
   system doesn't have that information and does not state any fabricated
   fact.
2. **Given** the knowledge base is ingested, **When** the user asks an
   ambiguous financial question outside the FAQ/account scope (e.g. "Can you
   approve me for a $50,000 mortgage?"), **Then** the response declines
   rather than guessing terms.

---

### Edge Cases

- What happens when the query is empty or whitespace-only? → return a
  clarification request, do not call the LLM with empty context.
- What happens when Chroma has not been ingested yet (empty collection)? →
  every query behaves as out-of-domain (no context found), not a crash.
- What happens when a query matches both an FAQ and account data (e.g. "how
  much is in my savings and what's the interest rate?")? → both retrieved
  passages are included in context; answer should address both.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST ingest `app/rag/knowledge_base/faqs.json` and
  `account_data.json` into a persistent local Chroma collection, one
  embedded chunk per FAQ entry and per logical account/transaction fact.
- **FR-002**: System MUST expose a retrieval function that, given a text
  query, returns the top-k most similar chunks plus a similarity score for
  the best match.
- **FR-003**: System MUST expose a text-in/text-out answer function that
  calls the local Ollama LLM (`llama3.2:3b`) with the retrieved chunks as
  context and returns a natural-language answer.
- **FR-004**: System MUST refuse to answer (explicit "I don't have that
  information" style response) when the best retrieval score is below
  `RETRIEVAL_MIN_SCORE` (configured in `app/config.py`), without calling the
  LLM in open-ended mode.
- **FR-005**: System MUST expose the pipeline via a FastAPI REST endpoint
  (`POST /chat/text`) accepting `{"query": str}` and returning
  `{"answer": str, "grounded": bool, "top_score": float}`.
- **FR-006**: System MUST log per-stage latency (retrieval, LLM) for every
  request via `app/logging_utils.py`, per Constitution Principle III / AD-2.

### Key Entities

- **FAQ chunk**: one FAQ question+answer pair, embedded as a single
  retrievable unit, tagged with `category`.
- **Account fact chunk**: one account's balance summary or one transaction (or
  small transaction batch), embedded as a retrievable unit, tagged with
  `account_id`.
- **Retrieval result**: ordered list of chunks with similarity scores for a
  given query.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 5 in-domain questions in the fixed 10-question test set
  (`tests/test_rag_qa.py`) receive a correct, grounded answer.
- **SC-002**: All 5 out-of-domain questions in the same test set receive an
  explicit refusal, with zero fabricated financial facts.
- **SC-003**: `pytest tests/test_rag_qa.py -v` passes 10/10 before Phase 2
  begins (Constitution Principle I: phase gate).

## Assumptions

- Single synthetic demo customer/account (per PRD §5 Non-Goals) — no
  multi-account disambiguation logic needed in v1.
- `RETRIEVAL_MIN_SCORE` threshold is tuned empirically against the 10-question
  test set during this phase and recorded in `app/config.py` with a comment
  explaining the chosen value.
- Embeddings via Ollama's `nomic-embed-text`, matching `architecture.md`
  Stack table.
