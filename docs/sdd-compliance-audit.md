# SDD Compliance Audit

**Date**: 2026-07-09
**Scope**: full project history — Phase 0 setup through the post-Phase-5
live-microphone debugging and performance-optimization work.
**Verdict up front**: the five build phases themselves followed the
constitution and the spec-kit flow with documented, bounded deviations — but
the **post-Phase-5 hotfix wave violated the process**, including one critical
gate violation (Principle II) that this audit triggered a remediation for.

---

## Part 1 — Constitution compliance, principle by principle

### Principle I — Phase-Gated, Spec-Driven Development: PARTIALLY VIOLATED

Compliant during the phases: every phase (001-005) had `spec.md`, `plan.md`,
and `tasks.md` written before implementation, and each phase's dedicated test
suite passed before the next phase began (results recorded in each
`tasks.md` "Phase gate result").

Deviations, in increasing severity:

1. **Time-boxed gates (documented at the time, low severity).** Phase 4's
   T006 combined regression run was stopped at 24/31 (zero failures), and
   Phase 5's T004 final full-suite run was stopped at 26/26 (zero failures),
   both on a machine that had slowed drastically over the session. Both were
   disclosed in the respective `tasks.md` rather than hidden — a defensible
   trade-off, but strictly a deviation from "no phase is done until its
   tests pass" applied to the *full* combined suite.

2. **Post-Phase-5 hotfix wave bypassed the loop entirely (high severity).**
   After Phase 5 closed, a series of real changes were made directly to the
   code with no spec, plan, or tasks update:
   - WebSocket inactivity timeout + first-frame wait logic (`app/main.py`)
   - Ghost-turn guard for trailing silence (`app/pipeline/streaming.py`)
   - Two-tier STT quality: greedy partials / beam-search finals
     (`app/voice/stt.py`)
   - Partial re-transcription cadence 1000ms → 3000ms
   - Ollama `keep_alive`, `num_ctx` 16384 → 2048, model warm-up on startup
   - System prompt compressed; knowledge-base balance chunk text compressed;
     `retrieval_top_k` 4 → 3
   - Debug instrumentation added (server `[stt-debug]` print, frontend
     `[audio-debug]` console logging)
   - `favicon.ico` route; `RuntimeError` hardening on the WebSocket send path

   The constitution's Development Workflow says changes are reflected
   upstream (spec) first. None were, until this audit. Remediation: a
   post-implementation change log is being appended to the affected specs
   (001, 003), and this audit document records the full list.

### Principle II — No Hallucination (NON-NEGOTIABLE): VIOLATED, REMEDIATED

The compressed system prompt, the rewritten (shortened) balance-chunk text,
and `retrieval_top_k` 4 → 3 all materially change retrieval and generation
behavior. The fixed 10-question gate (`tests/test_rag_qa.py`) — which the
constitution names as the *only* acceptable evidence for this principle —
**was not re-run before those changes went live**. Only a single-question
end-to-end smoke test was run. This is the most serious finding of this
audit: the exact scenario the gate exists for (a "harmless" prompt tweak
quietly reintroducing hallucination) went unchecked.

**Remediation**: the full 10-question gate was re-run as the first action of
this audit. Result recorded at the bottom of this document.

### Principle III — Latency Is Measured, Not Assumed: PARTIALLY VIOLATED

Compliant during the phases (JSONL stage logging, real before/after report).
Violated afterward: the performance optimizations changed the pipeline's
latency profile substantially (STT 6-43s → ~1.7-4.7s; LLM time-to-first-token
~15.5s → ~7.9s), but `docs/latency/report.md` and the README metrics still
describe the pre-optimization system, and `logs/latency.jsonl` now mixes
pre- and post-optimization records, so a naive regeneration would blend two
different systems into one misleading average. **Remediation (pending)**:
collect a fresh, post-optimization measurement run and regenerate the report
with only current-system data, then refresh the README numbers.

### Principle IV — Local-First, Provider-Agnostic: COMPLIANT

All changes stayed on the local stack; Playwright was added as a
dev/test-only dependency (browser automation for end-to-end verification),
not a runtime dependency; no hosted API crept in anywhere.

### Principle V — English Only, End to End: COMPLIANT (amendment now required)

Code, docs, tests, KB, and UI remain English-only as written. The user has
now requested a Spanish/English language option — under the constitution's
own Governance section this requires a formal amendment before
implementation, which is being made as part of Feature 006 (see
`specs/006-language-and-theme/`), with the version bump recorded in the
constitution footer.

### Principle VI — Simplicity and Test-Backed Behavior: MINOR VIOLATIONS

- Debug instrumentation (`[stt-debug]` server print, `[audio-debug]` frontend
  console logging) is still in the shipped code — added during live
  debugging, useful, but per this principle it should be removed or gated
  once the microphone issue is closed. **Remediation (pending user
  confirmation that the mic works)**.
