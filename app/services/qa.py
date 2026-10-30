"""Fachada do grafo: a API usa só estas duas funções."""
import logging
import time

from app.agents.common import Deps
from app.core.config import get_settings
from app.db.connection import connect
from app.graph.build import build_graph
from app.rag.embeddings import Embedder
from app.rag.llm import make_llm
from app.rag.retriever import retrieve
from app.repositories import documents as doc_repo
from app.services import cache

log = logging.getLogger(__name__)


def default_deps() -> Deps:
    s = get_settings()
    emb = Embedder(s)
    return Deps(s, lambda doc, q: retrieve(doc, q, s, emb), make_llm(s), emb)


def answer_question(document_id: str, question: str, mode: str = "auto", deps: Deps | None = None) -> dict:
    t0 = time.time()
    state = build_graph(deps or default_deps()).invoke(
        {"document_id": str(document_id), "request_type": "question", "question": question, "mode": mode, "trace": []})
    log.info("pergunta intent=%s trace=%s max_similarity=%.3f attempts=%s status=%s %.1fs",
             state.get("intent"), state["trace"], state.get("max_similarity", 0.0), state.get("attempts"),
             state.get("status"), time.time() - t0)
    return state


def get_or_create_summary(document_id: str, deps: Deps | None = None) -> dict:
    """Devolve o resumo do banco; só chama o LLM na primeira vez (CPU: minutos)."""
    with connect() as conn:
        cached = doc_repo.get_document(conn, document_id).summary
        if cached:
            return {"status": "answered", "summary": cached, "cached": True, "trace": []}
    state = build_graph(deps or default_deps()).invoke(
        {"document_id": str(document_id), "request_type": "summary", "mode": "auto", "trace": []})
    if state.get("status") == "answered":
        with connect() as conn:
            doc_repo.save_summary(conn, document_id, state["summary"])
    state["cached"] = False
    return state


def to_response(state: dict) -> dict:
    """Estado do grafo -> corpo da resposta da API (também é o que vai para o cache)."""
    nearest = []
    if state.get("status") == "insufficient":
        nearest = [{"page_number": e.page_number, "excerpt": e.content[:300], "similarity": e.similarity}
                   for e in state.get("nearest", [])]
    return {**{k: state.get(k) for k in ("status", "intent", "answer", "article_part", "simple_explanation",
                                         "message")},
            "citations": state.get("citations", []), "nearest_excerpts": nearest, "trace": state["trace"]}


def answer_cached(document_id: str, question: str, mode: str = "auto", deps: Deps | None = None) -> dict:
    """Consulta o cache; no MISS (ou sem Redis) roda o grafo completo e grava a resposta."""
    key = cache.make_key(str(document_id), mode, question)
    cache_status, hit = cache.get(key, str(document_id))
    if hit is not None:
        return {**hit, "cached": True, "cache_status": "hit"}
    state = answer_question(document_id, question, mode, deps)
    if state.get("status") == "error":
        return state
    response = to_response(state)
    if cache_status in ("miss", "unavailable"):
        cache.set(key, response)  # com Redis fora, a falha de gravação também é ignorada
    return {**response, "cached": False, "cache_status": cache_status}
