"""Serviços injetáveis: os testes trocam este objeto com app.dependency_overrides."""
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from app.core.config import get_settings
from app.core.errors import DocumentNotFoundError
from app.db.connection import connect


@dataclass
class Services:
    register_document: Callable[[str], Any]
    index_document: Callable[[Any, bytes, str], None]
    get_document: Callable[[str], Any]  # -> Document; DocumentNotFoundError se não existir
    count_chunks: Callable[[str], int]
    answer_question: Callable[..., dict]
    get_summary: Callable[[str], dict]
    health: Callable[[], dict]


def parse_id(document_id: str) -> str:
    try:
        return str(uuid.UUID(document_id))
    except ValueError:
        raise DocumentNotFoundError() from None


def _health() -> dict:
    s = get_settings()
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        db = "ok"
    except Exception:  # noqa: BLE001
        db = "unavailable"
    try:
        httpx.get(f"{s.ollama_base_url}/api/tags", timeout=2).raise_for_status()
        ollama = "ok"
    except Exception:  # noqa: BLE001
        ollama = "unavailable"
    try:  # cache real: feature cache-redis
        from app.services.cache import health as cache_health
        cache = cache_health()
    except ModuleNotFoundError:
        cache = {"status": "disabled", "hits": 0, "misses": 0}
    return {"status": "ok", "dependencies": {"database": db, "ollama": ollama, "cache": cache}}


def get_services() -> Services:
    from app.repositories import chunks as chunk_repo
    from app.repositories import documents as doc_repo
    from app.services import indexing, qa

    def get_document(doc_id):
        with connect() as conn:
            return doc_repo.get_document(conn, doc_id)

    def count_chunks(doc_id):
        with connect() as conn:
            return chunk_repo.count_chunks(conn, doc_id)

    return Services(indexing.register_document, indexing.index_document, get_document, count_chunks,
                    qa.answer_cached, qa.get_or_create_summary, _health)
