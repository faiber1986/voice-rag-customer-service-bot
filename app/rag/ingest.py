"""Loads the JSON knowledge base and upserts embedded chunks into Chroma.

Run as: python -m app.rag.ingest
"""

import json
from pathlib import Path

import chromadb
import ollama

from app.config import settings

KB_DIR = Path(__file__).parent / "knowledge_base"


def _embed_document(client: ollama.Client, text: str) -> list[float]:
    # nomic-embed-text expects a task prefix; "search_document" is required
    # for indexed content to be comparable against "search_query"-prefixed
    # queries at retrieval time. See app/rag/retriever.py.
    response = client.embeddings(model=settings.embedding_model, prompt=f"search_document: {text}")
    return response["embedding"]


def _load_faq_chunks() -> list[dict]:
    faqs = json.loads((KB_DIR / "faqs.json").read_text(encoding="utf-8"))
    chunks = []
    for faq in faqs:
        text = f"FAQ: {faq['question']}\nAnswer: {faq['answer']}"
        chunks.append(
            {
                "id": faq["id"],
                "text": text,
                "metadata": {"type": "faq", "category": faq["category"], "account_kind": "general"},
            }
        )
    return chunks


def _load_account_chunks() -> list[dict]:
    data = json.loads((KB_DIR / "account_data.json").read_text(encoding="utf-8"))
    customer_name = data["customer_name"]
    chunks = []

    for account in data["accounts"]:
        # The trailing sentence is anti-hallucination armor (see specs/001
        # tasks.md T009), kept short: prompt length drives CPU time-to-first-
        # token, and this chunk is retrieved on nearly every balance query.
        text = (
            f"{customer_name}'s {account['nickname']} ({account['type']} account, "
            f"masked number {account['account_number_masked']}) has a current "
            f"balance of {account['balance']:.2f} {account['currency']}. This "
            f"figure is final and already includes all transactions."
        )
        chunks.append(
            {
                "id": f"account-balance-{account['account_id']}",
                "text": text,
                "metadata": {
                    "type": "account_balance",
                    "account_id": account["account_id"],
                    "account_kind": account["type"],
                },
            }
        )

    by_account: dict[str, list[dict]] = {}
    for txn in data["transactions"]:
        by_account.setdefault(txn["account_id"], []).append(txn)

    account_lookup = {a["account_id"]: a for a in data["accounts"]}

    for account_id, txns in by_account.items():
        account = account_lookup[account_id]
        txns_sorted = sorted(txns, key=lambda t: t["date"], reverse=True)
        # Numbered, newline-separated: a single long semicolon-joined line
        # caused the LLM (greedy decoding) to garble transaction order and
        # skip the most recent entries — caught by the tests/test_rag_qa.py
        # gate re-run during the 2026-07-09 SDD compliance audit.
        lines = [
            f"{i}. {t['date']} {t['description']} {t['amount']:+.2f} ({t['category']})"
            for i, t in enumerate(txns_sorted, start=1)
        ]
        newest = txns_sorted[0]
        # The explicit "most recent" prose sentence anchors greedy decoding:
        # without it, the answer to "most recent transactions" flipped between
        # runs (CPU float nondeterminism makes near-tied greedy choices
        # unstable), sometimes starting mid-list — caught twice by the
        # tests/test_rag_qa.py gate.
        summary_text = (
            f"{customer_name}'s {account['nickname']} most recent transaction "
            f"is: {newest['date']} {newest['description']} "
            f"{newest['amount']:+.2f} ({newest['category']}). Full list, "
            f"numbered newest-first:\n" + "\n".join(lines)
        )
        chunks.append(
            {
                "id": f"account-transactions-{account_id}",
                "text": summary_text,
                "metadata": {
                    "type": "account_transactions",
                    "account_id": account_id,
                    "account_kind": account["type"],
                },
            }
        )

    # Deliberately no per-transaction chunks: a bare "$X" transaction line
    # sitting next to the balance chunk in retrieved context reliably tempted
    # the LLM into recomputing the balance by adding/subtracting it (observed
    # during specs/001-rag-base manual testing). The single aggregated
    # "recent transactions" chunk above still answers transaction-history
    # queries without introducing that failure mode.
    return chunks


def ingest() -> int:
    chunks = _load_faq_chunks() + _load_account_chunks()

    ollama_client = ollama.Client(host=settings.ollama_host)
    chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    collection = chroma_client.get_or_create_collection(
        name=settings.chroma_collection, metadata={"hnsw:space": "cosine"}
    )

    ids = [c["id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    embeddings = [_embed_document(ollama_client, text) for text in documents]

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    return len(chunks)


if __name__ == "__main__":
    count = ingest()
    print(f"Ingested {count} chunks into Chroma collection '{settings.chroma_collection}' "
          f"at '{settings.chroma_persist_dir}'.")
