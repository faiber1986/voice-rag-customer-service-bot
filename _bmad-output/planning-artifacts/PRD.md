---
title: Voice-RAG Customer Service Bot (Financial Domain)
created: 2026-07-08
updated: 2026-07-08
status: final
---

# PRD: Voice-RAG Customer Service Bot (Financial Domain)

## 0. Document Purpose

This PRD scopes a portfolio project for Andre: a voice-driven customer service
bot for a financial domain (balance inquiries, statements, recent transactions)
that demonstrates a complete, latency-optimized voice pipeline — STT → intent →
RAG → LLM → TTS, streaming end-to-end. It is written for a single-builder,
interview-portfolio context: the reader is Andre himself and anyone (e.g. an
interviewer) reviewing the finished repository. Sections are lean where the
solo/hobby stakes call for it and detailed where the project's actual
differentiator lives — the non-functional latency requirements. This PRD is
derived from `SPEC_Voice_RAG_Bot.md` (the original Spanish source spec) and is
the English source of truth going forward; downstream work is organized as five
sequential spec-kit features (`specs/001-rag-base` … `005-docs-metrics`), one per
build phase.

## 1. Vision

Voice customer-service bots fail for one of two reasons: they retrieve the wrong
information (a RAG failure), or they retrieve the right information but the
conversation feels slow and robotic (a latency/streaming failure). This project
builds a small but complete voice bot for a financial domain — checking an
account balance, reviewing a statement, looking up recent transactions — that
explicitly attacks both failure modes and *measures* the fix for the second one.
The deliverable is not just a working demo; it is a repository with real,
logged, before/after latency numbers proving that streaming architecture
measurably improves perceived responsiveness, and a RAG pipeline that
demonstrably refuses to hallucinate outside its knowledge base. It exists to be
defended point-by-point in a Data Scientist / Voice Bot interview.

## 2. Target User

### 2.1 Jobs To Be Done

- As the builder, I need a working, end-to-end voice-RAG system I can run,
  demo, and discuss in technical depth during an interview.
- As a bank customer (simulated), I want to ask for my balance or recent
  transactions by voice and get a correct, fast, spoken answer.
- As a bank customer (simulated), I want the bot to admit when it doesn't know
  something instead of guessing, and to offer a human when it can't help.

### 2.2 Non-Users (v1)

Real bank customers, real account holders, and any production financial
institution. This is a simulated, synthetic-data demo, not a deployable
product.

### 2.3 Key User Journeys

- **UJ-1. A customer asks for their balance and gets a fast, correct, spoken
  answer.**
  - **Persona + context:** a simulated retail banking customer, using the demo
    web page's microphone capture.
  - **Entry state:** on the demo page, no auth (synthetic single demo account).
  - **Path:** taps record, asks "What's my current balance?", stops speaking →
    VAD detects end of turn → STT transcribes → intent classified as balance
    inquiry → RAG retrieves the simulated account record → LLM composes a short
    spoken-style answer → TTS starts speaking before the LLM has finished the
    full sentence.
  - **Climax:** audio response starts within the documented latency budget,
    stating the correct balance.
  - **Resolution:** customer hears the answer and can ask a follow-up.

- **UJ-2. A customer asks something out of domain and the bot admits it instead
  of guessing.**
  - **Persona + context:** same demo customer, asks something unrelated to
    banking (e.g. "what's the weather tomorrow?") or an ambiguous financial
    question the knowledge base doesn't cover.
  - **Entry state:** mid-conversation on the demo page.
  - **Path:** STT transcribes → intent classifier flags low confidence /
    out-of-domain → RAG retrieval returns no sufficiently relevant context → LLM
    is constrained to say it doesn't have that information rather than
    fabricate an answer → bot offers escalation to a human agent.
  - **Climax:** the bot explicitly declines to answer instead of hallucinating,
    and offers a next step.
  - **Resolution:** a log entry simulates the handoff; the customer knows what
    happens next.
  - **Edge case:** if the customer says "let me talk to a person" explicitly at
    any point, the same escalation path fires regardless of intent confidence.

