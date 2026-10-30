"""Diagnóstico do ambiente: imprime OK/FALHA por item; código 1 se algo falhar."""
import sys

import httpx
import psycopg
import redis

from app.core.config import get_settings


def checks(s):
    def pg():
        with psycopg.connect(s.database_url, connect_timeout=5) as c:
            c.execute("SELECT 1")

    def vector():
        with psycopg.connect(s.database_url, connect_timeout=5) as c:
            row = c.execute("SELECT 1 FROM pg_available_extensions WHERE name='vector'").fetchone()
            if not row:
                raise RuntimeError("extensão vector indisponível")

    def red():
        redis.Redis.from_url(s.redis_url, socket_connect_timeout=3).ping()

    def tags():
        r = httpx.get(f"{s.ollama_base_url}/api/tags", timeout=5)
        r.raise_for_status()
        return {m["name"] for m in r.json()["models"]}

    def ollama():
        tags()

    def model(name):
        def f():
            names = tags()
            if not any(n == name or n.startswith(name + ":") or n == name + ":latest" for n in names):
                raise RuntimeError(f"modelo {name} ausente")
        return f

    def dim():
        r = httpx.post(f"{s.ollama_base_url}/api/embed",
                       json={"model": s.embedding_model, "input": "teste"}, timeout=s.llm_timeout_seconds)
        r.raise_for_status()
        real = len(r.json()["embeddings"][0])
        if real != s.embedding_dim:
            raise RuntimeError(f"dimensão real {real} ≠ EMBEDDING_DIM {s.embedding_dim}")

    return [
        ("PostgreSQL", f"PostgreSQL indisponível em {s.database_url.split('@')[-1]}", pg),
        ("extensão vector", "extensão vector ausente", vector),
        ("Redis", f"Redis indisponível em {s.redis_url}", red),
        ("Ollama", f"Ollama indisponível em {s.ollama_base_url}", ollama),
        (f"modelo {s.chat_model}", f"modelo {s.chat_model} ausente", model(s.chat_model)),
        (f"modelo {s.embedding_model}", f"modelo {s.embedding_model} ausente", model(s.embedding_model)),
        ("dimensão do embedding", "dimensão do embedding divergente", dim),
    ]


def main() -> int:
    failed = 0
    for label, msg, fn in checks(get_settings()):
        try:
            fn()
            print(f"OK: {label}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FALHA: {msg} ({exc})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
