import psycopg
from pgvector.psycopg import register_vector

from app.core.config import get_settings
from app.core.errors import DatabaseUnavailableError


def connect(autocommit: bool = True) -> psycopg.Connection:
    """Abre conexão com o vetor registrado. Falha com mensagem acionável."""
    try:
        conn = psycopg.connect(get_settings().database_url, autocommit=autocommit, connect_timeout=5)
    except psycopg.OperationalError as exc:
        raise DatabaseUnavailableError() from exc
    try:
        register_vector(conn)
    except Exception:  # extensão ainda não criada (init_db a cria antes de usar)
        pass
    return conn
