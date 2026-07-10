"""Text-to-speech via Piper (local, English-only voice per PRD Non-Goals)."""

import io
import wave
from pathlib import Path

from piper import PiperVoice

from app.config import settings

_VOICES_DIR = Path("data/models/piper")
_voice = PiperVoice.load(str(_VOICES_DIR / f"{settings.piper_voice}.onnx"))

# Spanish voice (specs/006), lazily loaded — English sessions never pay its RAM.
_voice_es: PiperVoice | None = None


def _get_voice(language: str) -> PiperVoice:
    global _voice_es
    if language == "es":
        if _voice_es is None:
            _voice_es = PiperVoice.load(str(_VOICES_DIR / f"{settings.piper_voice_es}.onnx"))
        return _voice_es
    return _voice


def synthesize(text: str, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav_file:
        _voice.synthesize_wav(text, wav_file)
    return output_path


def synthesize_bytes(text: str, language: str = "en") -> bytes:
    """In-memory WAV synthesis for a single sentence chunk — used by the
    Phase 3 streaming pipeline to emit audio per completed sentence instead
    of waiting for the full answer (FR-005/AD-3)."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        _get_voice(language).synthesize_wav(text, wav_file)
    return buffer.getvalue()
