from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import api_client as api
import view

APP = str(Path(__file__).resolve().parents[2] / "frontend" / "app.py")


def transport(handler):
    return httpx.MockTransport(handler)


def test_rotulos_e_selos():
    assert [view.status_label(s) for s in ("received", "extracting", "indexing", "ready", "error")] == [
        "Recebido", "Extraindo texto", "Indexando", "Pronto", "Erro"]
    assert view.cache_badge("hit") == "HIT" and view.cache_badge("unavailable") == "cache indisponível"
    assert view.MODES["Explicar termo"] == "explanation"


def test_fontes_e_trace():
    lines = view.source_lines([{"ref": 1, "page_number": 3, "excerpt": "trecho"}])
    assert lines == ['[1] Página 3 — "trecho…"']
    assert view.trace_text(["router", "researcher"]) == "router → researcher"


def test_cliente_ok_e_modo_enviado():
    seen = {}

    def handler(req):
        seen["body"] = req.read()
        return httpx.Response(200, json={"status": "answered"})

    api.ask("http://x", "id", "q?", "explanation", transport=transport(handler))
    assert b'"mode":"explanation"' in seen["body"].replace(b" ", b"")


def test_cliente_erros():
    with pytest.raises(api.ApiError, match="demorou demais"):
        api.get_status("http://x", "id", transport=transport(lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("t"))))
    with pytest.raises(api.ApiError, match="Não foi possível conectar à API em http://x. Ela está rodando?"):
        api.get_status("http://x", "id", transport=transport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("c"))))
    with pytest.raises(api.ApiError, match="Documento não encontrado."):
        api.get_status("http://x", "id", transport=transport(lambda r: httpx.Response(404, json={"detail": "Documento não encontrado."})))


def ready_app(monkeypatch, ask_payload, summary=None):
    monkeypatch.setattr(api, "get_status", lambda *a, **k: {"status": "ready", "error_message": None, "page_count": 3})
    monkeypatch.setattr(api, "ask", lambda *a, **k: dict(ask_payload))
    if summary:
        monkeypatch.setattr(api, "get_summary", lambda *a, **k: {"sections": summary})
    at = AppTest.from_file(APP, default_timeout=10)
    at.session_state["document_id"] = "abc"
    at.session_state["doc_status"] = "ready"
    at.session_state["page_count"] = 3
    return at.run()


BASE = {"trace": ["router", "researcher", "reader", "verifier", "finalize"], "cache_status": "miss",
        "citations": [], "nearest_excerpts": []}


def test_pergunta_com_fontes(monkeypatch):
    at = ready_app(monkeypatch, {**BASE, "status": "answered", "intent": "factual", "answer": "Foi 92% [1].",
                                 "citations": [{"ref": 1, "page_number": 3, "chunk_id": 1, "excerpt": "acurácia 92", "similarity": 0.8}]})
    at.chat_input[0].set_value("Qual a acurácia?").run()
    texts = " ".join(m.value for m in at.markdown)
    assert "Foi 92% [1]." in texts and "Página 3" in texts
    assert any("MISS" in c.value for c in at.caption)


def test_insuficiente_sem_fontes(monkeypatch):
    at = ready_app(monkeypatch, {**BASE, "status": "insufficient", "intent": "factual",
                                 "message": "O artigo não traz evidência suficiente para responder a essa pergunta.",
                                 "nearest_excerpts": [{"page_number": 2, "excerpt": "algo", "similarity": 0.4}]})
    at.chat_input[0].set_value("Pergunta fora").run()
    assert len(at.warning) == 1
    assert not any("Fontes" in m.value for m in at.markdown)


def test_explicacao_dois_blocos(monkeypatch):
    at = ready_app(monkeypatch, {**BASE, "status": "answered", "intent": "explanation", "article_part": "O artigo diz X [1].",
                                 "simple_explanation": "Em palavras simples, Y.",
                                 "citations": [{"ref": 1, "page_number": 1, "chunk_id": 1, "excerpt": "t", "similarity": 0.7}]})
    at.radio[0].set_value("Explicar termo")
    at.chat_input[0].set_value("O que é X?").run()
    assert any("No artigo" in m.value for m in at.markdown)
    assert any("gerada pelo modelo" in i.value for i in at.info)


def test_resumo_com_secao_nao_encontrada(monkeypatch):
    sec = {k: {"status": "found", "text": f"texto {k}", "citations": []} for k in view.SECTION_TITLES}
    sec["limitations"] = {"status": "not_found", "text": "Não encontrado no artigo.", "citations": []}
    at = ready_app(monkeypatch, BASE, summary=sec)
    at.button[0].click().run()
    texts = " ".join(m.value for m in at.markdown)
    assert texts.count("texto ") == 4 and "Não encontrado no artigo" in texts


def test_api_fora_do_ar(monkeypatch):
    def boom(*a, **k):
        raise api.ApiError("Não foi possível conectar à API em http://app:8000. Ela está rodando?")
    monkeypatch.setattr(api, "ask", boom)
    monkeypatch.setattr(api, "get_status", lambda *a, **k: {"status": "ready", "error_message": None, "page_count": 1})
    at = AppTest.from_file(APP, default_timeout=10)
    at.session_state["document_id"], at.session_state["doc_status"] = "abc", "ready"
    at.run()
    at.chat_input[0].set_value("oi").run()
    assert "Não foi possível conectar à API" in at.error[0].value
