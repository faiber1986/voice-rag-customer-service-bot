import json
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

_write_lock = threading.Lock()


def new_request_id() -> str:
    return str(uuid.uuid4())


class StageTimer:
    """Times one pipeline stage for one request; see architecture.md AD-2.

    Streaming stages call mark_first_partial() once (e.g. on the first LLM
    token or first TTS audio chunk) to additionally capture time-to-first-byte
    separately from total stage duration. `pipeline` tags which orchestration
    produced this record ("sequential" vs "streaming") so
    scripts/latency_report.py can build the Phase 3 before/after comparison.
    """

    def __init__(self, request_id: str, stage: str, pipeline: str = "sequential"):
        self.request_id = request_id
        self.stage = stage
        self.pipeline = pipeline
        self.start_ts: float | None = None
        self.end_ts: float | None = None
        self.first_partial_ts: float | None = None

    def mark_first_partial(self) -> None:
        if self.first_partial_ts is None:
            self.first_partial_ts = time.time()

    def _record(self) -> dict:
        record = {
            "request_id": self.request_id,
            "stage": self.stage,
            "pipeline": self.pipeline,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration_ms": round((self.end_ts - self.start_ts) * 1000, 2),
        }
        if self.first_partial_ts is not None:
            record["first_partial_ts"] = self.first_partial_ts
            record["time_to_first_partial_ms"] = round(
                (self.first_partial_ts - self.start_ts) * 1000, 2
            )
        return record

    def write(self) -> None:
        path = Path(settings.latency_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(self._record())
        with _write_lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


@contextmanager
def stage_timer(request_id: str, stage: str, pipeline: str = "sequential"):
    timer = StageTimer(request_id, stage, pipeline=pipeline)
    timer.start_ts = time.time()
    try:
        yield timer
    finally:
        timer.end_ts = time.time()
        timer.write()
