"""Lightweight intent classification via a short LLM prompt (PRD FR-2).

Logged for observability alongside every request; per
specs/004-fallback-escalation/spec.md Assumptions, intent confidence alone
does not gate escalation (see app/escalation.py) — only ungrounded retrieval
and explicit human requests do, since those have direct evidence the system
actually can't help.
"""

import json
from dataclasses import dataclass

import ollama

from app.config import settings

_client = ollama.Client(host=settings.ollama_host)

INTENT_LABELS = [
    "balance_inquiry",
    "transaction_inquiry",
    "faq",
    "complaint_or_escalation",
    "out_of_domain",
]

_SYSTEM_PROMPT = (
    "Classify the user's banking customer-service query into exactly one of "
    "these intents: " + ", ".join(INTENT_LABELS) + ". "
    "Respond with ONLY a JSON object: {\"intent\": \"<label>\", "
    "\"confidence\": <0.0-1.0>}. No other text."
)


@dataclass
class IntentResult:
    label: str
    confidence: float


def classify_intent(query: str) -> IntentResult:
    query = query.strip()
    if not query:
        return IntentResult(label="unknown", confidence=0.0)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    response = _client.chat(
        model=settings.llm_model, messages=messages, stream=False, options={"temperature": 0}
    )
    content = response["message"]["content"].strip()

    try:
        data = json.loads(content)
        label = data.get("intent", "unknown")
        confidence = float(data.get("confidence", 0.0))
        if label not in INTENT_LABELS:
            label = "unknown"
        return IntentResult(label=label, confidence=confidence)
    except (json.JSONDecodeError, TypeError, ValueError):
        return IntentResult(label="unknown", confidence=0.0)
