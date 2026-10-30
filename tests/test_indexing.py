import pytest

from app.core.config import Settings
from app.rag.embeddings import Embedder
from app.rag.retriever import add_next_chunks, apply_threshold
from app.repositories.chunks import Evidence
from scripts.calibrate_threshold import suggest


class FakeBackend:
    def __init__(self):
        self.docs, self.queries = [], []

    def embed_documents(self, texts):
        self.docs.append(texts)
        return [[0.0] * 3 for _ in texts]

    def embed_query(self, text):
        self.queries.append(text)
        return [0.0] * 3


def ev(sim):
    return Evidence(1, 1, 0, "x", sim)


def test_prefixos():
    b = FakeBackend()
    e = Embedder(Settings(), backend=b)
    e.embed_documents(["a"])
    e.embed_query("q")
    assert b.docs[0][0].startswith("search_document: ")
    assert b.queries[0].startswith("search_query: ")


def test_lotes_de_16():
    b = FakeBackend()
    Embedder(Settings(), backend=b).embed_documents(["t"] * 40)
    assert len(b.docs) == 3


def test_consulta_vazia():
    with pytest.raises(ValueError):
        Embedder(Settings(), backend=FakeBackend()).embed_query("   ")


def test_limiar():
    r = apply_threshold([ev(0.70), ev(0.52), ev(0.40)], 0.55)
    assert r.relevant and len(r.evidence) == 1 and r.max_similarity == 0.70
    r = apply_threshold([ev(0.50), ev(0.40)], 0.55)
    assert not r.relevant and r.evidence == []


def test_sugestao_de_limiar():
    assert suggest([0.7, 0.8], [0.3, 0.4]) == pytest.approx(0.55)
    assert suggest([], [0.3]) is None


# Expansão por vizinho: o chunk seguinte completa um trecho relevante cortado pelo chunking.

def evi(idx, sim=0.0, cid=None):
    return Evidence(cid or 1000 + idx, 9, idx, f"chunk {idx}", sim)


class Fetch:
    """Repositório falso: devolve os chunks pedidos e anota cada pedido."""
    def __init__(self, existing):
        self.existing, self.calls = {e.chunk_index: e for e in existing}, []

    def __call__(self, indices):
        self.calls.append(list(indices))
        return [self.existing[i] for i in indices if i in self.existing]


def test_vizinho_entra_logo_depois_do_trecho_relevante():
    fetch = Fetch([evi(50, 0.741, cid=82)])  # reproduz o caso 81 -> 82 do artigo
    out = add_next_chunks([evi(23, 0.838, cid=55), evi(49, 0.836, cid=81)], fetch)
    assert [e.chunk_id for e in out] == [55, 81, 82]
    assert fetch.calls == [[24, 50]]


def test_vizinho_ja_presente_nao_se_repete():
    fetch = Fetch([evi(48)])
    out = add_next_chunks([evi(46), evi(47)], fetch)  # 47 é vizinho de 46 e já está na lista
    assert [e.chunk_index for e in out] == [46, 47, 48]
    assert fetch.calls == [[48]]


def test_ultimo_chunk_sem_vizinho_e_lista_vazia():
    assert [e.chunk_index for e in add_next_chunks([evi(209)], Fetch([]))] == [209]
    fetch = Fetch([evi(1)])
    assert add_next_chunks([], fetch) == [] and fetch.calls == []


def test_vizinho_mantem_a_propria_similaridade():
    out = add_next_chunks([evi(49, 0.836)], Fetch([evi(50, 0.741)]))
    assert [e.similarity for e in out] == [0.836, 0.741]  # não copia a similaridade do trecho de origem


def test_retrieve_expande_sem_mudar_relevancia(monkeypatch):
    from app.rag import retriever as r
    found = [evi(23, 0.84, 55), evi(49, 0.83, 81), evi(10, 0.40, 30)]
    monkeypatch.setattr(r.doc_repo, "get_document", lambda conn, d: type("D", (), {"status": "ready"})())
    monkeypatch.setattr(r.chunk_repo, "search", lambda conn, d, v, k: found)
    monkeypatch.setattr(r.chunk_repo, "by_indices",
                        lambda conn, d, idx, v: [e for e in [evi(24, 0.5, 56), evi(50, 0.74, 82)] if e.chunk_index in idx])

    class Emb:
        def embed_query(self, q):
            return [0.0]

    res = r.retrieve("d", "pergunta", Settings(relevance_threshold=0.55), Emb(), conn=object())
    assert [e.chunk_id for e in res.evidence] == [55, 56, 81, 82]  # o chunk 30 continua barrado pelo limiar
    assert res.relevant and res.max_similarity == 0.84
    assert [e.chunk_id for e in res.candidates] == [55, 81, 30]  # candidatos são os do top-k original


def test_retrieve_sem_evidencia_relevante_nao_busca_vizinhos(monkeypatch):
    from app.rag import retriever as r
    monkeypatch.setattr(r.doc_repo, "get_document", lambda conn, d: type("D", (), {"status": "ready"})())
    monkeypatch.setattr(r.chunk_repo, "search", lambda conn, d, v, k: [evi(10, 0.40)])
    called = []
    monkeypatch.setattr(r.chunk_repo, "by_indices", lambda *a: called.append(a) or [])

    class Emb:
        def embed_query(self, q):
            return [0.0]

    res = r.retrieve("d", "q", Settings(relevance_threshold=0.55), Emb(), conn=object())
    assert not res.relevant and res.evidence == [] and called == []  # interrupção segura intacta
