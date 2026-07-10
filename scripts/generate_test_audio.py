"""Self-synthesizes the fixed 10-question test set into .wav fixtures.

Stands in for a real microphone recording per PRD Open Question 1: a coding
agent cannot grant itself live browser microphone permission, so the voice
pipeline tests are validated against Piper-synthesized audio of the same
question set used by tests/test_rag_qa.py. Run as:
    python -m scripts.generate_test_audio
"""

import re
from pathlib import Path

from app.voice.tts import synthesize
from tests.test_rag_qa import IN_DOMAIN_CASES, OUT_OF_DOMAIN_QUESTIONS

FIXTURES_DIR = Path("tests/fixtures")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60]


def generate() -> list[Path]:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    questions = [q for q, _ in IN_DOMAIN_CASES] + OUT_OF_DOMAIN_QUESTIONS

    paths = []
    for question in questions:
        output_path = FIXTURES_DIR / f"{_slugify(question)}.wav"
        synthesize(question, output_path)
        paths.append(output_path)

    return paths


if __name__ == "__main__":
    generated = generate()
    print(f"Generated {len(generated)} fixture audio files in '{FIXTURES_DIR}'.")
