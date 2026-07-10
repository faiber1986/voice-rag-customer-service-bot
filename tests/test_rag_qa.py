"""Phase 1 gate (Constitution Principle I): 10-question in/out-of-domain set.

5 in-domain questions must get a correct, grounded answer citing the right
fact from the knowledge base. 5 out-of-domain questions must get an explicit
refusal and never a fabricated financial fact (Constitution Principle II).
"""

import pytest

from app.llm.client import REFUSAL_TEXT, answer
from app.rag.ingest import ingest
from app.rag.retriever import retrieve

IN_DOMAIN_CASES = [
    ("What is my checking account balance?", ["2483.17", "2,483.17"]),
    ("What is my savings account balance?", ["11250.62", "11,250.62"]),
    ("What interest rate do savings accounts earn?", ["2.5%"]),
    ("How long does an external bank transfer take?", ["1-3 business days", "1 to 3 business days"]),
    ("What are my most recent transactions on my checking account?", ["Trader Joe"]),
]

OUT_OF_DOMAIN_QUESTIONS = [
    "What is the weather like tomorrow?",
    "Can you approve me for a 50000 dollar mortgage?",
    "Who won the last presidential election?",
    "Can you recommend a good stock to invest in?",
    "What is the capital of France?",
]


@pytest.fixture(scope="module", autouse=True)
def ingested_knowledge_base():
    ingest()


@pytest.mark.parametrize("question,expected_substrings", IN_DOMAIN_CASES)
def test_in_domain_question_is_grounded_and_correct(question, expected_substrings):
    retrieval_result = retrieve(question)
    assert retrieval_result.is_grounded, (
        f"Expected '{question}' to be grounded (top_score={retrieval_result.top_score:.3f})"
    )

    result = answer(question, retrieval_result)
    assert result.grounded
    assert any(s in result.text for s in expected_substrings), (
        f"Answer '{result.text}' did not contain any of {expected_substrings}"
    )


@pytest.mark.parametrize("question", OUT_OF_DOMAIN_QUESTIONS)
def test_out_of_domain_question_is_refused_not_hallucinated(question):
    retrieval_result = retrieve(question)
    assert not retrieval_result.is_grounded, (
        f"Expected '{question}' to be ungrounded (top_score={retrieval_result.top_score:.3f})"
    )

    result = answer(question, retrieval_result)
    assert not result.grounded
    assert result.text == REFUSAL_TEXT
