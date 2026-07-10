"""Voice activity detection for end-of-turn detection (RF-01/RNF-03).

webrtcvad classifies fixed-size frames (10/20/30ms) as speech/non-speech.
EndOfTurnDetector tracks trailing silence after speech has started and
declares end-of-turn once that silence exceeds a threshold — short enough to
feel responsive, long enough not to cut the user off mid-sentence (SM-C1).
"""

import webrtcvad

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_FRAME_MS = 20
DEFAULT_SILENCE_MS_TO_END = 700

# Safety net if VAD never detects trailing silence (e.g. continuous noise):
# force end-of-turn after this much audio rather than waiting indefinitely.
MAX_UTTERANCE_MS = 20000


class EndOfTurnDetector:
    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        frame_ms: int = DEFAULT_FRAME_MS,
        silence_ms_to_end: int = DEFAULT_SILENCE_MS_TO_END,
        aggressiveness: int = 2,
    ):
        self._vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self._silence_frames_to_end = max(1, silence_ms_to_end // frame_ms)
        self._max_frames = MAX_UTTERANCE_MS // frame_ms

        self.has_spoken = False
        self._trailing_silence_frames = 0
        self._total_frames = 0
        self.speech_frame_count = 0

    def process_frame(self, frame: bytes) -> bool:
        """Feed one frame; returns True if this frame marks end-of-turn."""
        self._total_frames += 1
        is_speech = self._vad.is_speech(frame, self.sample_rate)

        if is_speech:
            self.has_spoken = True
            self._trailing_silence_frames = 0
            self.speech_frame_count += 1
        else:
            self._trailing_silence_frames += 1

        if self.has_spoken and self._trailing_silence_frames >= self._silence_frames_to_end:
            return True

        if self._total_frames >= self._max_frames:
            return True

        return False
