"""Redis real do Compose."""
import time

import httpx
import pytest
import redis

from app.core.config import Settings, get_settings
from app.services import cache, qa
from tests.test_graph import GOOD, FakeLLM, deps as make_deps

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def real_client():
    cache.set_client(None)
    yield
    cache.set_client(None)


def test_miss_hit_ttl_e_contadores_reais():
    r = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    doc = f"doc-{time.time()}"
    d = make_deps(FakeLLM(GOOD))
    a = qa.answer_cached(doc, "Qual foi a acurácia?", "auto", deps=d)
    t0 = time.time()
    b = qa.answer_cached(doc, "qual foi a acurácia?", "auto", deps=d)
    assert (a["cache_status"], b["cache_status"]) == ("miss", "hit") and (time.time() - t0) < 0.2
    key = cache.make_key(doc, "auto", "Qual foi a acurácia?")
    assert 0 < r.ttl(key) <= get_settings().cache_ttl_seconds
    h = cache.health()
    assert h["status"] == "ok" and h["hits"] >= 1 and h["misses"] >= 1


def test_redis_inexistente_responde_pelo_fluxo_completo(monkeypatch):
    monkeypatch.setattr(cache, "get_settings", lambda: Settings(redis_url="redis://redis-inexistente:6379/0"))
    llm = FakeLLM(GOOD)
    t0 = time.time()
    r = qa.answer_cached("doc-x", "Qual foi a acurácia?", "auto", deps=make_deps(llm))
    assert r["cache_status"] == "unavailable" and len(llm.calls) == 1 and r["status"] == "answered"
    assert time.time() - t0 <= 3  # 2 operações x 0,5 s + folga de DNS


def test_health_da_api_mostra_cache():
    j = httpx.get("http://app:8000/health", timeout=10).json()
    assert j["dependencies"]["cache"]["status"] == "ok"