- **UJ-3. A customer has a natural-feeling exchange, not a robotic one.**
  - **Persona + context:** same demo customer, sensitive to awkward silences.
  - **Entry state:** mid-conversation.
  - **Path:** as in UJ-1, but the point being exercised is that LLM tokens and
    TTS audio both stream — the customer hears the first words of the response
    while the rest is still being generated, instead of waiting for the full
    pipeline to finish sequentially.
  - **Climax:** time from end-of-speech to first audio byte is short and
    documented; Andre can show the before/after (sequential vs. streaming)
    comparison as interview evidence.
  - **Resolution:** conversation continues without a perceptible dead-air gap.

## 3. Glossary

- **STT (Speech-to-Text)** — transcribes user audio to text; streaming STT
  emits partial transcripts before the user finishes speaking.
- **VAD (Voice Activity Detection)** — detects end-of-turn (user stopped
  speaking) from the audio stream.
- **Intent Classification** — labels a transcribed query as one of: balance
  inquiry, transaction inquiry, general FAQ, or complaint/escalation request.
- **RAG (Retrieval-Augmented Generation)** — retrieves relevant passages from
  the Knowledge Base via a Vector DB, supplied to the LLM as grounding context.
- **Knowledge Base** — the set of Financial FAQs and Simulated Account Data the
  system may draw on; anything outside it is out of domain.
- **Vector DB** — local embedded store (Chroma) holding embeddings of the
  Knowledge Base for similarity search.
- **LLM (Large Language Model)** — generates the natural-language answer from
  the user query plus retrieved context; runs locally via Ollama.
- **TTS (Text-to-Speech)** — synthesizes the LLM's text response into audio.
  Streaming TTS begins synthesizing a sentence chunk before the LLM has
  produced the full response.
- **Escalation / Handoff** — the simulated hand-off to a human agent, triggered
  by low intent confidence or an explicit user request; logged, not a live
  transfer.
- **Stage Latency** — the elapsed time of one pipeline stage (STT, retrieval,
  LLM, TTS), logged with start/end timestamps for every request.
- **Perceived Latency** — elapsed time from end of user speech to the first
  byte of response audio; the project's primary latency metric.

## 4. Features

### 4.1 Voice Understanding (STT + VAD)

**Description:** Converts the customer's spoken audio into text in real time
and determines when the customer has finished speaking, without cutting them
off or introducing dead air. Realizes UJ-1, UJ-3.

**Functional Requirements:**

#### FR-1: Streaming speech-to-text

The system can transcribe user audio to text as audio arrives, rather than
waiting for the full utterance to be recorded. Realizes UJ-1, UJ-3.

**Consequences (testable):**
- Partial transcripts are available before end-of-turn is declared.
- End-of-turn is detected via VAD, not a fixed silence timeout large enough to
  feel laggy or short enough to cut the customer off mid-sentence.
- STT is English-only for v1 (see §5 Non-Goals).

**Feature-specific NFRs:**
- VAD approach must be documented (rule/model used, thresholds chosen) — see
  Cross-Cutting NFRs, NFR-3.

### 4.2 Intent Classification

**Description:** Classifies each transcribed query into a small fixed set of
intents so the system knows whether to answer, retrieve, or escalate. Realizes
UJ-1, UJ-2.

**Functional Requirements:**

#### FR-2: Query intent classification

The system can classify a transcribed query into one of: balance inquiry,
transaction inquiry, general FAQ, or complaint/escalation request, with an
associated confidence signal. Realizes UJ-1, UJ-2.

**Consequences (testable):**
- Every query receives exactly one primary intent label plus a confidence
  value used by FR-6 (escalation).
- Classification may be performed by a short, dedicated LLM prompt rather than
  a separately trained model. `[ASSUMPTION: a lightweight prompt-based
  classifier is sufficient for a 4-way intent split at this scale — confirmed
  by the SPEC's own suggested architecture.]`

### 4.3 Knowledge Retrieval (RAG)

