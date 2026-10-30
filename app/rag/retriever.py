import logging
from dataclasses import dataclass, field

from app.core.config import Settings, get_settings
from app.core.errors import DocumentNotReadyError
from app.db.connection import connect
from app.rag.embeddings import Embedder
from app.repositories import chunks as chunk_repo
from app.repositories import documents as doc_repo
from app.repositories.chunks import Evidence

log = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    relevant: bool
    evidence: list[Evidence] = field(default_factory=list)
    max_similarity: float = 0.0
    candidates: list[Evidence] = field(default_factory=list)  # top-k antes do limiar


def apply_threshold(found: list[Evidence], threshold: float) -> RetrievalResult:
    """Relevante se ao menos um chunk atinge o limiar; só os chunks acima dele seguem."""
    max_sim = max((e.similarity for e in found), default=0.0)
    kept = [e for e in found if e.similarity >= threshold]
    return RetrievalResult(bool(kept), kept, max_sim, list(found))


def add_next_chunks(kept: list[Evidence], fetch) -> list[Evidence]:
    """Coloca, logo depois de cada trecho relevante, o chunk seguinte do documento.
    O chunking corta o texto a cada CHUNK_SIZE caracteres, então um parágrafo pode continuar no próximo chunk.
    `fetch(indices)` devolve os chunks pedidos; os que já estão na lista não se repetem."""
    if not kept:
        return kept
    present = {e.chunk_index for e in kept}
    wanted = sorted({e.chunk_index + 1 for e in kept} - present)
    following = {e.chunk_index: e for e in fetch(wanted)} if wanted else {}
    out: list[Evidence] = []
    for e in kept:
        out.append(e)
        if e.chunk_index + 1 in following:
            out.append(following[e.chunk_index + 1])
    return out


def retrieve(document_id, query: str, settings: Settings | None = None, embedder: Embedder | None = None,
             conn=None) -> RetrievalResult:
    s = settings or get_settings()
    own = conn is None
    conn = conn or connect()
    try:
        doc = doc_repo.get_document(conn, document_id)
        if doc.status != "ready":
            raise DocumentNotReadyError(f"O documento ainda não está pronto (status: {doc.status}).")
        vec = (embedder or Embedder(s)).embed_query(query)
        found = chunk_repo.search(conn, document_id, vec, s.top_k)
        # relevância, máximo e candidatos são decididos antes; os vizinhos só completam o contexto
        result = apply_threshold(found, s.relevance_threshold)
        result.evidence = add_next_chunks(
            result.evidence, lambda idx: chunk_repo.by_indices(conn, document_id, idx, vec))
    finally:
        if own:
            conn.close()
    log.info("retrieve doc=%s max_similarity=%.3f relevant=%s", document_id, result.max_similarity, result.relevant)
    return result
