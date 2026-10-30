"""Resumo persistido: 2ª chamada não aciona o LLM (banco real, LLM falso)."""
import pytest

from app.agents.common import Deps
from app.core.config import get_settings
from app.rag.embeddings import Embedder
from app.rag.retriever import retrieve
from app.services.indexing import index_document, register_document
from app.services.qa import get_or_create_summary
from tests.pdfgen import make_pdf
from tests.test_graph import FakeLLM

pytestmark = pytest.mark.integration


def test_resumo_gravado_e_reaproveitado():
    texto = "O objetivo do estudo é medir a energia celular na mitocôndria humana. " * 6
    doc = register_document("r.pdf")
    index_document(doc, make_pdf([texto]), "r.pdf")
    s, emb = get_settings(), Embedder()
    llm = FakeLLM("A mitocôndria produz energia [1].")
    d = Deps(s.model_copy(update={"relevance_threshold": 0.0}), lambda dd, q: retrieve(dd, q, s.model_copy(update={"relevance_threshold": 0.0}), emb), llm, emb)
    first = get_or_create_summary(str(doc), d)
    n = len(llm.calls)
    second = get_or_create_summary(str(doc), d)
    assert first["cached"] is False and second["cached"] is True
    assert len(llm.calls) == n and n == 5
