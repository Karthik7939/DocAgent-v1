"""
Runtime configuration for the RAG module.

Loads configurable values from environment variables while providing
safe defaults.
"""

from pathlib import Path

# pyrefly: ignore [missing-import]
from pydantic import AliasChoices, Field
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGSettings(BaseSettings):
    """
    Runtime configuration for the RAG system.
    """

    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM

    llm_provider: str = Field(
        default="groq",
        description="LLM provider for semantic query refinement (groq, gemini, ollama, grok).",
    )

    llm_model: str = Field(
        default="llama-3.3-70b-versatile",
        validation_alias=AliasChoices("OLLAMA_MODEL", "RAG_LLM_MODEL", "LLM_MODEL"),
        description="LLM model used for generation.",
    )

    # Groq API keys for the RAG module's semantic query refinement.
    # Falls back to the main app's GROQ_API_KEY when not set separately.
    # Add RAG_GROQ_API_KEY_2 to enable dual-key round-robin load balancing.

    groq_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("RAG_GROQ_API_KEY", "GROQ_API_KEY"),
        description="Primary Groq API key for RAG semantic query refinement.",
    )

    groq_api_key_2: str = Field(
        default="",
        validation_alias=AliasChoices("RAG_GROQ_API_KEY_2"),
        description=(
            "Secondary Groq API key. When set, requests are distributed "
            "round-robin across both keys, doubling the effective rate limit. "
            "Automatically retried on HTTP 429 rate limit responses."
        ),
    )

    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        validation_alias=AliasChoices("RAG_GROQ_MODEL", "LLM_MODEL"),
        description="Groq model for semantic query refinement.",
    )

    # Gemini API key for RAG semantic query refinement.
    # Falls back to the main app's GEMINI_API_KEY when not set separately.
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("RAG_GEMINI_API_KEY", "GEMINI_API_KEY"),
        description="Google Gemini API key for RAG semantic query refinement.",
    )

    gemini_model: str = Field(
        default="gemini-1.5-flash",
        validation_alias=AliasChoices("RAG_GEMINI_MODEL", "LLM_MODEL"),
        description="Gemini model for RAG semantic query refinement.",
    )

    ollama_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "RAG_OLLAMA_BASE_URL"),
        description="Base URL for the local Ollama server.",
    )

    ollama_timeout: int | None = Field(
        default=None,
        validation_alias=AliasChoices("OLLAMA_TIMEOUT", "RAG_OLLAMA_TIMEOUT"),
        ge=1,
        description="Timeout (seconds) for Ollama API requests.",
    )

    ollama_temperature: float | None = Field(
        default=None,
        validation_alias=AliasChoices("OLLAMA_TEMPERATURE", "RAG_OLLAMA_TEMPERATURE"),
        ge=0.0,
        description="Sampling temperature for Ollama generation.",
    )

    ollama_top_p: float | None = Field(
        default=None,
        validation_alias=AliasChoices("OLLAMA_TOP_P", "RAG_OLLAMA_TOP_P"),
        ge=0.0,
        le=1.0,
        description="Top-p sampling value for Ollama generation.",
    )

    ollama_num_ctx: int | None = Field(
        default=None,
        validation_alias=AliasChoices("OLLAMA_NUM_CTX", "RAG_OLLAMA_NUM_CTX"),
        ge=1,
        description="Context window size for Ollama generation.",
    )

    enable_semantic_query_refinement: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "ENABLE_SEMANTIC_QUERY_REFINEMENT",
            "RAG_ENABLE_SEMANTIC_QUERY_REFINEMENT",
        ),
        description="Enable optional Groq LLM refinement for retrieval query semantics.",
    )
    enable_semantic_change_llm_classification: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ENABLE_SEMANTIC_CHANGE_LLM_CLASSIFICATION",
            "RAG_ENABLE_SEMANTIC_CHANGE_LLM_CLASSIFICATION",
        ),
        description="Enable optional per-file LLM change classification before query refinement.",
    )

    # Embeddings

    embedding_model: str = Field(
        default="nomic-embed-text",
        description="Embedding model used for vector generation.",
    )

    embedding_batch_size: int = Field(
        default=32,
        ge=1,
        description="Number of chunks processed per embedding batch.",
    )

    embedding_provider: str = Field(
        default="ollama",
        description="Embedding provider (ollama, sentence-transformers, openai).",
    )

    embedding_model_version: str = Field(
        default="1",
        description="Embedding model version used for cache invalidation.",
    )

    embedding_normalize: bool = Field(
        default=True,
        description="Apply L2 normalization to embedding vectors.",
    )

    embedding_max_retries: int = Field(
        default=3,
        ge=0,
        description="Maximum retry attempts for embedding requests.",
    )

    embedding_retry_delay: float = Field(
        default=1.0,
        ge=0.0,
        description="Delay in seconds between embedding retry attempts.",
    )

    # Retrieval

    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of retrieved chunks.",
    )

    similarity_threshold: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum similarity score for retrieval, applied per-channel "
            "before RRF fusion. Kept low deliberately: cosine similarity "
            "from the configured embedding model does not reliably "
            "separate relevant from irrelevant content for the long, "
            "multi-topic queries this system sends (verified empirically — "
            "0.30 discarded genuinely relevant results while still "
            "admitting some irrelevant ones at lower values, i.e. it "
            "wasn't a precision/recall tradeoff, just a bad cutoff). "
            "This threshold only needs to keep the pre-rerank candidate "
            "pool from exploding; rerank_enabled is the real relevance "
            "judge — see reranker.py."
        ),
    )

    query_purpose_symbol_ceiling: int = Field(
        default=50,
        ge=1,
        description="Maximum symbols named in the deterministic purpose fallback.",
    )
    query_keyword_limit: int = Field(
        default=20,
        ge=1,
        description="Maximum noncanonical retrieval keywords emitted per query.",
    )
    query_dependency_keyword_cap: int = Field(
        default=2,
        ge=0,
        description="Maximum dependency-derived keywords emitted per query.",
    )
    query_top_k_symbol_increment: int = Field(
        default=1,
        ge=0,
        description="Additional retrieval results requested for each changed symbol.",
    )
    query_scope_baseline_symbol_count: int = Field(
        default=1,
        ge=0,
        description="Changed-symbol count treated as the baseline retrieval scope.",
    )
    query_top_k_max: int = Field(
        default=100,
        ge=1,
        description="Upper bound for change-derived retrieval result counts.",
    )
    query_similarity_threshold_symbol_step: float = Field(
        default=0.01,
        ge=0.0,
        le=1.0,
        description="Threshold reduction per additional changed symbol.",
    )
    query_similarity_threshold_min: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Lower bound for change-derived similarity thresholds.",
    )
    symbol_rename_similarity_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Minimum normalized structural similarity required to pair a delete and add as a rename.",
    )
    query_keyword_ngram_size: int = Field(
        default=0,
        ge=0,
        description="Canonical symbol n-gram window; zero disables n-gram variants.",
    )
    query_similarity_threshold_precision: int = Field(
        default=4,
        ge=0,
        description="Decimal places used when serializing derived similarity thresholds.",
    )

    rrf_k: int = Field(
        default=60,
        ge=1,
        description="Constant used in Reciprocal Rank Fusion (RRF).",
    )

    # Reranking
    #
    # RRF fusion merges channels by rank position only — each channel's raw
    # score is discarded, so the fused list has no real relevance judgment,
    # only "how early did this show up." Reranking scores the fused
    # candidate pool directly against the query with a cross-encoder before
    # final truncation to top_k.

    rerank_enabled: bool = Field(
        default=True,
        description=(
            "Rerank the RRF-fused candidate pool with a cross-encoder "
            "before truncating to top_k, instead of trusting RRF rank "
            "order alone."
        ),
    )

    rerank_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder model used to rerank retrieval candidates.",
    )

    rerank_candidate_pool: int = Field(
        default=40,
        ge=1,
        description=(
            "Number of RRF-fused candidates fed to the reranker before "
            "truncating to top_k. Must be >= top_k to have any effect."
        ),
    )


    # Chunking

    max_chunk_tokens: int = Field(
        default=1024,
        ge=128,
        description="Maximum tokens allowed in a chunk.",
    )

    chunk_overlap: int = Field(
        default=100,
        ge=0,
        description="Token overlap between adjacent chunks.",
    )

    # Storage

    storage_root: Path = Field(
        default=Path("rag/storage"),
        description="Root directory for all persisted indexes.",
    )

    # Logging

    log_level: str = Field(
        default="INFO",
        description="Logging level for the RAG module.",
    )

    # Indexing

    enable_embedding_cache: bool = Field(
        default=True,
        description="Enable embedding cache to avoid recomputation.",
    )

    enable_soft_delete: bool = Field(
        default=True,
        description="Soft delete outdated chunks instead of removing them.",
    )

    # Dependency Graph

    max_dependency_depth: int = Field(
        default=2,
        ge=1,
        description="Maximum traversal depth for dependency retrieval.",
    )

    # Performance

    max_workers: int = Field(
        default=4,
        ge=1,
        description="Maximum number of worker threads.",
    )

    # Vector Store Backend

    vector_store_backend: str = Field(
        default="faiss",
        validation_alias=AliasChoices(
            "RAG_VECTOR_STORE_BACKEND",
            "VECTOR_STORE_BACKEND",
        ),
        description=(
            "Vector store backend to use. "
            "'pinecone' for cloud-hosted Pinecone (per-repo namespaces), "
            "'faiss' for local FAISS file index."
        ),
    )

    # Pinecone

    pinecone_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("PINECONE_API_KEY", "RAG_PINECONE_API_KEY"),
        description="Pinecone API key.",
    )

    pinecone_index_name: str = Field(
        default="code-rag",
        validation_alias=AliasChoices(
            "PINECONE_INDEX_NAME",
            "RAG_PINECONE_INDEX_NAME",
        ),
        description="Name of the Pinecone index to use.",
    )

    pinecone_upsert_batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Number of vectors per Pinecone upsert batch.",
    )


settings = RAGSettings()