- The post-Phase-5 behavior changes shipped without new/updated tests (e.g.
  nothing asserts the ghost-turn guard or the two-tier STT split). The
  ghost-turn guard in particular is user-visible behavior that warrants a
  test. **Remediation: folded into Feature 006's task list.**

### Technology Constraints & Development Workflow sections: COMPLIANT

Python 3.12 via uv, pinned `av`/`setuptools`, FastAPI/WebSockets, Chroma
local persistence, synthetic data only — all still true. The
source-of-truth ordering (SPEC → PRD/architecture → specs → code) was
respected during the phases and broken only by the hotfix wave covered
under Principle I.

---

## Part 2 — spec-kit workflow steps, one by one

| Step | Status | Notes |
| --- | --- | --- |
| `constitution` | ✅ Done | Written at Phase 0 before any feature spec; versioned footer present. |
| `specify` | ✅ Done ×5 | One `spec.md` per phase, user-story structure with acceptance scenarios and measurable success criteria. |
| `clarify` | ⚠️ **Skipped** | The optional structured-clarification step was never run for any feature. Partially compensated: scope questions were asked interactively at project planning (framework combination, session scope, API keys) — but per-feature ambiguities (e.g. "should intent confidence gate escalation?") were resolved unilaterally and documented in spec Assumptions instead of being asked. |
| `plan` | ✅ Done ×5 | One `plan.md` per phase with Technical Context, Constitution Check, structure decision; Complexity Tracking used honestly (streaming STT trade-off declared in 003). |
| `tasks` | ✅ Done ×5 | Ordered task lists; checked off as executed; unplanned work recorded (001's T009 hallucination fix). |
| `analyze` | ⚠️ **Skipped** | The optional cross-artifact consistency check (spec ↔ plan ↔ tasks) was never run. The post-Phase-5 drift this audit found is exactly what `analyze` exists to catch earlier. |
| `checklist` | ⚠️ **Skipped** | Optional requirement-quality checklists never generated. |
| `implement` | ✅ Done ×5 | Implementation followed each phase's tasks; phase gates run (with the two time-boxed exceptions noted above). |
| `converge` (post-hoc reconciliation) | ❌ **Not run when needed** | After the post-Phase-5 hotfix wave, a converge pass (assess codebase vs. specs, append drift as new tasks) was the correct tool and was not used. This audit is effectively that converge pass, performed manually. |

**Honest summary**: the *mandatory* spec-kit chain
(constitution → specify → plan → tasks → implement) was followed for all
five planned features. The *optional-but-recommended* steps (clarify,
analyze, checklist) were skipped entirely, and the framework's mechanism for
handling post-implementation drift (converge) was not used when the drift
actually happened — which is how the Principle II gate violation slipped
through.

---

## Part 3 — Remediation log

| # | Finding | Action | Status |
| --- | --- | --- | --- |
| R1 | P-II gate not re-run after prompt/KB/top_k changes | Full `tests/test_rag_qa.py` re-run | ✅ Done — result below |
| R2 | Post-Phase-5 drift undocumented in specs | Change-log appendix added to `specs/001-rag-base/tasks.md` and `specs/003-streaming-e2e/tasks.md` | ✅ Done |
| R3 | Latency report/README metrics stale | Fresh post-optimization measurement + regenerated report | ⏳ Queued (folded into 006 tasks) |
| R4 | Debug instrumentation still shipped | Remove/gate after mic issue confirmed closed | ⏳ Queued (folded into 006 tasks) |
| R5 | Ghost-turn guard untested | Test added in 006 task list | ⏳ Queued |
| R6 | English-only principle vs. new bilingual requirement | Formal constitution amendment (v1.1.0) + Feature 006 through the full spec-kit flow *including* the previously-skipped clarify/analyze equivalents | ⏳ In progress |

### R1 result — Principle II gate re-run (2026-07-09)

**The audit was immediately vindicated: the first re-run FAILED 9/10.**
The transactions question returned a garbled answer — it named the July 3rd
transfer as the most recent transaction (omitting Trader Joe's, July 7th,
the actual most recent) and shuffled dates. The single-question smoke test
used during the optimization work had not caught this; the 10-question gate
did, on its first re-run.

Root cause: the transactions knowledge-base chunk was one long
semicolon-joined line, which greedy decoding (temperature=0) follows poorly.
Fix: restructured the chunk as a numbered, newline-separated list
("1 = newest"), re-ingested, re-ran the full gate: **10/10 PASSED**.

Lesson recorded: any change touching prompts, knowledge-base text, retrieval
parameters, or decoding options requires a full gate re-run before being
considered done — a smoke test is not a gate.
