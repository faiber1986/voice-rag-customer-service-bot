"""Local Ollama LLM wrapper for grounded answer generation.

Implements architecture.md AD-4 (no-hallucination gate): when the retrieval
result is not grounded, this module returns REFUSAL_TEXT without calling the
LLM in open-ended mode. A second, post-generation guard verifies every
numeric figure in the answer exists in the retrieved context — the model was
caught fabricating a balance ("$1,200") that appeared nowhere in context
(tests/test_language.py, 2026-07-09), and prompt instructions alone did not
prevent it.
"""

import re
from dataclasses import dataclass

import ollama

from app.config import settings
from app.rag.retriever import RetrievalResult

REFUSAL_TEXT = (
    "I don't have that information in my knowledge base. "
    "Would you like me to connect you with a human agent for more help?"
)

# Spanish conversation surface (specs/006, constitution v1.1.0).
REFUSAL_TEXT_ES = (
    "No tengo esa información en mi base de conocimiento. "
    "¿Le gustaría que lo conecte con un agente humano para ayudarle mejor?"
)

_RESPOND_IN_SPANISH = (
    "Respond in Spanish (the CONTEXT is in English; translate the facts "
    "faithfully, keeping every figure exactly as given)."
)


def translate_to_english(text: str) -> str:
    """Translates a short Spanish utterance to English for retrieval
    (specs/006): whisper's built-in translate head proved unstable, while
    text translation is a core LLM strength. Greedy, tightly capped."""
    response = _client.chat(
        model=settings.llm_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Translate the user's Spanish message to English using "
                    "standard US banking terms (say 'checking account' for "
                    "'cuenta de cheques'/'cuenta corriente', 'savings "
                    "account' for 'cuenta de ahorros', 'balance' for "
                    "'saldo'). Output ONLY the English translation, nothing "
                    "else."
                ),
            },
            {"role": "user", "content": text},
        ],
        stream=False,
        options={"temperature": 0, "num_predict": 60, "num_ctx": 2048},
        keep_alive=_KEEP_ALIVE,
    )
    return response["message"]["content"].strip()

# Kept deliberately compact: on CPU, time-to-first-token scales with prompt
# length (measured ~15s at ~600 prompt tokens on this machine), and this
# system prompt is re-evaluated every turn. The balance rule survives in
# shortened form — it fixed a real observed hallucination (see specs/001
# tasks.md T009) and must not be dropped.
SYSTEM_PROMPT = (
    "You are a concise voice assistant for a bank's customer service line. "
    "Answer ONLY from the CONTEXT below; never invent balances, transactions, "
    "fees, rates, or policies. Balance figures in CONTEXT are final — copy "
    "them exactly; never add or subtract transaction amounts from them. List "
    "transactions in the order given. Keep answers to 1-3 spoken-style "
    "sentences."
)

_client = ollama.Client(host=settings.ollama_host)


@dataclass
class AnswerResult:
    text: str
    grounded: bool


_SECTION_HEADERS = {
    "account_balance": "ACCOUNT BALANCE (authoritative — state this figure exactly as given; it is already final and must never be recomputed):",
    "account_transactions": "RECENT ACTIVITY (background only — already fully reflected in the ACCOUNT BALANCE above; never add or subtract these amounts from the balance):",
    "faq": "RELEVANT POLICY INFORMATION:",
}


def _build_context(retrieval_result: RetrievalResult) -> str:
    # Grouping by chunk type under distinct headers (rather than one flat
    # blob) measurably reduced balance-recomputation hallucinations during
    # specs/001-rag-base manual testing — a balance chunk sitting inline next
    # to a transaction amount was the strongest trigger for it.
    by_type: dict[str, list[str]] = {}
    for chunk in retrieval_result.chunks:
        chunk_type = chunk.metadata.get("type", "faq")
        by_type.setdefault(chunk_type, []).append(chunk.text)

    sections = []
    for chunk_type in ("account_balance", "account_transactions", "faq"):
        texts = by_type.get(chunk_type)
        if texts:
            header = _SECTION_HEADERS[chunk_type]
            sections.append(header + "\n" + "\n".join(texts))

    return "\n\n".join(sections)


