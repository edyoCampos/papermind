"""Configuração central: tudo vem de variáveis de ambiente (ver .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql://papermind:papermind_dev@postgres:5432/papermind"
    redis_url: str = "redis://redis:6379/0"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600

    ollama_base_url: str = "http://ollama:11434"
    chat_model: str = "qwen2.5:3b"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
    llm_num_predict: int = 400
    llm_timeout_seconds: int = 180

    max_upload_mb: int = 20
    max_pages: int = 60
    chunk_size: int = 800
    chunk_overlap: int = 120
    top_k: int = 5
    relevance_threshold: float = 0.55
    grounding_threshold: float = 0.60
    prompt_version: str = "1"
    verifier_version: str = "3"  # suba ao mudar as regras ou o feedback do verificador; entra na chave do cache

    api_url: str = "http://app:8000"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
