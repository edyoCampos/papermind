import logging

from app.core.config import Settings, get_settings
from app.core.errors import IngestionError, ModelUnavailableError, PaperMindError
from app.db.connection import connect
from app.ingestion import ingest_pdf
from app.rag.embeddings import Embedder
from app.repositories import chunks as chunk_repo
from app.repositories import documents as doc_repo

log = logging.getLogger(__name__)


def register_document(filename: str):
    with connect() as conn:
        return doc_repo.create_document(conn, filename)


def index_document(document_id, data: bytes, filename: str, settings: Settings | None = None,
                   embedder: Embedder | None = None) -> None:
    """Ingestão + embeddings + gravação. Atualiza o status; em falha nada fica gravado."""
    s = settings or get_settings()
    embedder = embedder or Embedder(s)
    with connect() as conn:
        try:
            doc_repo.set_status(conn, document_id, "extracting")
            result = ingest_pdf(data, filename, s)
            doc_repo.set_status(conn, document_id, "indexing")
            vectors = embedder.embed_documents([c.content for c in result.chunks])
            chunk_repo.save_chunks(conn, document_id, result.chunks, vectors, filename)
            doc_repo.set_status(conn, document_id, "ready", page_count=result.page_count)
            log.info("indexado doc=%s chunks=%d", document_id, len(result.chunks))
        except (IngestionError, ModelUnavailableError, PaperMindError) as exc:
            doc_repo.set_status(conn, document_id, "error", exc.user_message)
            raise
        except Exception as exc:
            msg = f"Falha ao indexar o documento: {exc}"
            doc_repo.set_status(conn, document_id, "error", msg)
            raise
