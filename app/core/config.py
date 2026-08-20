from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_SECRET_FILE_FIELDS = {
    "database_url": "database_url_file",
    "redis_url": "redis_url_file",
    "qdrant_api_key": "qdrant_api_key_file",
    "github_token": "github_token_file",
    "llm_api_key": "llm_api_key_file",
    "ops_admin_key": "ops_admin_key_file",
    "metrics_admin_key": "metrics_admin_key_file",
}


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
    docs_enabled: bool = True

    trusted_hosts: str = "localhost,127.0.0.1,api,testserver"
    cors_origins: str = ""
    request_max_body_bytes: int = Field(default=65_536, ge=4_096, le=10_485_760)
    max_concurrent_requests: int = Field(default=64, ge=1, le=10_000)
    rate_limit_requests: int = Field(default=120, ge=1, le=100_000)
    rate_limit_window_seconds: float = Field(default=60.0, gt=0.0, le=3_600.0)
    trust_forwarded_for: bool = False

    database_url: str = "postgresql+asyncpg://tractusmind:tractusmind@postgres:5432/tractusmind"
    database_url_file: str | None = None
    redis_url: str = "redis://redis:6379/0"
    redis_url_file: str | None = None

    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    qdrant_api_key_file: str | None = None
    qdrant_collection: str = "tractusmind_knowledge"

    github_token: str | None = None
    github_token_file: str | None = None
    github_timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)
    github_max_attempts: int = Field(default=4, ge=1, le=10)

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_api_key_file: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0.0, le=300.0)
    llm_max_attempts: int = Field(default=3, ge=1, le=6)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1_500, ge=128, le=16_384)
    generation_context_max_chars: int = Field(default=24_000, ge=1_000, le=200_000)
    verification_max_claims: int = Field(default=12, ge=1, le=50)
    history_max_turns: int = Field(default=6, ge=1, le=20)
    history_max_chars: int = Field(default=6_000, ge=500, le=30_000)

    oidc_enabled: bool = False
    oidc_issuer_url: str | None = None
    oidc_audience: str | None = None
    oidc_allowed_algorithms: str = "RS256"
    oidc_role_claims: str = "roles,realm_access.roles,groups"
    oidc_admin_roles: str = ""
    oidc_operator_roles: str = ""
    oidc_display_name_claims: str = "name,preferred_username,email"
    oidc_http_timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)
    oidc_cache_ttl_seconds: int = Field(default=3_600, ge=30, le=86_400)

    provider_retry_base_seconds: float = Field(default=0.5, ge=0.0, le=30.0)
    provider_retry_max_seconds: float = Field(default=8.0, ge=0.1, le=120.0)
    provider_circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    provider_circuit_cooldown_seconds: float = Field(default=30.0, gt=0.0, le=600.0)

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
    source_sync_lock_seconds: int = Field(default=43_200, ge=300, le=604_800)
    ops_admin_key: str | None = None
    ops_admin_key_file: str | None = None

    metrics_enabled: bool = True
    metrics_admin_key: str | None = None
    metrics_admin_key_file: str | None = None
    worker_metrics_port: int = Field(default=9_101, ge=0, le=65_535)
    scheduler_metrics_port: int = Field(default=9_102, ge=0, le=65_535)
    otel_traces_endpoint: str | None = None
    otel_service_name: str = "tractusmind-api"
    otel_sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)

    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket: str = "tractusmind-raw"
    s3_region: str = "auto"

    retrieval_top_k: int = Field(default=20, ge=1, le=100)
    rerank_top_k: int = Field(default=6, ge=1, le=50)
    minimum_relevance_score: float | None = Field(default=None, ge=-100.0, le=100.0)

    @model_validator(mode="after")
    def load_secret_files(self) -> Self:
        for target, file_field in _SECRET_FILE_FIELDS.items():
            secret_file = getattr(self, file_field)
            if not secret_file:
                continue
            path = Path(secret_file)
            try:
                value = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ValueError(f"Unable to read secret file for {target}: {path}") from exc
            object.__setattr__(self, target, value)
        if self.oidc_enabled and not self.oidc_issuer_url:
            raise ValueError("OIDC_ISSUER_URL is required when OIDC_ENABLED=true")
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.database_url

    @property
    def trusted_host_list(self) -> list[str]:
        return self._csv(self.trusted_hosts)

    @property
    def cors_origin_list(self) -> list[str]:
        return self._csv(self.cors_origins)

    @property
    def oidc_algorithm_list(self) -> list[str]:
        return self._csv(self.oidc_allowed_algorithms)

    @property
    def oidc_role_claim_list(self) -> list[str]:
        return self._csv(self.oidc_role_claims)

    @property
    def oidc_admin_role_list(self) -> list[str]:
        return self._csv(self.oidc_admin_roles)

    @property
    def oidc_operator_role_list(self) -> list[str]:
        return self._csv(self.oidc_operator_roles)

    @property
    def oidc_display_name_claim_list(self) -> list[str]:
        return self._csv(self.oidc_display_name_claims)

    @staticmethod
    def _csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
