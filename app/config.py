from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_host: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    embedding_model: str = "nomic-embed-text"
    chroma_persist_dir: str = "data/chroma"
    chroma_collection: str = "financial_knowledge_base"

    # Recalibrated 2026-07-09 after the KB text restructuring (every chunk
    # re-embed shifts the whole score landscape — the threshold MUST be
    # re-measured whenever knowledge_base content changes). Current landscape,
    # including translation-degraded Spanish variants (specs/006): in-domain
    # 0.717-0.901, out-of-domain 0.507-0.644 — 0.68 sits mid-gap.
    # (Original 001-rag-base calibration was 0.62 for the pre-restructuring
    # chunk texts: in-domain 0.696-0.901 vs out-of-domain 0.511-0.562.)
    retrieval_min_score: float = 0.68
    # Back to 4 (was briefly 3 as a latency micro-optimization): with 3, the
    # checking-balance chunk missed the context for a translation-degraded
    # Spanish query and the LLM answered with a $500 figure lifted from the
    # fees FAQ — a real misgrounding caught by tests/test_language.py.
    # Correctness beats ~1s of prompt-eval time (Constitution SM-C2).
    retrieval_top_k: int = 4

    whisper_model_size: str = "base.en"
    # Multilingual model used only for Spanish mode (specs/006): loaded
    # lazily on the first Spanish turn so English-only usage pays no RAM.
    # "small" (not "base"): base's es->en translation mangled domain terms
    # even with a glossary prompt ("cuenta de cheques" -> "Czech account" /
    # "account of checkers"), failing the feature gate; small translates
    # these reliably at ~2x the decode cost, Spanish-mode only.
    whisper_multilingual_model: str = "small"
    piper_voice: str = "en_US-lessac-medium"
    piper_voice_es: str = "es_MX-ald-medium"

    escalation_min_intent_confidence: float = 0.55

    latency_log_path: str = "logs/latency.jsonl"
    escalation_log_path: str = "logs/escalations.jsonl"


settings = Settings()
