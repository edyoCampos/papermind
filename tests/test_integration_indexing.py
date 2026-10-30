"""Integração real (Postgres + Ollama). docker compose run --rm app pytest -m integration"""
import pytest

from app.core.config import get_settings
from app.core.errors import DocumentNotReadyError
from app.db.connection import connect
from app.db.schema import ensure_schema
from app.rag.embeddings import Embedder
from app.rag.retriever import retrieve
from app.repositories import chunks as chunk_repo
from app.repositories import documents as doc_repo
from app.services.indexing import index_document, register_document
from tests.pdfgen import make_pdf

pytestmark = pytest.mark.integration

TEXTO_A = "A mitocondria produz energia celular por meio da respiração aeróbica. " * 6
TEXTO_B = "O telescópio espacial observa galáxias distantes usando infravermelho. " * 6


@pytest.fixture(scope="module", autouse=True)
def schema():
    with connect() as conn:
        ensure_schema(conn)


def _index(pages, filename="t.pdf"):
    doc_id = register_document(filename)
    index_document(doc_id, make_pdf(pages), filename)
    return doc_id


def test_indexa_e_recupera_pagina_certa():
    doc = _index([TEXTO_A, TEXTO_B])
    other = _index([TEXTO_B])
    r = retrieve(doc, "Como a célula produz energia?")
    assert r.evidence and all(e.page_number >= 1 for e in r.evidence)
    top = chunk_repo.search(connect(), doc, Embedder().embed_query("telescópio e galáxias"), 5)
    assert top[0].page_number == 2
    assert top == sorted(top, key=lambda e: -e.similarity)
    with connect() as conn:  # nenhum chunk do outro documento aparece
        ids = {e.chunk_id for e in chunk_repo.search(conn, doc, Embedder().embed_query("galáxias"), 10)}
        other_ids = {e.chunk_id for e in chunk_repo.chunks_by_page(conn, other)}
    assert not ids & other_ids


def test_status_ready_e_nao_pronto():
    doc = _index([TEXTO_A])
    with connect() as conn:
        d = doc_repo.get_document(conn, doc)
        assert d.status == "ready" and d.page_count == 1
        doc_repo.set_status(conn, doc, "indexing")
    with pytest.raises(DocumentNotReadyError):
        retrieve(doc, "qualquer")


def test_falha_no_embedding_nao_grava_nada():
    class Quebrado:
        def embed_documents(self, texts):
            raise RuntimeError("falha simulada")

    doc_id = register_document("x.pdf")
    with pytest.raises(RuntimeError):
        index_document(doc_id, make_pdf([TEXTO_A]), "x.pdf", embedder=Quebrado())
    with connect() as conn:
        assert chunk_repo.count_chunks(conn, doc_id) == 0
        assert doc_repo.get_document(conn, doc_id).status == "error"
