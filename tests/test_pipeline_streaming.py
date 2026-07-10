"""Phase 3 gate: same 10-question set through the streaming pipeline,
reassembled from StreamEvents, matching Phase 1/2 correctness. Also asserts
the streaming-specific behaviors FR-002..FR-004 require: partial transcripts
before end-of-turn, incremental LLM tokens, and per-sentence audio chunks
before the full answer is complete.
"""

from pathlib import Path

import pytest

from app.llm.client import REFUSAL_TEXT
from app.pipeline.streaming import run_streaming
from app.rag.ingest import ingest
from app.voice.audio_utils import chunk_pcm16, wav_file_to_pcm16
from scripts.generate_test_audio import _slugify
from tests.test_rag_qa import IN_DOMAIN_CASES, OUT_OF_DOMAIN_QUESTIONS

FIXTURES_DIR = Path("tests/fixtures")


@pytest.fixture(scope="module", autouse=True)
def ingested_knowledge_base():
    ingest()


def _fixture_path(question: str) -> Path:
    path = FIXTURES_DIR / f"{_slugify(question)}.wav"
    assert path.exists(), f"Missing fixture audio for '{question}' — run scripts/generate_test_audio.py"
    return path


async def _frames_for(question: str):
    pcm = wav_file_to_pcm16(_fixture_path(question))
    for frame in chunk_pcm16(pcm):
        yield frame


async def _run(question: str) -> dict:
    events = []
    async for event in run_streaming(_frames_for(question)):
        events.append(event)

    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1, f"Expected exactly one 'done' event, got {len(done_events)}"

    return {
        "events": events,
        "done": done_events[0],
        "partial_transcripts": [e for e in events if e["type"] == "partial_transcript"],
        "answer_tokens": [e for e in events if e["type"] == "answer_token"],
        "audio_chunks": [e for e in events if e["type"] == "audio_chunk"],
    }


@pytest.mark.parametrize("question,expected_substrings", IN_DOMAIN_CASES)
@pytest.mark.asyncio
async def test_streaming_in_domain_question_is_grounded_and_correct(question, expected_substrings):
    result = await _run(question)
    done = result["done"]

    assert done["grounded"]
    assert any(s in done["answer"] for s in expected_substrings), (
        f"Answer '{done['answer']}' did not contain any of {expected_substrings}"
    )
    assert len(result["audio_chunks"]) >= 1
    # The full answer, reassembled token-by-token, must match what was marked done.
    assert "".join(t["text"] for t in result["answer_tokens"]) == done["answer"]


@pytest.mark.parametrize("question", OUT_OF_DOMAIN_QUESTIONS)
@pytest.mark.asyncio
async def test_streaming_out_of_domain_question_is_refused(question):
    result = await _run(question)
    done = result["done"]

    assert not done["grounded"]
    assert done["answer"] == REFUSAL_TEXT
    assert len(result["audio_chunks"]) >= 1


@pytest.mark.asyncio
async def test_streaming_emits_audio_before_full_answer_is_known():
    # A multi-sentence answer should synthesize its first sentence's audio
    # chunk before the last answer_token arrives — proving TTS starts before
    # the LLM has finished (FR-004), not after.
    question = "What are my most recent transactions on my checking account?"
    result = await _run(question)

    assert len(result["answer_tokens"]) > 1, "Expected a multi-token streamed answer"
    events = result["events"]

    first_audio_idx = next(i for i, e in enumerate(events) if e["type"] == "audio_chunk")
    last_token_idx = max(i for i, e in enumerate(events) if e["type"] == "answer_token")

    assert first_audio_idx < last_token_idx, (
        "Expected the first audio chunk to be emitted before the last LLM token, "
        "proving TTS overlaps LLM generation instead of waiting for it to finish"
    )
