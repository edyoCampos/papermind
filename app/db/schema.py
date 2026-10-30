from app.core.config import get_settings

_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
  id uuid PRIMARY KEY,
  filename text NOT NULL,
  status text NOT NULL CHECK (status IN ('received','extracting','indexing','ready','error')),
  error_message text,
  page_count int,
  summary jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
)"""

_CHUNKS = """
CREATE TABLE IF NOT EXISTS document_chunks (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index int NOT NULL,
  page_number int NOT NULL CHECK (page_number >= 1),
  content text NOT NULL,
  embedding vector({dim}) NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{{}}',
  UNIQUE (document_id, chunk_index)
)"""


def ensure_schema(conn) -> None:
    """Cria o esquema se não existir (idempotente)."""
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute(_DOCUMENTS)
    conn.execute(_CHUNKS.format(dim=int(get_settings().embedding_dim)))
    conn.execute("CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx ON document_chunks(document_id)")
