"""N3: usa os serviços reais do Compose. Rodar: docker compose run --rm app pytest -m integration"""
import httpx
import psycopg
import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.integration


def test_pgvector_grava_e_busca():
    s = get_settings()
    with psycopg.connect(s.database_url, autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute("CREATE TEMP TABLE t (id int, v vector(3))")
        c.execute("INSERT INTO t VALUES (1,'[1,0,0]'),(2,'[0,1,0]')")
        row = c.execute("SELECT id FROM t ORDER BY v <=> '[0.9,0.1,0]' LIMIT 1").fetchone()
    assert row[0] == 1


def test_ollama_embedding_tem_a_dimensao_configurada():
    s = get_settings()
    r = httpx.post(f"{s.ollama_base_url}/api/embed",
                   json={"model": s.embedding_model, "input": "olá"}, timeout=s.llm_timeout_seconds)
    assert len(r.json()["embeddings"][0]) == s.embedding_dim
