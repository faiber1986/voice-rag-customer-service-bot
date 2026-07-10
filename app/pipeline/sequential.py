"""Phase 2 pipeline: STT -> retrieval -> LLM -> TTS, called strictly in order.

This is the "before" baseline architecture.md AD-3 requires: streaming.py
(Phase 3) calls the same underlying stage functions, only the orchestration
(blocking vs. streaming) differs, so the before/after latency comparison
isolates the effect of streaming rather than different stage implementations.

Phase 4 adds a cross-cutting escalation check (AD-5): an explicit human
request short-circuits retrieval/generation entirely; ungrounded retrieval
still flows through the existing 001-rag-base refusal path, now also logged.
"""

from dataclasses import dataclass
from pathlib import Path

from app.escalation import ESCALATION_TEXT, log_escalation, should_escalate
from app.llm.client import answer
from app.logging_utils import new_request_id, stage_timer
from app.rag.retriever import RetrievalResult, retrieve
from app.voice.stt import transcribe
from app.voice.tts import synthesize

AUDIO_OUT_DIR = Path("data/audio_out")


@dataclass
class PipelineResult:
    request_id: str
    transcript: str
    answer_text: str
    grounded: bool
    top_score: float
    output_audio_path: Path


def run_sequential(audio_path: str | Path) -> PipelineResult:
    request_id = new_request_id()

    with stage_timer(request_id, "stt", pipeline="sequential"):
        transcript = transcribe(audio_path)

    escalation = should_escalate(transcript)
    if escalation.escalate:
        log_escalation(request_id, escalation.reason, transcript)
        with stage_timer(request_id, "retrieval", pipeline="sequential"):
            retrieval_result = RetrievalResult(chunks=[])
        with stage_timer(request_id, "llm", pipeline="sequential"):
            answer_text, grounded = ESCALATION_TEXT, False
    else:
        with stage_timer(request_id, "retrieval", pipeline="sequential"):
            retrieval_result = retrieve(transcript)

        escalation = should_escalate(transcript, retrieval_result)
        if escalation.escalate:
            log_escalation(request_id, escalation.reason, transcript)

        with stage_timer(request_id, "llm", pipeline="sequential"):
            result = answer(transcript, retrieval_result)
            answer_text, grounded = result.text, result.grounded

    output_path = AUDIO_OUT_DIR / f"{request_id}.wav"
    with stage_timer(request_id, "tts", pipeline="sequential"):
        synthesize(answer_text, output_path)

    return PipelineResult(
        request_id=request_id,
        transcript=transcript,
        answer_text=answer_text,
        grounded=grounded,
        top_score=retrieval_result.top_score,
        output_audio_path=output_path,
    )
