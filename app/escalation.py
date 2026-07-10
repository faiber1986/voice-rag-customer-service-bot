"""Cross-cutting escalation decision point (architecture.md AD-5).

Called identically by app/pipeline/sequential.py and app/pipeline/streaming.py
right after a transcript is available, before retrieval/generation — see
specs/004-fallback-escalation/spec.md.
"""

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.rag.retriever import RetrievalResult

ESCALATION_TEXT = "I'll connect you with a human agent right away. One moment please."

# Spanish conversation surface (specs/006, constitution v1.1.0).
ESCALATION_TEXT_ES = "Lo conecto con un agente humano de inmediato. Un momento, por favor."

_EXPLICIT_REQUEST_PHRASES = [
    "talk to a human",
    "speak to a human",
    "speak with a human",
    "human agent",
    "real person",
    "talk to a person",
    "talk to someone",
    "speak to someone",
    "representative",
    "customer service agent",
    "connect me to an agent",
    "speak with a person",
    "speak to a representative",
    # Spanish phrases (specs/006): defense-in-depth — the Spanish-mode
    # translate pass normally yields English text, but if Whisper passes a
    # phrase through untranslated the request must still be honored.
    "hablar con un humano",
    "hablar con una persona",
    "hablar con alguien",
    "agente humano",
    "persona real",
    "un representante",
    "con un agente",
    # Phonetic twins: "un agente humano" and "una gente mano" are
    # indistinguishable in spoken Spanish, and Whisper picks either
    # segmentation (observed in tests/test_language.py). Neither phrase
    # occurs in legitimate banking queries, so false-positive risk is nil.
    "gente mano",
    "hablar con una gente",
]

_write_lock = threading.Lock()


@dataclass
class EscalationResult:
    escalate: bool
    reason: str | None


def contains_explicit_human_request(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _EXPLICIT_REQUEST_PHRASES)


def should_escalate(
    transcript: str, retrieval_result: RetrievalResult | None = None
) -> EscalationResult:
    """The single escalation decision point (architecture.md AD-5).

    Callers check this twice per request: once with `retrieval_result=None`
    right after transcription (catches an explicit request and lets the
    pipeline skip retrieval/generation entirely, per FR-004), and again after
    retrieval with the real `RetrievalResult` (catches ungrounded retrieval).
    """
    if contains_explicit_human_request(transcript):
        return EscalationResult(escalate=True, reason="explicit_request")
    if retrieval_result is not None and not retrieval_result.is_grounded:
        return EscalationResult(escalate=True, reason="ungrounded_retrieval")
    return EscalationResult(escalate=False, reason=None)


def log_escalation(request_id: str, reason: str, transcript: str) -> None:
    path = Path(settings.escalation_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "request_id": request_id,
        "reason": reason,
        "transcript": transcript,
        "timestamp": time.time(),
    }
    line = json.dumps(record)
    with _write_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
