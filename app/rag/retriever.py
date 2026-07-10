"""Similarity search over the Chroma knowledge base collection.

Implements architecture.md AD-4: retrieve() always returns a similarity score
so callers (app/llm/client.py) can gate generation on retrieval confidence.
"""

from dataclasses import dataclass, field

import chromadb
import ollama

from app.config import settings

_ollama_client = ollama.Client(host=settings.ollama_host)
_chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)


@dataclass
class RetrievedChunk:
    text: str
    metadata: dict
    score: float


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)

    @property
    def top_score(self) -> float:
        return self.chunks[0].score if self.chunks else 0.0

    @property
    def is_grounded(self) -> bool:
        return self.top_score >= settings.retrieval_min_score


def _get_collection():
    return _chroma_client.get_or_create_collection(
        name=settings.chroma_collection, metadata={"hnsw:space": "cosine"}
    )


# Simple keyword hint to disambiguate "checking" vs "savings" at retrieval
# time. Without this, a query naming one account still pulled the other
# account's chunks into context (both are semantically close to "account
# balance"/"recent transactions"), and the LLM conflated the two accounts'
# dates and amounts (observed during specs/001-rag-base manual testing).
# A real intent/entity classifier is Phase 4 scope; this is a minimal,
# single-demo-account-appropriate stopgap (Constitution Principle VI).
# Ordered: pass-through Spanish terms and translation variants first — when
# Whisper's es->en translate pass leaves "cheques" untranslated or renders
# "cuenta corriente" as "current account", those tokens are a stronger signal
# of which account the user actually named than a generic English word that
# may itself be a translation artifact (observed: "saldo" -> "savings").
_ACCOUNT_KIND_KEYWORDS = {
    "cheques": "checking",
    "cheque": "checking",
    "checkbook": "checking",
    "check account": "checking",
    "checks account": "checking",
    "current account": "checking",
    "checking": "checking",
    # "savings" intentionally last: Whisper's es->en translate pass renders
    # "saldo" (balance) as "savings" often enough ("What is the savings of my
    # check account?") that any explicit checking-account token above must win
    # before this generic word is trusted as the account the user named.
    "savings account": "savings",
    "savings": "savings",
    "ahorro": "savings",
}


def _account_kind_hint(query: str) -> str | None:
    lowered = query.lower()
    for keyword, account_kind in _ACCOUNT_KIND_KEYWORDS.items():
        if keyword in lowered:
            return account_kind
    return None


def retrieve(query: str, k: int | None = None) -> RetrievalResult:
    query = query.strip()
    if not query:
        return RetrievalResult(chunks=[])

    collection = _get_collection()
    if collection.count() == 0:
        return RetrievalResult(chunks=[])

    k = k or settings.retrieval_top_k
    # Must match the "search_document" prefix used at ingest time (app/rag/ingest.py)
    # for nomic-embed-text's asymmetric query/document embeddings to be comparable.
    embedding = _ollama_client.embeddings(
        model=settings.embedding_model,
        prompt=f"search_query: {query}",
        keep_alive="30m",  # avoid Ollama unloading/reloading the embedding model between turns
    )["embedding"]

    where = None
    account_kind = _account_kind_hint(query)
    if account_kind:
        where = {"account_kind": {"$in": [account_kind, "general"]}}

    results = collection.query(
        query_embeddings=[embedding], n_results=min(k, collection.count()), where=where
    )

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    chunks = [
        RetrievedChunk(text=doc, metadata=meta, score=max(0.0, 1.0 - dist))
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]

    # Guaranteed-context rule: when the user explicitly named an account, that
    # account's balance chunk MUST be in the context — a degraded/mistranslated
    # phrasing can rank four FAQs above it, and the LLM then fabricated a
    # balance figure from thin air (caught by tests/test_language.py). This
    # does not affect top_score (the grounding gate still reflects natural
    # similarity); it only guarantees the authoritative figure is available
    # when generation happens.
    if account_kind and not any(
        c.metadata.get("type") == "account_balance" for c in chunks
    ):
        balance_results = collection.query(
            query_embeddings=[embedding],
            n_results=1,
            where={"$and": [{"type": "account_balance"}, {"account_kind": account_kind}]},
        )
        if balance_results["documents"][0]:
            chunks.append(
                RetrievedChunk(
                    text=balance_results["documents"][0][0],
                    metadata=balance_results["metadatas"][0][0],
                    score=max(0.0, 1.0 - balance_results["distances"][0][0]),
                )
            )

    return RetrievalResult(chunks=chunks)
