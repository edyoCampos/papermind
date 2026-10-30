"""Contra o app real em execução no Compose (rede interna). Usa o LLM real só no /health e no status."""
import time

import httpx
import pytest

from tests.pdfgen import make_pdf

pytestmark = pytest.mark.integration
BASE = "http://app:8000"
TEXTO = "A mitocôndria produz energia celular por respiração aeróbica. " * 8


def test_health_real():
    j = httpx.get(f"{BASE}/health", timeout=10).json()
    assert j["dependencies"]["database"] == "ok" and j["dependencies"]["ollama"] == "ok"


def test_upload_ate_ready_e_erros_reais():
    r = httpx.post(f"{BASE}/documents", files={"file": ("t.pdf", make_pdf([TEXTO]), "application/pdf")})
    assert r.status_code == 202
    doc = r.json()["document_id"]
    for _ in range(60):
        s = httpx.get(f"{BASE}/documents/{doc}").json()
        if s["status"] in ("ready", "error"):
            break
        time.sleep(1)
    assert s["status"] == "ready" and s["chunk_count"] > 0 and s["page_count"] == 1
    sem_texto = httpx.post(f"{BASE}/documents", files={"file": ("v.pdf", make_pdf(["", ""]), "application/pdf")}).json()
    for _ in range(30):
        e = httpx.get(f"{BASE}/documents/{sem_texto['document_id']}").json()
        if e["status"] in ("ready", "error"):
            break
        time.sleep(1)
    assert e["status"] == "error" and "digitalizado" in e["error_message"]
