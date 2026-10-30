import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Services, get_services
from app.api.main import app
from app.core.errors import (DatabaseUnavailableError, DocumentNotFoundError)
from app.repositories.documents import Document
from tests.pdfgen import make_pdf

ID = uuid.uuid4()
TEXTO = "O modelo atingiu acurácia de 92 por cento. " * 10


class Fake:
    def __init__(self):
        self.status = "ready"
        self.indexed = []
        self.error_message = None
        self.state = {"status": "answered", "intent": "factual", "answer": "ok [1]", "message": None,
                      "citations": [{"ref": 1, "page_number": 3, "chunk_id": 1, "excerpt": "x", "similarity": 0.8}],
                      "trace": ["router", "researcher", "reader", "verifier", "finalize"],
                      "cached": False, "cache_status": "disabled"}
        self.summary = {k: {"status": "found", "text": "t", "citations": []}
                        for k in ["objetivo", "metodologia", "resultados", "limitações", "contribuição"]}
        self.summary["limitações"] = {"status": "not_found", "text": "Não encontrado no artigo.", "citations": []}

    def services(self):
        def get_document(i):
            if str(i) != str(ID):
                raise DocumentNotFoundError()
            return Document(ID, "a.pdf", self.status, self.error_message, None if self.status != "ready" else 3, None)
        return Services(lambda f: ID, lambda *a: self.indexed.append(a), get_document, lambda i: 7,
                        lambda *a: self.state, lambda i: {"status": "answered", "summary": self.summary},
                        lambda: {"status": "ok", "dependencies": {"database": "ok", "ollama": "unavailable",
                                                                  "cache": {"status": "disabled", "hits": 0, "misses": 0}}})


@pytest.fixture
def fake():
    f = Fake()
    app.dependency_overrides[get_services] = f.services
    yield f
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_health(fake, client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["dependencies"]["ollama"] == "unavailable"


def test_upload_valido_agenda_indexacao(fake, client):
    r = client.post("/documents", files={"file": ("a.pdf", make_pdf([TEXTO]), "application/pdf")})
    assert r.status_code == 202
    assert r.json() == {"document_id": str(ID), "filename": "a.pdf", "status": "received"}
    assert len(fake.indexed) == 1  # BackgroundTasks roda ao fim da requisição


def test_upload_erros(fake, client):
    r = client.post("/documents", files={"file": ("a.txt", b"texto", "text/plain")})
    assert r.status_code == 400 and "PDF" in r.json()["detail"]
    r = client.post("/documents", files={"file": ("a.pdf", b"%PDF-" + b"0" * (21 * 1024 * 1024), "application/pdf")})
    assert r.status_code == 413
    r = client.post("/documents")
    assert r.status_code == 422 and "campo 'file'" in r.json()["detail"]


def test_status_do_documento(fake, client):
    r = client.get(f"/documents/{ID}")
    assert r.status_code == 200
    assert set(r.json()) == {"document_id", "filename", "status", "page_count", "chunk_count", "error_message"}
    fake.status = "indexing"
    assert client.get(f"/documents/{ID}").json()["page_count"] is None


def test_documento_inexistente_e_uuid_invalido(fake, client):
    assert client.get(f"/documents/{uuid.uuid4()}").status_code == 404
    r = client.get("/documents/nao-e-uuid")
    assert r.status_code == 404 and r.json()["detail"] == "Documento não encontrado."


def test_resumo_cinco_secoes(fake, client):
    r = client.get(f"/documents/{ID}/summary")
    secs = r.json()["sections"]
    assert set(secs) == {"objective", "methodology", "results", "limitations", "contribution"}
    assert secs["limitations"]["status"] == "not_found" and secs["limitations"]["citations"] == []


def test_pergunta_respondida(fake, client):
    r = client.post(f"/documents/{ID}/questions", json={"question": "  Qual a acurácia? "})
    j = r.json()
    assert r.status_code == 200 and j["status"] == "answered" and j["citations"][0]["page_number"] == 3
    assert j["trace"] and j["cache_status"] == "disabled" and j["cached"] is False


def test_pergunta_insuficiente(fake, client):
    fake.state = {"status": "insufficient", "intent": "factual", "message": "O artigo não traz...",
                  "citations": [], "trace": ["router", "researcher", "insufficient"]}
    j = client.post(f"/documents/{ID}/questions", json={"question": "x"}).json()
    assert j["status"] == "insufficient" and j["citations"] == [] and j["message"]


def test_pergunta_invalida(fake, client):
    for q in ("   ", "a" * 1001):
        r = client.post(f"/documents/{ID}/questions", json={"question": q})
        assert r.status_code == 422 and "entre 1 e 1000" in r.json()["detail"]


def test_documento_nao_pronto_e_com_erro(fake, client):
    fake.status = "indexing"
    r = client.post(f"/documents/{ID}/questions", json={"question": "x"})
    assert r.status_code == 409 and "indexing" in r.json()["detail"]
    fake.status, fake.error_message = "error", "Não foi possível extrair texto deste PDF."
    assert client.get(f"/documents/{ID}/summary").json()["detail"] == fake.error_message


def test_ollama_fora_vira_503(fake, client):
    fake.state = {"status": "error", "error_message": "Modelo local indisponível. Verifique o serviço ollama com 'docker compose ps'.",
                  "trace": ["reader"]}
    r = client.post(f"/documents/{ID}/questions", json={"question": "x"})
    assert r.status_code == 503 and "docker compose ps" in r.json()["detail"]


def test_banco_fora_vira_503(fake, client):
    def boom(i):
        raise DatabaseUnavailableError()
    s = fake.services()
    s.get_document = boom
    app.dependency_overrides[get_services] = lambda: s
    assert client.get(f"/documents/{ID}").status_code == 503


def test_erro_inesperado_vira_500_sem_stack(fake, client):
    def boom(i):
        raise RuntimeError("segredo interno")
    s = fake.services()
    s.get_document = boom
    app.dependency_overrides[get_services] = lambda: s
    r = client.get(f"/documents/{ID}")
    assert r.status_code == 500 and r.json() == {"detail": "Erro interno. Veja o log da API."}
