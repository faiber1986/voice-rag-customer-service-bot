"""Phase 3 pipeline: VAD-gated streaming STT -> retrieval -> streaming LLM ->
per-sentence streaming TTS.

Implements architecture.md AD-3: calls the exact same app/rag, app/llm,
app/voice stage functions as app/pipeline/sequential.py. Only orchestration
differs — stages overlap here instead of running fully sequentially — so the
Phase 3 before/after latency comparison isolates the effect of streaming.
"""

import base64
import re
import time
from collections.abc import AsyncIterator

from app.escalation import ESCALATION_TEXT, ESCALATION_TEXT_ES, log_escalation, should_escalate
from app.llm.client import (
    REFUSAL_TEXT,
    REFUSAL_TEXT_ES,
    answer_stream,
    context_figures,
    figures_grounded,
    translate_to_english,
)
from app.logging_utils import StageTimer, new_request_id, stage_timer
from app.rag.retriever import retrieve
from app.voice.stt import transcribe_pcm16
from app.voice.tts import synthesize_bytes
from app.voice.vad import EndOfTurnDetector

# Re-transcribing the whole growing buffer is inherently O(n^2) in utterance
# length (faster-whisper has no incremental decoder — see plan.md Complexity
# Tracking). At 1000ms cadence this dominated real live-mic latency (measured
# 6-43s STT totals); 3000ms keeps the live-caption feel while cutting the
# cumulative re-transcription work ~3x.
PARTIAL_TRANSCRIBE_EVERY_MS = 3000

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")