def _build_messages(
    query: str, retrieval_result: RetrievalResult, language: str = "en"
) -> list[dict]:
    context = _build_context(retrieval_result)
    system = SYSTEM_PROMPT if language == "en" else f"{SYSTEM_PROMPT} {_RESPOND_IN_SPANISH}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {query}"},
    ]


# Greedy decoding: this is factual grounded QA, not creative writing. Sampling
# with the default temperature measurably increased balance-recomputation
# hallucinations during specs/001-rag-base manual testing; temperature=0
# removed them in side-by-side comparison on the same prompts.
# num_predict caps worst-case generation length: greedy decoding on small
# models can fall into repetition loops that never hit a natural stop, and a
# voice assistant answer should be short regardless (SYSTEM_PROMPT already
# asks for 1-3 sentences) — this is a hard backstop, not the primary control.
# num_ctx=2048: Ollama's default loaded llama3.2:3b with a 16384-token
# context window (4.1GB resident), which on this 16GB machine with ~2GB free
# caused constant page-thrash between whisper and the LLM (measured 7-9s
# time-to-first-token from weight paging alone). Our grounded-QA prompts run
# ~300-500 tokens, so 2048 is ample and halves the resident footprint.
_GENERATION_OPTIONS = {"temperature": 0, "num_predict": 200, "num_ctx": 2048}

# Ollama unloads a model after ~5 minutes idle by default; the reload cost
# (several seconds on this CPU) then lands on whichever unlucky request comes
# next. Keep the chat model resident between demo interactions.
_KEEP_ALIVE = "30m"

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def extract_figures(text: str) -> set[float]:
    figures = set()
    for match in _NUMBER_RE.finditer(text):
        try:
            figures.add(float(match.group(0).replace(",", "")))
        except ValueError:
            continue
    return figures


def context_figures(retrieval_result: RetrievalResult) -> set[float]:
    return extract_figures(" ".join(chunk.text for chunk in retrieval_result.chunks))


def figures_grounded(text: str, allowed: set[float]) -> bool:
    """True iff every numeric figure in `text` appears in `allowed` (the
    numbers present in the retrieved context). Conservative by design: a
    correct-but-recomputed figure gets refused rather than trusted
    (Constitution SM-C2 — refusing is cheaper than being wrong)."""
    return all(any(abs(n - c) < 0.005 for c in allowed) for n in extract_figures(text))


def answer(query: str, retrieval_result: RetrievalResult) -> AnswerResult:
    if not retrieval_result.is_grounded:
        return AnswerResult(text=REFUSAL_TEXT, grounded=False)

    messages = _build_messages(query, retrieval_result)
    response = _client.chat(
        model=settings.llm_model,
        messages=messages,
        stream=False,
        options=_GENERATION_OPTIONS,
        keep_alive=_KEEP_ALIVE,
    )
    text = response["message"]["content"].strip()

    if not figures_grounded(text, context_figures(retrieval_result)):
        return AnswerResult(text=REFUSAL_TEXT, grounded=False)

    return AnswerResult(text=text, grounded=True)


def answer_stream(query: str, retrieval_result: RetrievalResult, language: str = "en"):
    """Yields text chunks as they're generated; used by the Phase 3 streaming pipeline.

    Yields a single refusal chunk (not streamed token-by-token) when
    ungrounded, so callers can treat both paths as an iterable of str chunks.
    """
    if not retrieval_result.is_grounded:
        yield REFUSAL_TEXT if language == "en" else REFUSAL_TEXT_ES
        return

    messages = _build_messages(query, retrieval_result, language)
    for part in _client.chat(
        model=settings.llm_model,
        messages=messages,
        stream=True,
        options=_GENERATION_OPTIONS,
        keep_alive=_KEEP_ALIVE,
    ):
        content = part["message"]["content"]
        if content:
            yield content
