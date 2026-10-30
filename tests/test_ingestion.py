import pytest

from app.core.config import Settings
from app.core.errors import (FileTooLargeError, InvalidPdfError, NoExtractableTextError,
                             TooManyPagesError)
from app.ingestion import ingest_pdf
from app.ingestion.extract import normalize
from tests.pdfgen import make_pdf

S = Settings()
FILLER = " palavra" * 40  # >200 caracteres no total


def pdf(pages):
    return make_pdf(pages)


def test_extensao_e_assinatura():
    with pytest.raises(InvalidPdfError):
        ingest_pdf(b"%PDF-1.4 x", "a.txt", S)
    with pytest.raises(InvalidPdfError):
        ingest_pdf(b"texto puro", "a.pdf", S)


def test_arquivo_grande():
    with pytest.raises(FileTooLargeError):
        ingest_pdf(b"%PDF-" + b"0" * (20 * 1024 * 1024), "a.pdf", S)


def test_paginas_demais():
    with pytest.raises(TooManyPagesError) as e:
        ingest_pdf(pdf(["x"] * 61), "a.pdf", S)
    assert "61" in str(e.value)


def test_corrompido():
    with pytest.raises(InvalidPdfError):
        ingest_pdf(b"%PDF-1.4 lixo sem estrutura", "a.pdf", S)


def test_paginas_numeradas_com_marcadores():
    r = ingest_pdf(pdf([f"PAGINA_UM{FILLER}", f"PAGINA_DOIS{FILLER}", f"PAGINA_TRES{FILLER}"]), "a.pdf", S)
    assert r.page_count == 3
    for c in r.chunks:
        marker = {1: "PAGINA_UM", 2: "PAGINA_DOIS", 3: "PAGINA_TRES"}[c.page_number]
        assert marker in c.content or "palavra" in c.content
        others = {"PAGINA_UM", "PAGINA_DOIS", "PAGINA_TRES"} - {marker}
        assert not any(o in c.content for o in others)
    assert {c.page_number for c in r.chunks} == {1, 2, 3}


def test_normalizacao():
    assert normalize("algo-\nritmo  de\nteste") == "algoritmo de teste"


def test_sem_texto():
    with pytest.raises(NoExtractableTextError) as e:
        ingest_pdf(pdf(["", ""]), "a.pdf", S)
    assert "digitalizado" in e.value.user_message


def test_pagina_vazia_ignorada():
    r = ingest_pdf(pdf([f"A{FILLER}", "", f"C{FILLER}"]), "a.pdf", S)
    assert {c.page_number for c in r.chunks} == {1, 3}


def test_tamanho_e_indices():
    long = "frase de teste longa. " * 200
    r = ingest_pdf(pdf([long, long]), "a.pdf", S)
    assert all(c.char_count <= 800 and c.char_count == len(c.content) for c in r.chunks)
    assert [c.chunk_index for c in r.chunks] == list(range(len(r.chunks)))
    assert len(r.chunks) > 2
