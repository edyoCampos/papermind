import json
import logging

import pytest
import redis

from app.agents.common import Deps
from app.core.config import Settings
from app.rag.retriever import RetrievalResult
from app.repositories.chunks import Evidence
from app.services import cache, qa
from tests.test_graph import GOOD, FakeEmb, FakeLLM, deps as make_deps

S = Settings()


class FakeRedis:
    def __init__(self, fail=False):
        self.data, self.ttl, self.fail = {}, {}, fail

    def _chk(self):
        if self.fail:
            raise redis.ConnectionError("down")

    def get(self, k):
        self._chk()
        return self.data.get(k)

    def set(self, k, v, ex=None):
        self._chk()
        self.data[k], self.ttl[k] = v, ex

    def delete(self, k):
        self.data.pop(k, None)

    def incr(self, k):
        self._chk()
        self.data[k] = str(int(self.data.get(k, 0)) + 1)

    def ping(self):
        self._chk()


@pytest.fixture
def fake():
    f = FakeRedis()
    cache.set_client(f)
    yield f
    cache.set_client(None)


def test_chave_normalizada_e_distinta():
    a = cache.make_key("d1", "auto", "  Qual o  método? ")
    assert a == cache.make_key("d1", "auto", "qual o método?")
    assert a != cache.make_key("d2", "auto", "qual o método?")
    assert a != cache.make_key("d1", "factual", "qual o método?")


def test_pipeline_version_muda_com_limiar():
    assert cache.pipeline_version(S) != cache.pipeline_version(Settings(relevance_threshold=0.9))
    assert cache.make_key("d", "auto", "q", S) != cache.make_key("d", "auto", "q", Settings(grounding_threshold=0.1))


def run(question="Qual foi a acurácia?", llm=None, relevant=True):
    llm = llm or FakeLLM(GOOD)
    return qa.answer_cached("d1", question, "auto", deps=make_deps(llm, relevant=relevant)), llm


def test_miss_depois_hit_sem_executar_grafo(fake, caplog):
    caplog.set_level(logging.INFO)
    first, llm = run()
    assert first["cache_status"] == "miss" and first["cached"] is False
    second, llm2 = run(llm=FakeLLM("NÃO DEVE SER CHAMADO"))
    assert second["cache_status"] == "hit" and second["cached"] is True and llm2.calls == []
    assert second["citations"] == first["citations"] and second["citations"][0]["page_number"] == 3
    assert "cache=MISS" in caplog.text and "cache=HIT" in caplog.text
    assert int(fake.data[cache.HITS]) == 1 and int(fake.data[cache.MISSES]) == 1
    assert cache.health()["hits"] == 1


def test_ttl_na_gravacao(fake):
    run()
    key = cache.make_key("d1", "auto", "Qual foi a acurácia?")
    assert 1 <= fake.ttl[key] <= S.cache_ttl_seconds


def test_insuficiente_e_gravada_mas_erro_nao(fake):
    r, _ = run(relevant=False)
    assert r["status"] == "insufficient" and any(k.startswith("papermind:qa") for k in fake.data)
    fake.data.clear()
    err, _ = run(llm=FakeLLM(error=ConnectionError("x")))
    assert err["status"] == "error" and not [k for k in fake.data if k.startswith("papermind:qa")]


def test_redis_indisponivel_roda_grafo_completo():
    cache.set_client(FakeRedis(fail=True))
    try:
        r, llm = run()
    finally:
        cache.set_client(None)
    assert r["cache_status"] == "unavailable" and len(llm.calls) == 1 and r["status"] == "answered"


def test_valor_corrompido_vira_miss(fake):
    fake.data[cache.make_key("d1", "auto", "Qual foi a acurácia?")] = "{nao-json"
    r, llm = run()
    assert r["cache_status"] == "miss" and len(llm.calls) == 1


def test_cache_desligado_nao_abre_conexao(monkeypatch):
    cache.set_client(None)
    monkeypatch.setattr(cache, "get_settings", lambda: Settings(cache_enabled=False))
    built = []
    monkeypatch.setattr(cache.redis.Redis, "from_url", lambda *a, **k: built.append(1))
    status, payload = cache.get("k", "d")
    assert status == "disabled" and payload is None and built == []


def test_sem_import_de_cache_no_grafo():
    import pathlib
    for p in list(pathlib.Path("app/graph").glob("*.py")) + list(pathlib.Path("app/agents").glob("*.py")):
        assert "cache" not in p.read_text().replace("# ", ""), p


# Versão do verificador na chave: regras novas não reaproveitam respostas aprovadas pelas antigas.

def test_mesma_configuracao_gera_a_mesma_versao_e_chave():
    assert cache.pipeline_version(Settings()) == cache.pipeline_version(Settings())
    assert cache.make_key("d", "auto", "q", Settings()) == cache.make_key("d", "auto", "q", Settings())


def test_mudar_so_a_versao_do_verificador_muda_a_versao():
    base = Settings()
    outra = base.model_copy(update={"verifier_version": "99"})  # qualquer valor diferente do padrão
    assert cache.pipeline_version(base) != cache.pipeline_version(outra)
    assert cache.make_key("d", "auto", "q", base).rsplit(":", 3)[1:] == cache.make_key("d", "auto", "q", outra).rsplit(":", 3)[1:]


def test_mudar_prompt_version_continua_mudando_a_versao():
    assert cache.pipeline_version(Settings()) != cache.pipeline_version(Settings(prompt_version="99"))


def test_padrao_do_verificador_e_override_por_ambiente(monkeypatch):
    monkeypatch.delenv("VERIFIER_VERSION", raising=False)
    assert Settings().verifier_version == "3"
    monkeypatch.setenv("VERIFIER_VERSION", "7")
    assert Settings().verifier_version == "7"


def test_resposta_antiga_fica_guardada_mas_nao_e_lida_pela_versao_nova(fake):
    antiga, nova = Settings(verifier_version="1"), Settings(verifier_version="2")
    k_antiga = cache.make_key("d1", "auto", "q", antiga)
    assert cache.set(k_antiga, {"status": "answered"}, antiga)
    k_nova = cache.make_key("d1", "auto", "q", nova)
    assert k_nova != k_antiga
    assert cache.get(k_nova, "d1", nova) == ("miss", None)  # a nova versão não encontra a resposta antiga
    assert k_antiga in fake.data  # e a antiga não foi apagada
