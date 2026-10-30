"""Cria a extensão vector e confere a dimensão do embedding. Idempotente."""
import sys
import time

import httpx
import psycopg

from app.core.config import get_settings


def embedding_dim(s) -> int:
    r = httpx.post(
        f"{s.ollama_base_url}/api/embed",
        json={"model": s.embedding_model, "input": "teste"},
        timeout=s.llm_timeout_seconds,
    )
    r.raise_for_status()
    return len(r.json()["embeddings"][0])


def main() -> int:
    s = get_settings()
    real = embedding_dim(s)
    if real != s.embedding_dim:
        print(f"FALHA: dimensão real {real} ≠ EMBEDDING_DIM {s.embedding_dim}")
        return 1
    for attempt in range(10):
        try:
            with psycopg.connect(s.database_url, autocommit=True) as conn:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                try:  # esquema completo: feature indexacao-recuperacao
                    from app.db.schema import ensure_schema

                    ensure_schema(conn)
                except ModuleNotFoundError:
                    pass
            break
        except psycopg.OperationalError as exc:
            if attempt == 9:
                print(f"FALHA: PostgreSQL indisponível: {exc}")
                return 1
            time.sleep(2)
    print("init_db: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
