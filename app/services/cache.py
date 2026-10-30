"""Cache Redis de respostas. Qualquer falha do Redis vira "sem cache", nunca erro para o usuário."""
import hashlib
import json
import logging
import re
import time

import redis

from app.core.config import Settings, get_settings

log = logging.getLogger(__name__)
HITS, MISSES = "papermind:stats:hits", "papermind:stats:misses"
_client = None


def set_client(client) -> None:
    """Para testes: injeta um cliente falso (ou None para recriar)."""
    global _client
    _client = client


def _redis(s: Settings):
    global _client
    if not s.cache_enabled:
        return None
    if _client is None:  # criado uma vez por processo
        _client = redis.Redis.from_url(s.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5,
                                       decode_responses=True)
    return _client


def pipeline_version(s: Settings) -> str:
    parts = [s.chat_model, s.embedding_model, s.top_k, s.chunk_size, s.chunk_overlap,
             s.relevance_threshold, s.grounding_threshold, s.prompt_version, s.verifier_version]
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12]


def make_key(document_id: str, mode: str, question: str, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    normalized = re.sub(r"\s+", " ", question.strip().lower())
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"papermind:qa:{pipeline_version(s)}:{document_id}:{mode}:{digest}"


def _log(status: str, key: str, doc: str, t0: float) -> None:
    log.info("cache=%s key=%s doc=%s ms=%.0f", status, key.rsplit(":", 1)[-1][:12], doc, (time.time() - t0) * 1000)


def get(key: str, document_id: str, settings: Settings | None = None) -> tuple[str, dict | None]:
    """Devolve (cache_status, payload). cache_status: hit | miss | unavailable | disabled."""
    s, t0 = settings or get_settings(), time.time()
    r = _redis(s)
    if r is None:
        _log("DISABLED", key, document_id, t0)
        return "disabled", None
    try:
        raw = r.get(key)
        if raw is not None:
            try:
                payload = json.loads(raw)
            except ValueError:  # valor corrompido: apaga e trata como MISS
                r.delete(key)
                raw = None
        if raw is not None:
            r.incr(HITS)
            _log("HIT", key, document_id, t0)
            return "hit", payload
        r.incr(MISSES)
        _log("MISS", key, document_id, t0)
        return "miss", None
    except redis.RedisError as exc:
        log.warning("Redis indisponível na leitura: %s", exc)
        _log("UNAVAILABLE", key, document_id, t0)
        return "unavailable", None


def set(key: str, payload: dict, settings: Settings | None = None) -> bool:  # noqa: A001
    s = settings or get_settings()
    r = _redis(s)
    if r is None:
        return False
    try:
        r.set(key, json.dumps(payload), ex=s.cache_ttl_seconds)
        return True
    except redis.RedisError as exc:
        log.warning("Redis indisponível na gravação: %s", exc)
        return False


def health(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    r = _redis(s)
    if r is None:
        return {"status": "disabled", "hits": 0, "misses": 0}
    try:
        r.ping()
        return {"status": "ok", "hits": int(r.get(HITS) or 0), "misses": int(r.get(MISSES) or 0)}
    except redis.RedisError:
        return {"status": "unavailable", "hits": 0, "misses": 0}
