"""Phase 2 gate: the same 10-question set, now driven end-to-end through
audio (STT -> retrieval -> LLM -> TTS), matching Phase 1's text-pipeline
correctness (Constitution Principle II: no hallucination).
"""

from pathlib import Path

import pytest

from app.llm.client import REFUSAL_TEXT
from app.pipeline.sequential import run_sequential
from app.rag.ingest import ingest
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


@pytest.mark.parametrize("question,expected_substrings", IN_DOMAIN_CASES)
def test_audio_in_domain_question_is_grounded_and_correct(question, expected_substrings):
    audio_path = _fixture_path(question)

    result = run_sequential(audio_path)

    assert result.grounded
    assert any(s in result.answer_text for s in expected_substrings), (
        f"Answer '{result.answer_text}' did not contain any of {expected_substrings}"
    )
    assert result.output_audio_path.exists()
    assert result.output_audio_path.stat().st_size > 1000


@pytest.mark.parametrize("question", OUT_OF_DOMAIN_QUESTIONS)
def test_audio_out_of_domain_question_is_refused(question):
    audio_path = _fixture_path(question)

    result = run_sequential(audio_path)

    assert not result.grounded
    assert result.answer_text == REFUSAL_TEXT
    assert result.output_audio_path.exists()
    assert result.output_audio_path.stat().st_size > 1000
