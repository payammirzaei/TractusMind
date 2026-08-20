from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "TractusMind"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://tractusmind:tractusmind@postgres:5432/tractusmind"
    redis_url: str = "redis://redis:6379/0"

    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "tractusmind_knowledge"

    github_token: str | None = None

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0.0, le=300.0)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1_500, ge=128, le=16_384)
    generation_context_max_chars: int = Field(default=24_000, ge=1_000, le=200_000)
    verification_max_claims: int = Field(default=12, ge=1, le=50)

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = Field(default=32, ge=1, le=256)
    sparse_embedding_model: str = "Qdrant/bm25"
    sparse_embedding_batch_size: int = Field(default=32, ge=1, le=256)
    hybrid_prefetch_k: int = Field(default=40, ge=2, le=500)
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    reranker_batch_size: int = Field(default=32, ge=1, le=128)
    debug_exact_k: int = Field(default=30, ge=1, le=200)
    debug_rrf_k: int = Field(default=60, ge=1, le=500)
    debug_exact_weight: float = Field(default=1.5, gt=0.0, le=10.0)
    debug_hybrid_weight: float = Field(default=1.0, gt=0.0, le=10.0)

    source_sync_interval_seconds: int = Field(default=21_600, ge=300, le=604_800)
    source_sync_lock_seconds: int = Field(default=43_200, ge=600, le=86_400)

    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket: str = "tractusmind-raw"
    s3_region: str = "auto"

    retrieval_top_k: int = Field(default=20, ge=1, le=100)
    rerank_top_k: int = Field(default=6, ge=1, le=50)
    minimum_relevance_score: float | None = Field(default=None, ge=-100.0, le=100.0)

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