**Description:** Retrieves the most relevant passages from the Knowledge Base
(financial FAQs plus simulated account data) for a given query, so the LLM
answers from real, grounded context instead of parametric guesswork. Realizes
UJ-1, UJ-2.

**Functional Requirements:**

#### FR-3: Context retrieval via vector search

The system can retrieve relevant Knowledge Base passages for a query via
similarity search over the Vector DB. Realizes UJ-1, UJ-2.

**Consequences (testable):**
- The Knowledge Base contains both general financial FAQs and simulated
  per-customer account data (balance, recent transactions), all synthetic.
- Retrieval returns a relevance/similarity score usable by FR-6 to decide
  whether the result is strong enough to answer from.
- Out-of-domain queries retrieve no sufficiently relevant passage, which is the
  signal FR-4 uses to refuse rather than fabricate.

### 4.4 Response Generation (LLM)

**Description:** Composes a natural-language, spoken-style answer from the
retrieved context, streaming tokens as they're generated, and explicitly
refusing to answer when context is insufficient. Realizes UJ-1, UJ-2, UJ-3.

**Functional Requirements:**

#### FR-4: Grounded, streaming answer generation

The system can generate a natural-language response using only the retrieved
context, streaming tokens as they are produced rather than waiting for the full
completion. Realizes UJ-1, UJ-3.

**Consequences (testable):**
- Token streaming is observable in logs/traces (first-token timestamp captured
  separately from last-token timestamp).
- When retrieved context is insufficient (see FR-3), the response explicitly
  states the system does not have that information — it must never fabricate a
  financial fact. This is validated by the out-of-domain half of the Phase 1
  test set (see §7 SM-3).

### 4.5 Voice Response (TTS)

**Description:** Converts the LLM's streamed text response into spoken audio,
starting synthesis before the full response text is available, so the customer
hears the answer begin almost as soon as it starts generating. Realizes UJ-1,
UJ-3.

**Functional Requirements:**

#### FR-5: Streaming text-to-speech

The system can begin synthesizing audio for a completed sentence/clause chunk
of the LLM's response before the LLM has finished generating the rest of the
response. Realizes UJ-1, UJ-3.

**Consequences (testable):**
- Time-to-first-audio-byte is measured and is materially lower than the
  time-to-last-token would imply under a fully sequential design (see §7 SM-1,
  SM-2).
- TTS voice is English-only for v1 (see §5 Non-Goals).

### 4.6 Escalation to Human Agent

**Description:** Recognizes when the bot should hand off to a human rather than
keep guessing, and simulates that handoff so the behavior is demonstrable
without a real support queue. Realizes UJ-2.

**Functional Requirements:**

#### FR-6: Low-confidence / explicit-request escalation

The system can offer escalation to a simulated human agent when intent
confidence is low or when the customer explicitly asks for a human. Realizes
UJ-2.

**Consequences (testable):**
- Escalation triggers on: (a) intent-classification confidence below a
  documented threshold, or (b) the transcript containing an explicit human-agent
  request, at any point in the conversation.
- Each escalation produces a logged event (simulated handoff), not a live
  transfer (see §5 Non-Goals).

### 4.7 Latency Observability

**Description:** Every request's per-stage timing is captured so the project
can produce defensible, real before/after latency numbers rather than
anecdotal claims. Realizes UJ-3.

**Functional Requirements:**

#### FR-7: Per-stage latency logging

The system can log start/end timestamps for each pipeline stage (STT,
retrieval, LLM, TTS) for every request. Realizes UJ-3.

**Consequences (testable):**
- Logs are structured (JSON Lines) and machine-readable by the Phase 5
  reporting script.
- A report/dashboard can be generated from the logs showing per-stage latency
  and the sequential-vs-streaming comparison (Phase 2 baseline vs. Phase 3).

## 5. Non-Goals (Explicit)

- No real telephony integration (no Twilio or equivalent in production use) —
  the MVP simulates input via prerecorded/self-generated audio or local
  microphone capture in a browser demo page. How a real telephony platform
  would be integrated is documented as future work, not built.
- No real customer authentication and no real customer data — all account and
  transaction data is synthetic, generated for this project.