async def run_streaming(
    audio_frames: AsyncIterator[bytes],
    sample_rate: int = 16000,
    frame_ms: int = 20,
    language: str = "en",
) -> AsyncIterator[dict]:
    request_id = new_request_id()
    detector = EndOfTurnDetector(sample_rate=sample_rate, frame_ms=frame_ms)
    buffer = bytearray()
    ms_since_last_partial = 0

    stt_timer = StageTimer(request_id, "stt", pipeline="streaming")
    stt_timer.start_ts = time.time()

    # Spanish mode hides the transcript panel (specs/006 FR-005), so partial
    # transcriptions would be pure wasted STT cost there.
    emit_partials = language == "en"

    final_transcript = ""
    turn_ended = False
    async for frame in audio_frames:
        buffer.extend(frame)
        ms_since_last_partial += frame_ms
        ended = detector.process_frame(frame)

        if (
            not ended
            and emit_partials
            and detector.has_spoken
            and ms_since_last_partial >= PARTIAL_TRANSCRIBE_EVERY_MS
        ):
            partial_text = transcribe_pcm16(bytes(buffer), sample_rate, final=False)
            stt_timer.mark_first_partial()
            ms_since_last_partial = 0
            yield {"type": "partial_transcript", "text": partial_text}

        if ended:
            final_transcript = transcribe_pcm16(bytes(buffer), sample_rate, language=language)
            stt_timer.mark_first_partial()
            turn_ended = True
            break

    # The frame source can end (client disconnect, or — in tests — a fixture
    # file running out) without VAD ever observing enough trailing silence to
    # declare end-of-turn itself; treat exhaustion as an implicit end-of-turn
    # rather than silently discarding whatever was buffered.
    if not turn_ended and buffer:
        final_transcript = transcribe_pcm16(bytes(buffer), sample_rate, language=language)
        stt_timer.mark_first_partial()

    stt_timer.end_ts = time.time()
    stt_timer.write()

    yield {"type": "final_transcript", "text": final_transcript}

    # Ghost-turn guard: trailing silence after a completed turn (the client
    # keeps streaming quiet frames briefly after release) would otherwise
    # start a new "turn" whose empty/noise transcript flows into retrieval,
    # comes back ungrounded, and speaks an unprompted refusal at the user.
    # If VAD saw no speech at all or STT produced nothing meaningful, end the
    # turn quietly instead.
    if detector.speech_frame_count == 0 or not final_transcript.strip():
        yield {
            "type": "done",
            "transcript": final_transcript,
            "answer": "",
            "grounded": False,
            "top_score": 0.0,
        }
        return

    escalation_text = ESCALATION_TEXT if language == "en" else ESCALATION_TEXT_ES

    escalation = should_escalate(final_transcript)
    if escalation.escalate:
        # Explicit request: skip retrieval/generation entirely (FR-004) and
        # emit the fixed escalation message as a single chunk, same shape as
        # a normal one-sentence answer so clients don't need a special case.
        log_escalation(request_id, escalation.reason, final_transcript)
        with stage_timer(request_id, "retrieval", pipeline="streaming"):
            pass
        yield {"type": "retrieval_done", "grounded": False, "top_score": 0.0}

        with stage_timer(request_id, "llm", pipeline="streaming") as llm_timer:
            llm_timer.mark_first_partial()
            yield {"type": "answer_token", "text": escalation_text}

        with stage_timer(request_id, "tts", pipeline="streaming") as tts_timer:
            audio_bytes = synthesize_bytes(escalation_text, language=language)
            tts_timer.mark_first_partial()

        yield {
            "type": "audio_chunk",
            "index": 1,
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
        }
        yield {
            "type": "done",
            "transcript": final_transcript,
            "answer": escalation_text,
            "grounded": False,
            "top_score": 0.0,
        }
        return

    # Spanish mode: the transcript is native Spanish (reliable transcription);
    # translate it to English via the LLM for retrieval — whisper's translate
    # head was measured unstable run-to-run on identical audio ("saldo" ->
    # save/sale/fate), while LLM text translation is consistent. The explicit
    # human-request check above already ran on the Spanish text using the
    # Spanish keyword list, so an escalation never pays for translation.
    query_text = final_transcript
    if language == "es":
        with stage_timer(request_id, "translate", pipeline="streaming"):
            query_text = translate_to_english(final_transcript)

    with stage_timer(request_id, "retrieval", pipeline="streaming"):
        retrieval_result = retrieve(query_text)
    yield {
        "type": "retrieval_done",
        "grounded": retrieval_result.is_grounded,
        "top_score": retrieval_result.top_score,
    }

    escalation = should_escalate(query_text, retrieval_result)
    if escalation.escalate:
        log_escalation(request_id, escalation.reason, final_transcript)

    llm_timer = StageTimer(request_id, "llm", pipeline="streaming")
    llm_timer.start_ts = time.time()
    tts_timer = StageTimer(request_id, "tts", pipeline="streaming")
    tts_timer.start_ts = time.time()

    # Per-sentence figure guard (AD-4 extension): every number in a sentence
    # must exist in the retrieved context BEFORE that sentence's audio is
    # synthesized — in a voice bot, once a fabricated figure is spoken it
    # cannot be unspoken. Checked per sentence rather than post-hoc because
    # audio streams out per sentence.
    allowed_figures = context_figures(retrieval_result)
    refusal_text = REFUSAL_TEXT if language == "en" else REFUSAL_TEXT_ES
    guard_tripped = False

    sentence_buffer = ""
    full_answer = ""
    chunk_index = 0

    for token in answer_stream(query_text, retrieval_result, language=language):
        llm_timer.mark_first_partial()
        full_answer += token
        sentence_buffer += token
        yield {"type": "answer_token", "text": token}

        parts = _SENTENCE_END_RE.split(sentence_buffer)
        if len(parts) > 1:
            *complete_sentences, sentence_buffer = parts
            for sentence in complete_sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if not figures_grounded(sentence, allowed_figures):
                    guard_tripped = True
                    break
                audio_bytes = synthesize_bytes(sentence, language=language)
                tts_timer.mark_first_partial()
                chunk_index += 1
                yield {
                    "type": "audio_chunk",
                    "index": chunk_index,
                    "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
                }
        if guard_tripped:
            break

    if guard_tripped:
        # Replace the whole answer with the refusal: the tainted sentence was
        # never synthesized, and the displayed answer is corrected too.
        full_answer = refusal_text
        yield {"type": "answer_token", "text": f" {refusal_text}"}
        audio_bytes = synthesize_bytes(refusal_text, language=language)
        tts_timer.mark_first_partial()
        chunk_index += 1
        yield {
            "type": "audio_chunk",
            "index": chunk_index,
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
        }
        sentence_buffer = ""

    # LLM generation is done the moment the token loop ends — stop its timer
    # here, before any trailing-sentence TTS work, so llm.duration_ms reflects
    # token generation (interleaved mid-stream TTS calls still count, since
    # this implementation is single-threaded and they really do delay the
    # next token — see specs/003-streaming-e2e Design Decisions) and isn't
    # further inflated by the final chunk's synthesis, which is TTS's cost.
    llm_timer.end_ts = time.time()
    llm_timer.write()

    trailing = sentence_buffer.strip()
    if trailing:
        if figures_grounded(trailing, allowed_figures):
            audio_bytes = synthesize_bytes(trailing, language=language)
            tts_timer.mark_first_partial()
            chunk_index += 1
            yield {
                "type": "audio_chunk",
                "index": chunk_index,
                "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            }
        else:
            guard_tripped = True
            full_answer = refusal_text
            yield {"type": "answer_token", "text": f" {refusal_text}"}
            audio_bytes = synthesize_bytes(refusal_text, language=language)
            tts_timer.mark_first_partial()
            chunk_index += 1
            yield {
                "type": "audio_chunk",
                "index": chunk_index,
                "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            }

    tts_timer.end_ts = time.time()
    tts_timer.write()

    yield {
        "type": "done",
        "transcript": final_transcript,
        "answer": full_answer,
        "grounded": retrieval_result.is_grounded and not guard_tripped,
        "top_score": retrieval_result.top_score,
    }
