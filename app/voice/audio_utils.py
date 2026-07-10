"""PCM16 conversion helpers used to simulate streaming audio frames from a
.wav file (tests) and, on the real path, to normalize whatever a browser
sends before it reaches VAD/STT.
"""

import audioop
import wave
from pathlib import Path

BYTES_PER_SAMPLE = 2  # 16-bit PCM


def wav_file_to_pcm16(path: str | Path, target_rate: int = 16000) -> bytes:
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    if n_channels == 2:
        raw = audioop.tomono(raw, sample_width, 0.5, 0.5)

    if sample_width != BYTES_PER_SAMPLE:
        raw = audioop.lin2lin(raw, sample_width, BYTES_PER_SAMPLE)

    if frame_rate != target_rate:
        raw, _ = audioop.ratecv(raw, BYTES_PER_SAMPLE, 1, frame_rate, target_rate, None)

    return raw


def chunk_pcm16(pcm_bytes: bytes, sample_rate: int = 16000, frame_ms: int = 20) -> list[bytes]:
    frame_size = int(sample_rate * frame_ms / 1000) * BYTES_PER_SAMPLE
    frames = [
        pcm_bytes[i : i + frame_size] for i in range(0, len(pcm_bytes) - frame_size + 1, frame_size)
    ]
    return frames
