"""Phase 4 gate: explicit human requests always escalate (skipping normal
generation); ungrounded retrieval still refuses exactly as in 001-rag-base
but now also logs an escalation event; in-domain questions never escalate.
"""

import json
from pathlib import Path

import pytest

from app.escalation import ESCALATION_TEXT, contains_explicit_human_request, should_escalate
from app.llm.client import REFUSAL_TEXT
from app.pipeline.sequential import run_sequential
from app.pipeline.streaming import run_streaming
from app.rag.ingest import ingest
from app.rag.retriever import retrieve
from app.voice.audio_utils import chunk_pcm16, wav_file_to_pcm16
from scripts.generate_test_audio import _slugify
from tests.test_rag_qa import IN_DOMAIN_CASES, OUT_OF_DOMAIN_QUESTIONS

FIXTURES_DIR = Path("tests/fixtures")
ESCALATION_LOG = Path("logs/escalations.jsonl")


@pytest.fixture(scope="module", autouse=True)
def ingested_knowledge_base():
    ingest()


def _read_escalation_log() -> list[dict]:
    if not ESCALATION_LOG.exists():
        return []
    with ESCALATION_LOG.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.mark.parametrize(
    "transcript",
    [
        "I want to talk to a human about my balance",
        "Can I speak to a real person please",
        "Get me a representative",
    ],
)
def test_explicit_request_detected(transcript):
    assert contains_explicit_human_request(transcript)
    result = should_escalate(transcript)
    assert result.escalate
    assert result.reason == "explicit_request"


@pytest.mark.parametrize("question,_", IN_DOMAIN_CASES)
def test_in_domain_question_does_not_escalate(question, _):
    retrieval_result = retrieve(question)
    result = should_escalate(question, retrieval_result)
    assert not result.escalate


def test_ungrounded_question_escalates_with_unchanged_refusal_text():
    question = OUT_OF_DOMAIN_QUESTIONS[0]
    retrieval_result = retrieve(question)
    result = should_escalate(question, retrieval_result)
    assert result.escalate
    assert result.reason == "ungrounded_retrieval"


def test_sequential_pipeline_explicit_request_skips_generation(tmp_path):
    from app.voice.tts import synthesize

    audio_path = synthesize(
        "I want to talk to a human agent", tmp_path / "explicit_request.wav"
    )

    before = len(_read_escalation_log())
    result = run_sequential(audio_path)
    after = _read_escalation_log()

    assert result.answer_text == ESCALATION_TEXT
    assert not result.grounded
    assert len(after) == before + 1
    assert after[-1]["reason"] == "explicit_request"


def test_sequential_pipeline_logs_escalation_for_out_of_domain_question():
    question = OUT_OF_DOMAIN_QUESTIONS[1]
    audio_path = FIXTURES_DIR / f"{_slugify(question)}.wav"

    before = len(_read_escalation_log())
    result = run_sequential(audio_path)
    after = _read_escalation_log()

    assert result.answer_text == REFUSAL_TEXT
    assert not result.grounded
    assert len(after) == before + 1
    assert after[-1]["reason"] == "ungrounded_retrieval"


@pytest.mark.asyncio
async def test_streaming_pipeline_logs_escalation_for_out_of_domain_question():
    question = OUT_OF_DOMAIN_QUESTIONS[2]

    async def frames():
        pcm = wav_file_to_pcm16(FIXTURES_DIR / f"{_slugify(question)}.wav")
        for frame in chunk_pcm16(pcm):
            yield frame

    before = len(_read_escalation_log())
    done = None
    async for event in run_streaming(frames()):
        if event["type"] == "done":
            done = event
    after = _read_escalation_log()

    assert done["answer"] == REFUSAL_TEXT
    assert not done["grounded"]
    assert len(after) == before + 1
    assert after[-1]["reason"] == "ungrounded_retrieval"


def test_explicit_escalation_message_is_distinct_from_refusal_text():
    # Sanity: the two fixed strings must not be accidentally identical,
    # otherwise the two escalation reasons would be indistinguishable to a
    # user even though they're logged distinctly.
    assert ESCALATION_TEXT != REFUSAL_TEXT
