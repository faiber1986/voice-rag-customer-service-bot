"""Speech-to-text via faster-whisper (local, English-only per PRD Non-Goals)."""

from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from app.config import settings

_model = WhisperModel(settings.whisper_model_size, device="cpu", compute_type="int8")

# Spanish mode (specs/006): the multilingual model transcribes-and-translates
# Spanish speech to English in one pass (task="translate"), so retrieval and
# the grounding gate keep operating on English text. Lazily loaded — English
# sessions never pay its RAM.
_multilingual_model: WhisperModel | None = None


def _get_multilingual_model() -> WhisperModel:
    global _multilingual_model
    if _multilingual_model is None:
        _multilingual_model = WhisperModel(
            settings.whisper_multilingual_model, device="cpu", compute_type="int8"
        )
    return _multilingual_model

# Two quality tiers, tuned against real live-mic sessions on this CPU:
# - FAST (greedy, beam_size=1): ~3-4x cheaper decode. Used for the periodic
#   partial re-transcriptions of the growing buffer, which are live-caption
#   cosmetics only — an imperfect partial costs nothing.
# - ACCURATE (beam_size=5, the faster-whisper default): used for the final
#   transcription, which is the one retrieval/LLM answer from — a wrong word
#   there ("earn" -> "error") degrades the whole turn, worth ~1-2s extra.
# condition_on_previous_text=False in both: avoids cross-segment state that
# slows decoding and compounds errors on re-transcribed growing buffers.
_COMMON_OPTS = {"condition_on_previous_text": False, "language": "en"}
_FAST_OPTS = {**_COMMON_OPTS, "beam_size": 1}
_ACCURATE_OPTS = {**_COMMON_OPTS, "beam_size": 5}


def transcribe(audio_path: str | Path) -> str:
    segments, _info = _model.transcribe(str(audio_path), **_ACCURATE_OPTS)
    return " ".join(segment.text for segment in segments).strip()


def transcribe_pcm16(
    pcm_bytes: bytes, sample_rate: int = 16000, final: bool = True, language: str = "en"
) -> str:
    """Transcribes a raw 16-bit PCM mono buffer at `sample_rate` (must be 16000
    for faster-whisper to interpret it correctly without file-based resampling).

    Used by the Phase 3 streaming pipeline to re-transcribe a growing audio
    buffer (faster-whisper has no incremental decoder — see
    specs/003-streaming-e2e/plan.md Complexity Tracking). Pass final=False for
    the cheap live-caption partials; final=True uses full beam search.

    language="es" (specs/006) transcribes Spanish speech and translates it to
    English in the same pass, so callers always receive English text.
    """
    if sample_rate != 16000:
        raise ValueError("transcribe_pcm16 requires 16kHz audio")
    if not pcm_bytes:
        return ""

    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    opts = dict(_ACCURATE_OPTS if final else _FAST_OPTS)

    if language == "es":
        # task="transcribe" (NOT "translate"): whisper-small's es->en
        # translate head proved unstable run to run on the same audio
        # ("saldo" -> save/sale/fate, "agente humano" -> "a man"), derailing
        # retrieval and escalation. Native Spanish transcription is far more
        # reliable; the es->en translation for retrieval happens downstream
        # as LLM text translation (app/llm/client.py::translate_to_english),
        # which is a core LLM strength. See specs/006 plan.md.
        #
        # The in-language initial_prompt biases genuinely ambiguous Spanish
        # homophones toward the domain reading ("un agente humano" vs "una
        # gente mano" are phonetically identical). Unlike the abandoned
        # English glossary on the translate task, an in-language context
        # prompt is the intended use of initial_prompt.
        opts["language"] = "es"
        opts["initial_prompt"] = (
            "Llamada de servicio al cliente de un banco. El cliente puede "
            "preguntar por su saldo, su cuenta de cheques, su cuenta de "
            "ahorros, sus transacciones, o pedir hablar con un agente humano."
        )
        segments, _info = _get_multilingual_model().transcribe(audio, **opts)
    else:
        segments, _info = _model.transcribe(audio, **opts)

    return " ".join(segment.text for segment in segments).strip()