- No multi-language support in v1 — English only, end to end (STT, TTS, UI,
  knowledge base, code, and documentation).
- No production-grade scaling, security hardening, or multi-tenant concerns —
  this is a single-demo-account portfolio artifact.

## 6. MVP Scope

### 6.1 In Scope

- Phase 1: text-only RAG pipeline (retrieval + LLM), validated against a fixed
  10-question test set (5 in-domain, 5 out-of-domain).
- Phase 2: STT and TTS added sequentially (no streaming yet), full audio-in →
  audio-out pipeline working end to end.
- Phase 3: full pipeline converted to streaming (STT, LLM, TTS), with a
  measured before/after latency comparison against the Phase 2 baseline.
- Phase 4: intent-confidence and explicit-request-based escalation to a
  simulated human agent.
- Phase 5: an English README with an architecture diagram, real latency
  metrics, and an explicit "Design Decisions" section explaining why streaming
  matters, backed by this project's own numbers.

### 6.2 Out of Scope for MVP

- Real telephony/Twilio integration — deferred, documented as future work only.
- Multi-language support — deferred to a hypothetical v2.
- Any hosted/paid API dependency — v1 runs entirely on local, free components
  (Ollama, Chroma, faster-whisper, Piper); swapping in hosted providers
  (OpenAI/ElevenLabs/Deepgram/Pinecone) is documented as a future-work option,
  not implemented. `[NOTE FOR PM: revisit if a real interview loop specifically
  asks about hosted-provider tradeoffs — the architecture is provider-agnostic
  enough to swap in without a redesign.]`

## 7. Success Metrics

**Primary**
- **SM-1**: Perceived latency (end of user speech → first byte of response
  audio) — target < 1.5s; the real value achieved on this machine's local
  stack is measured and documented even if it misses the target. Validates
  FR-1, FR-4, FR-5.
- **SM-2**: Streaming is verifiable in logs/traces for both LLM and TTS stages
  (first-token / first-audio-byte timestamps distinct from completion
  timestamps), with a documented before/after comparison against the Phase 2
  sequential baseline. Validates FR-4, FR-5, FR-7.

**Secondary**
- **SM-3**: Zero hallucinated financial facts on the fixed 10-question test set
  — all 5 out-of-domain questions receive an explicit "I don't have that
  information" style answer, all 5 in-domain questions receive a correct,
  grounded answer. Validates FR-3, FR-4.
- **SM-4**: Escalation fires correctly on the low-confidence and
  explicit-request test cases (see Phase 4 test set). Validates FR-6.

**Counter-metrics (do not optimize)**
- **SM-C1**: STT/VAD tuned purely for speed must not cut the customer off
  mid-sentence or misdetect end-of-turn — a faster wrong transcript is worse
  than a slightly slower correct one. Counterbalances SM-1.
- **SM-C2**: Chasing lower perceived latency must not come at the cost of SM-3
  (no hallucination) — e.g. skipping retrieval to save time is not an
  acceptable optimization. Counterbalances SM-1.

## 8. Open Questions

1. Should the demo web page attempt live microphone streaming to the backend
   during this build, or is self-generated/prerecorded audio sufficient
   evidence for the interview? *(Current plan: build the live WebSocket path
   for real, validate it primarily with self-generated audio since a coding
   agent cannot grant itself live browser microphone permission; the user
   tests live mic manually afterward.)*
2. Is `llama3.2:3b` (fast, already local) the right default LLM, or should
   `qwen3.5:9b` (slower, higher quality, also local) be the default with
   `llama3.2:3b` as a documented low-latency alternative? *(Current plan:
   default to `llama3.2:3b` since latency is this project's stated
   differentiator; document the tradeoff.)*

## 9. Assumptions Index

- §4.2 FR-2 — a lightweight prompt-based intent classifier (same LLM, short
  prompt) is sufficient rather than a separately trained classifier model.
- §6.2 — v1 ships entirely on a local/free stack (Ollama, Chroma,
  faster-whisper, Piper); hosted-provider integration is documented, not built.
