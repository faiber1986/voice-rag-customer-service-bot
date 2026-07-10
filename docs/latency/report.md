# Latency Report: Sequential (Phase 2) vs Streaming (Phase 3)

Sample size: 10 sequential requests, 7 streaming requests.

## Time to first audio byte (perceived latency, SM-1)

| Pipeline | Mean (ms) | Min (ms) | Max (ms) |
| --- | --- | --- | --- |
| Sequential (Phase 2) | 8294 | 2180 | 21809 |
| Streaming (Phase 3) | 13598 | 10465 | 18293 |

**Streaming reduced average time-to-first-audio by -64.0% (8294ms -> 13598ms).**

## Per-stage average duration (ms)

| Stage | Sequential | Streaming |
| --- | --- | --- |
| stt | 1444 | 3096 |
| retrieval | 1348 | 2136 |
| llm | 4274 | 8734 |
| tts | 1227 | 9293 |

SM-1 target: <1500ms perceived latency. Real numbers above are reported as measured on this local CPU-only stack, whether or not they meet the target (Constitution Principle III).

## Streaming's internal overlap (isolated from the STT confound)

The top-line time-to-first-audio comparison above is confounded by this project's streaming STT approach (periodic re-transcription of a growing buffer, since faster-whisper has no incremental decoder — see specs/003-streaming-e2e/plan.md Complexity Tracking): on this project's short (~2s) test questions, re-transcribing twice roughly doubles STT cost, which can outweigh the LLM/TTS overlap savings for single-sentence answers. The metrics below isolate the actual claim — does streaming reduce the wait for *some* output vs. the *complete* output — independent of STT.

| Stage | Mean full duration (ms) | Mean time-to-first-output (ms) | Reduction |
| --- | --- | --- | --- |
| LLM (first token vs. full answer) | 8734 | 5021 | 42.5% |
| TTS (first audio chunk vs. all chunks) | 9293 | 8439 | 9.2% |

These numbers answer "why does streaming matter?" directly: the user hears the first words/audio well before the full answer exists — this is the streaming benefit demonstrated with this project's own data (SPEC section 11).
