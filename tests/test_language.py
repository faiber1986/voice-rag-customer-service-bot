"""Feature 006 gate: Spanish conversation surface + ghost-turn guard (audit R5).

Spanish audio fixtures are self-synthesized with the es_MX Piper voice, then
run through the streaming pipeline in language="es" mode: Whisper translates
the Spanish speech to English internally, retrieval/grounding operate on
English (constitution v1.1.0 Principle V), and the answer comes back in
Spanish.
"""

import json
from pathlib import Path

import pytest

from app.escalation import ESCALATION_TEXT_ES
from app.llm.client import REFUSAL_TEXT_ES
from app.pipeline.streaming import run_streaming
from app.rag.ingest import ingest
from app.voice.audio_utils import chunk_pcm16, wav_file_to_pcm16
from app.voice.tts import synthesize_bytes

ESCALATION_LOG = Path("logs/escalations.jsonl")


@pytest.fixture(scope="module", autouse=True)
def ingested_knowledge_base():
    ingest()


def _spanish_fixture(tmp_path: Path, text: str) -> Path:
    wav_bytes = synthesize_bytes(text, language="es")
    path = tmp_path / "spanish_question.wav"
    path.write_bytes(wav_bytes)
    return path


async def _frames_from(path: Path):
    pcm = wav_file_to_pcm16(path)
    for frame in chunk_pcm16(pcm):
        yield frame


async def _run_es(path: Path) -> dict:
    events = []
    async for event in run_streaming(_frames_from(path), language="es"):
        events.append(event)
    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    return {"events": events, "done": done[0]}


def _read_escalation_log() -> list[dict]:
    if not ESCALATION_LOG.exists():
        return []
    with ESCALATION_LOG.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.mark.asyncio
async def test_spanish_in_domain_question_grounded_with_correct_figure(tmp_path):
    path = _spanish_fixture(tmp_path, "¿Cuál es el saldo de mi cuenta de cheques?")
    result = await _run_es(path)
    done = result["done"]

    assert done["grounded"], f"Expected grounded (transcript={done['transcript']!r})"
    assert "2483.17" in done["answer"] or "2,483.17" in done["answer"], (
        f"Answer {done['answer']!r} missing the checking balance figure"
    )
    assert len([e for e in result["events"] if e["type"] == "audio_chunk"]) >= 1


@pytest.mark.asyncio
async def test_spanish_out_of_domain_question_refused_in_spanish(tmp_path):
    path = _spanish_fixture(tmp_path, "¿Cómo estará el clima mañana?")
    result = await _run_es(path)
    done = result["done"]

    assert not done["grounded"]
    assert done["answer"] == REFUSAL_TEXT_ES


@pytest.mark.asyncio
async def test_spanish_explicit_human_request_escalates_in_spanish(tmp_path):
    path = _spanish_fixture(tmp_path, "Quiero hablar con un agente humano, por favor.")

    before = len(_read_escalation_log())
    result = await _run_es(path)
    after = _read_escalation_log()

    done = result["done"]
    assert done["answer"] == ESCALATION_TEXT_ES
    assert len(after) == before + 1
    assert after[-1]["reason"] == "explicit_request"


@pytest.mark.asyncio
async def test_spanish_mode_emits_no_partial_transcripts(tmp_path):
    # FR-005: the transcript panel is hidden in Spanish mode, so partial
    # re-transcriptions would be pure wasted STT cost — assert they're skipped.
    path = _spanish_fixture(tmp_path, "¿Cuál es el saldo de mi cuenta de ahorros?")
    result = await _run_es(path)
    assert [e for e in result["events"] if e["type"] == "partial_transcript"] == []


@pytest.mark.asyncio
async def test_ghost_turn_pure_silence_ends_quietly():
    # Audit R5 / FR-008: trailing silence must never speak an unprompted
    # refusal. 2 seconds of digital silence in -> quiet done, no audio.
    async def silence_frames():
        frame = b"\x00" * 640  # 20ms of 16kHz PCM16 silence
        for _ in range(100):
            yield frame

    events = []
    async for event in run_streaming(silence_frames(), language="en"):
        events.append(event)

    done = [e for e in events if e["type"] == "done"]
    assert len(done) == 1
    assert done[0]["answer"] == ""
    assert [e for e in events if e["type"] == "audio_chunk"] == []
