import copy
import hashlib
import logging
import math

import pytest

from app.agents.common import Deps
from app.agents.reader import parse_explanation
from app.agents.router import classify
from app.agents.verifier import _cos, _RecordingEmbedder, check, describe, make_verifier, similarity_diagnostics
from app.core.config import Settings
from app.graph.build import build_graph
from app.rag.retriever import RetrievalResult
from app.repositories.chunks import Evidence

CH = [
    Evidence(1, 3, 0, "O modelo atingiu acurácia de 92 por cento no conjunto de teste.", 0.8),
    Evidence(2, 5, 1, "Os dados vieram de 1200 imagens médicas anotadas.", 0.7),
]


class FakeEmb:
    """Bag-of-words em hash: frases com as mesmas palavras ficam próximas."""
    def _v(self, text):
        v = [0.0] * 64
        for w in text.lower().replace(".", "").split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
        return v

    def embed_query(self, t):
        return self._v(t)

    def embed_documents(self, ts):
        return [self._v(t) for t in ts]


class FakeLLM:
    def __init__(self, *answers, error=None):
        self.answers, self.calls, self.error = list(answers), [], error

    def __call__(self, prompt):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


def deps(llm, relevant=True, evidence=CH, settings=None):
    s = settings or Settings(grounding_threshold=0.3)
    r = RetrievalResult(relevant, list(evidence) if relevant else [], 0.8 if relevant else 0.2, list(evidence))
    return Deps(s, lambda d, q: r, llm, FakeEmb())


def run(llm, question="Qual foi a acurácia?", mode="auto", request_type="question", **kw):
    return build_graph(deps(llm, **kw)).invoke(
        {"document_id": "d", "request_type": request_type, "question": question, "mode": mode, "trace": []})


GOOD = "O modelo atingiu acurácia de 92 por cento no conjunto de teste [1]."


@pytest.mark.parametrize("req,mode,q,expected", [
    ("question", "auto", "O que é overfitting?", "explanation"),
    ("question", "auto", "O que eles fizeram?", "factual"),
    ("question", "auto", "Qual foi a acurácia?", "factual"),
    ("question", "factual", "O que é X?", "factual"),
    ("question", "explanation", "Qual a acurácia?", "explanation"),
    ("summary", "auto", None, "summary"),
])
def test_router(req, mode, q, expected):
    assert classify(req, mode, q) == expected


def test_caminho_respondido():
    llm = FakeLLM(GOOD)
    st = run(llm)
    assert st["trace"] == ["router", "researcher", "reader", "verifier", "finalize"]
    assert st["status"] == "answered"
    assert st["citations"][0]["page_number"] == 3 and st["citations"][0]["chunk_id"] == 1


def test_interrupcao_segura_sem_llm():
    llm = FakeLLM(GOOD)
    st = run(llm, relevant=False)
    assert st["trace"] == ["router", "researcher", "insufficient"]
    assert st["status"] == "insufficient" and llm.calls == []


def test_reformula_uma_vez_e_aprova():
    llm = FakeLLM("A acurácia foi 92 por cento [7].", GOOD)
    st = run(llm)
    assert st["trace"] == ["router", "researcher", "reader", "verifier", "reader", "verifier", "finalize"]
    assert len(llm.calls) == 2 and "V3" in llm.calls[1] and st["status"] == "answered"


def test_reprovacao_dupla_termina_em_insuficiente():
    llm = FakeLLM("Acurácia [7].")
    st = run(llm)
    assert st["trace"] == ["router", "researcher", "reader", "verifier", "reader", "verifier", "insufficient"]
    assert len(llm.calls) == 2 and st["status"] == "insufficient" and st["citations"] == []


def test_sem_evidencia_declarada_nao_reformula():
    llm = FakeLLM("SEM_EVIDENCIA")
    st = run(llm)
    assert st["trace"][-2:] == ["verifier", "insufficient"] and len(llm.calls) == 1


def test_explicacao_dois_blocos_e_mensagem_propria():
    llm = FakeLLM("NO ARTIGO: O modelo atingiu acurácia de 92 por cento no conjunto de teste [1].\n"
                  "EM TERMOS SIMPLES: acurácia é a fração de acertos.")
    st = run(llm, question="O que é acurácia?")
    assert st["intent"] == "explanation" and st["status"] == "answered"
    assert st["article_part"].startswith("O modelo") and st["simple_explanation"].startswith("acurácia")
    ins = run(FakeLLM("x"), question="O que é acurácia?", relevant=False)
    fac = run(FakeLLM("x"), relevant=False)
    assert ins["message"] != fac["message"]


def test_explicacao_sem_rotulo_reprova_v2():
    assert parse_explanation("sem rótulos") == (None, None)
    v = check("texto [1]", None, "explanation", CH, FakeEmb(), 0.3)
    assert not v["passed"] and v["problems"][0].startswith("V2")


def test_verificador_cada_checagem():
    e, g = FakeEmb(), 0.3
    assert check("SEM_EVIDENCIA", None, "factual", CH, e, g)["problems"][0].startswith("V1")
    assert check("sem marcador", None, "factual", CH, e, g)["problems"][0].startswith("V2")
    assert check("acurácia [9].", None, "factual", CH, e, g)["problems"][0].startswith("V3")
    v4a = check("O modelo atingiu acurácia de 97 por cento no conjunto de teste [1].", None, "factual", CH, e, g)
    assert v4a["problems"][0].startswith("V4a")
    v4b = check("Gatos dormem muito durante o dia [1].", None, "factual", CH, e, 0.5)
    assert v4b["problems"][0].startswith("V4b")
    assert check(GOOD, None, "factual", CH, e, 0.5)["passed"]


def test_falha_do_ollama_vira_status_error():
    st = run(FakeLLM(error=ConnectionError("down")))
    assert st["status"] == "error" and "docker compose ps" in st["error_message"]
    assert st["trace"][-1] == "reader"


def test_resumo_cinco_secoes_uma_nao_encontrada():
    calls = {"n": 0}

    def retrieve(doc, q):
        calls["n"] += 1
        ok = "limitações" not in q
        return RetrievalResult(ok, list(CH) if ok else [], 0.8, list(CH))

    d = Deps(Settings(), retrieve, FakeLLM(GOOD), FakeEmb())
    st = build_graph(d).invoke({"document_id": "d", "request_type": "summary", "mode": "auto", "trace": []})
    assert st["trace"] == ["router", "summarizer"]
    s = st["summary"]
    assert s["limitações"]["status"] == "not_found"
    assert [k for k, v in s.items() if v["status"] == "found"] == ["objetivo", "metodologia", "resultados", "contribuição"]
    assert s["objetivo"]["citations"][0]["page_number"] == 3


def test_citacoes_so_dos_chunks():
    st = run(FakeLLM("O modelo atingiu acurácia de 92 por cento no conjunto de teste [1] [2]."))
    # [2] está fora do que a frase sustenta, mas existe: citação vem do chunk 2, página 5
    assert {c["ref"]: c["page_number"] for c in st["citations"]} == {1: 3, 2: 5}


# Observabilidade do verificador: só metadados no log, sem mudar o resultado.

def _describe(draft, article_part=None, intent="factual", grounding=0.0):
    return describe(draft, article_part, intent, CH, check(draft, article_part, intent, CH, FakeEmb(), grounding))


@pytest.mark.parametrize("draft,article_part,intent,markers", [
    ("Os autores citam limitações sem marcador.", None, "factual", "ausente"),
    ("A acurácia foi alta [1, 2].", None, "factual", "malformado"),
    ("A acurácia foi alta [ 1 ].", None, "factual", "malformado"),
    ("A acurácia foi alta [9].", None, "factual", "fora_do_intervalo"),
    (GOOD, None, "factual", "ok"),
    ("sem rótulos", None, "explanation", "sem_bloco_no_artigo"),
])
def test_describe_estado_dos_marcadores(draft, article_part, intent, markers):
    assert _describe(draft, article_part, intent)["markers"] == markers


def test_describe_etapa_e_codigos():
    assert _describe("SEM_EVIDENCIA")["stage"] == "V1"
    d = _describe("O modelo atingiu 97 por cento [1]. Outra coisa [9].")
    assert d["stage"] == "V4a" and d["codes"] == ["V4a", "V3"] and d["invalid"] == [9] and d["valid"] == 1
    assert d["sentences_marked"] == 2 and d["sentences"] == 2 and d["evidence"] == 2
    assert _describe("Gatos dormem muito durante o dia [1].", grounding=0.5)["codes"] == ["V4b"]
    ok = _describe(GOOD, grounding=0.5)
    assert ok["result"] == "APROVADA" and ok["stage"] == "-" and ok["codes"] == []


def test_describe_e_pura_e_nao_muda_o_resultado():
    v = check("A acurácia foi alta [1, 2].", None, "factual", CH, FakeEmb(), 0.3)
    before = copy.deepcopy(v)
    d = describe("A acurácia foi alta [1, 2].", None, "factual", CH, v)
    assert v == before and d["markers"] == "malformado"
    # malformado é só diagnóstico: a reprovação continua sendo a V2 de sempre
    assert v["problems"] == ["V2: a resposta não tem nenhum marcador [n]."]


def test_log_do_caso_teste2_sem_marcadores(caplog):
    caplog.set_level(logging.INFO, logger="app.agents.verifier")
    draft = "Os autores identificam limitações sem citar a fonte."
    llm = FakeLLM(draft)
    st = run(llm, question="What limitations do the authors identify?")
    assert st["trace"] == ["router", "researcher", "reader", "verifier", "reader", "verifier", "insufficient"]
    assert len(llm.calls) == 2
    lines = [r.getMessage() for r in caplog.records if r.name == "app.agents.verifier"]
    assert len(lines) == 2
    assert all("result=REPROVADA stage=V2 codes=V2 markers=ausente valid=0" in m for m in lines)
    assert "attempt=0" in lines[0] and "attempt=1" in lines[1] and "doc=d" in lines[0]


def test_log_aprovada_e_reformulacao(caplog):
    caplog.set_level(logging.INFO, logger="app.agents.verifier")
    st = run(FakeLLM("A acurácia foi 92 por cento [7].", GOOD))
    assert st["trace"] == ["router", "researcher", "reader", "verifier", "reader", "verifier", "finalize"]
    lines = [r.getMessage() for r in caplog.records if r.name == "app.agents.verifier"]
    assert "result=REPROVADA stage=V3" in lines[0] and "markers=fora_do_intervalo valid=0 invalid=[7]" in lines[0]
    assert "result=APROVADA stage=- codes=- markers=ok" in lines[1]


def test_log_nao_contem_texto_da_resposta_nem_dos_trechos(caplog):
    caplog.set_level(logging.INFO, logger="app.agents.verifier")
    run(FakeLLM("Gatos dormem muito durante o dia [1].", GOOD), settings=Settings(grounding_threshold=0.5))
    text = "\n".join(r.getMessage() for r in caplog.records if r.name == "app.agents.verifier")
    assert "Gatos" not in text and "acurácia" not in text and "imagens" not in text
    assert "stage=V4b" in text


# Observabilidade P1: similaridades reaproveitadas dos vetores que check() já pede, sem chamadas novas.

class SpyEmb(FakeEmb):
    """Anota método e argumentos de cada chamada, na ordem."""
    def __init__(self):
        self.seq = []

    def embed_query(self, t):
        self.seq.append(("query", t))
        return super().embed_query(t)

    def embed_documents(self, ts):
        self.seq.append(("documents", list(ts)))
        return super().embed_documents(ts)


G = 0.5
CASOS = {
    "aprovada": GOOD,
    "V2": "Resposta sem nenhuma citação.",
    "V3": "A acurácia foi alta [9].",
    "V4a": "O modelo atingiu acurácia de 97 por cento no conjunto de teste [1].",
    "V4b": "Gatos dormem muito durante o dia [1].",
}
DOIS = ("O modelo atingiu acurácia de 92 por cento no conjunto de teste [1]. "
        "Os dados vieram de 1200 imagens médicas anotadas [2].")


def _node_state(draft):
    return {"draft": draft, "article_part": None, "intent": "factual", "evidence": CH, "attempts": 0,
            "document_id": "d"}


@pytest.mark.parametrize("caso", list(CASOS))
def test_obs_retorno_de_check_identico_com_o_gravador(caso):
    draft = CASOS[caso]
    plain = check(draft, None, "factual", CH, FakeEmb(), G)
    recorded = check(draft, None, "factual", CH, _RecordingEmbedder(FakeEmb()), G)
    assert recorded == plain
    assert plain["passed"] if caso == "aprovada" else plain["problems"][0].startswith(caso)


@pytest.mark.parametrize("caso", list(CASOS) + ["duas_frases"])
def test_obs_mesmas_chamadas_ao_embedder_na_mesma_ordem(caso):
    draft = DOIS if caso == "duas_frases" else CASOS[caso]
    direto = SpyEmb()
    esperado = check(draft, None, "factual", CH, direto, G)
    pelo_no = SpyEmb()
    out = make_verifier(Deps(Settings(grounding_threshold=G), None, None, pelo_no))(_node_state(draft))
    assert pelo_no.seq == direto.seq  # mesmo número, ordem e argumentos
    assert out["verification"] == esperado


def test_obs_similaridade_registrada_e_a_da_v4b():
    rec = _RecordingEmbedder(FakeEmb())
    check(DOIS, None, "factual", CH, rec, G)
    got = similarity_diagnostics(rec.calls, DOIS, None, "factual", CH)["frase_vs_trecho"]
    e = FakeEmb()  # recalcula de forma independente, com a mesma conta da linha da V4b
    expected = [max(_cos(e.embed_query(s), cv) for cv in e.embed_documents([CH[i].content]))
                for s, i in [("O modelo atingiu acurácia de 92 por cento no conjunto de teste.", 0),
                             ("Os dados vieram de 1200 imagens médicas anotadas.", 1)]]
    assert got == expected
    for value, v4b in zip(got, [check(s, None, "factual", CH, FakeEmb(), G) for s in DOIS.split(". ")]):
        assert (value < G) == any(p.startswith("V4b") for p in v4b["problems"])  # coerente com a decisão


def test_obs_log_separa_frase_e_recuperacao(caplog):
    caplog.set_level(logging.INFO, logger="app.agents.verifier")
    make_verifier(Deps(Settings(grounding_threshold=G), None, None, FakeEmb()))(_node_state(DOIS))
    rec = _RecordingEmbedder(FakeEmb())
    check(DOIS, None, "factual", CH, rec, G)
    sent = similarity_diagnostics(rec.calls, DOIS, None, "factual", CH)["frase_vs_trecho"]
    line = next(r.getMessage() for r in caplog.records if r.name == "app.agents.verifier")
    assert f"frase_vs_trecho_citado=[{sent[0]:.3f},{sent[1]:.3f}] frase_vs_trecho_min={min(sent):.3f}" in line
    assert "recuperacao_pergunta_vs_citados=[0.800,0.700] recuperacao_pergunta_max=0.800" in line


@pytest.mark.parametrize("draft,grounding", [(CASOS["V2"], G), (GOOD, 0.0)], ids=["V2-sem-v4b", "limiar-zero"])
def test_obs_sem_calculo_da_v4b_nao_inventa_numero(caplog, draft, grounding):
    caplog.set_level(logging.INFO, logger="app.agents.verifier")
    make_verifier(Deps(Settings(grounding_threshold=grounding), None, None, FakeEmb()))(_node_state(draft))
    line = next(r.getMessage() for r in caplog.records if r.name == "app.agents.verifier")
    assert "frase_vs_trecho_citado=- frase_vs_trecho_min=-" in line


def test_obs_sequencia_inesperada_vira_indisponivel():
    assert similarity_diagnostics([("documents", [[1.0]])], GOOD, None, "factual", CH)["frase_vs_trecho"] is None


def test_obs_log_sem_texto_da_resposta_nem_das_evidencias(caplog):
    caplog.set_level(logging.INFO, logger="app.agents.verifier")
    st = run(FakeLLM(DOIS), settings=Settings(grounding_threshold=G))
    assert st["trace"] == ["router", "researcher", "reader", "verifier", "finalize"]
    text = "\n".join(r.getMessage() for r in caplog.records if r.name == "app.agents.verifier")
    for fragment in ("acurácia", "imagens", "médicas", "anotadas", "conjunto de teste", "Os dados vieram"):
        assert fragment not in text


# Resposta sem afirmação textual (só marcadores, vazia ou só pontuação) não pode ser aprovada.

SEM_TEXTO = "V2: a resposta não tem nenhuma afirmação em texto, só marcadores ou pontuação."


@pytest.mark.parametrize("draft", ["[3]", "[1] [2]", "", "   ", " .;! ", "[1].", "[2] . [1] !"],
                         ids=["so-[3]", "so-[1]-[2]", "vazia", "espacos", "pontuacao", "marcador-e-ponto", "misto"])
def test_resposta_sem_afirmacao_textual_reprova(draft):
    v = check(draft, None, "factual", CH, FakeEmb(), 0.6)
    assert not v["passed"] and v["problems"] == [SEM_TEXTO]


def test_resposta_com_texto_e_marcador_valido_nao_cai_na_regra_nova():
    v = check(GOOD, None, "factual", CH, FakeEmb(), 0.6)
    assert v["passed"] and SEM_TEXTO not in v["problems"]


def test_regras_existentes_continuam():
    e = FakeEmb()
    assert check("Texto sobre o artigo [9].", None, "factual", CH, e, 0.6)["problems"][0].startswith("V3")
    assert check("SEM_EVIDENCIA", None, "factual", CH, e, 0.6)["problems"] == ["V1: o modelo declarou falta de evidência."]
    assert check("Texto sem marcador.", None, "factual", CH, e, 0.6)["problems"] == ["V2: a resposta não tem nenhum marcador [n]."]
    assert check(CASOS["V4a"], None, "factual", CH, e, 0.6)["problems"][0].startswith("V4a")
    assert check(CASOS["V4b"], None, "factual", CH, e, 0.6)["problems"][0].startswith("V4b")
    # modo explicação: bloco ausente mantém a mensagem própria; bloco só com marcador cai na regra nova
    assert check("x", None, "explanation", CH, e, 0.6)["problems"][0].startswith("V2: faltou o bloco")
    assert check("x", "[1]", "explanation", CH, e, 0.6)["problems"] == [SEM_TEXTO]


def test_grafo_reformula_e_termina_em_insuficiente_com_resposta_so_de_marcador():
    llm = FakeLLM("[3]")  # o caso real da validação integrada
    st = run(llm, evidence=CH + [CH[0]])
    assert st["trace"] == ["router", "researcher", "reader", "verifier", "reader", "verifier", "insufficient"]
    assert st["status"] == "insufficient" and st["citations"] == [] and len(llm.calls) == 2
    assert SEM_TEXTO in llm.calls[1]  # o feedback da reformulação explica o problema ao modelo


# Cobertura: toda frase com afirmação precisa do seu marcador (não verifica se o trecho sustenta a frase).

EV7 = CH + [CH[0]] * 5  # 7 evidências, como na validação integrada
V6_ANSWER = '[1] [3] [5] [6] Os autores identificam várias limitações do uso de prompt de cadeia de pensamento. Uma delas é que a adição de exemplares manualmente com cadeias de pensamento pode ser custosa, especialmente para fine-tuning, embora isso possa ser superado com geração de dados sintéticos ou generalização zero-shot. Outra limitação é que não há garantia de que as cadeias de pensamento geradas sejam corretas, o que pode levar a respostas corretas e incorretas. Além disso, a emergência do pensamento de cadeia apenas em modelos de grande escala torna-o caro para servir em ambientes fora do domínio.'  # resposta literal aprovada com PROMPT_VERSION=6


def cobertura(*frases):
    """Mensagem esperada: contagem + início (até 60 caracteres) de cada frase descoberta + instrução."""
    lista = "; ".join(f"«{f[:60]}»" for f in frases)
    return (f"V2: {len(frases)} frase(s) com afirmação sem marcador: {lista}. Reescreva a resposta em frases "
            "completas e termine cada afirmação factual com o marcador da evidência que realmente a sustenta; "
            "um marcador que não corresponde a essa evidência não basta.")


def v6_descobertas():
    return [f.strip() for f in __import__("re").split(r"(?<=[.!?])\s+", V6_ANSWER)[1:]]


QUATRO = ["Primeira afirmação sobre o método", "Segunda afirmação sobre os dados",
          "Terceira afirmação sobre a escala", "Quarta afirmação sobre o custo"]


def test_quatro_frases_so_a_primeira_citada_reprova():
    draft = f"{QUATRO[0]} [1]. {QUATRO[1]}. {QUATRO[2]}. {QUATRO[3]}."
    assert check(draft, None, "factual", CH, FakeEmb(), 0.0)["problems"] == [cobertura(*(q + "." for q in QUATRO[1:]))]


def test_quatro_frases_todas_citadas_passa_pela_cobertura():
    draft = " ".join(f"{q} [{1 + i % 2}]." for i, q in enumerate(QUATRO))
    assert check(draft, None, "factual", CH, FakeEmb(), 0.0) == {"passed": True, "problems": []}


def test_frase_sem_marcador_entre_duas_citadas_reprova():
    draft = f"{QUATRO[0]} [1]. {QUATRO[1]}. {QUATRO[2]} [2]."
    assert check(draft, None, "factual", CH, FakeEmb(), 0.0)["problems"] == [cobertura(QUATRO[1] + ".")]


def test_resposta_da_versao_6_reprova_pela_cobertura():
    assert check(V6_ANSWER, None, "factual", EV7, FakeEmb(), 0.6)["problems"] == [cobertura(*v6_descobertas())]


def test_frase_so_com_marcador_nao_conta_como_afirmacao():
    # "[2]" sozinho não é afirmação: não reprova pela cobertura, e o resto da resposta tem citação
    assert check(f"{QUATRO[0]} [1]. [2]", None, "factual", CH, FakeEmb(), 0.0)["passed"]
    assert check("[3]", None, "factual", EV7, FakeEmb(), 0.6)["problems"] == [SEM_TEXTO]  # regra de texto preservada


def test_cobertura_preserva_as_demais_checagens():
    e = FakeEmb()
    assert check("Texto sobre o artigo [9].", None, "factual", CH, e, 0.6)["problems"][0].startswith("V3")
    assert check("SEM_EVIDENCIA", None, "factual", CH, e, 0.6)["problems"] == ["V1: o modelo declarou falta de evidência."]
    assert check("Texto sem marcador.", None, "factual", CH, e, 0.6)["problems"] == ["V2: a resposta não tem nenhum marcador [n]."]
    assert check(CASOS["V4a"], None, "factual", CH, e, 0.6)["problems"][0].startswith("V4a")
    assert check(CASOS["V4b"], None, "factual", CH, e, 0.6)["problems"][0].startswith("V4b")


def test_modo_explicacao_cobre_so_o_bloco_no_artigo():
    e = FakeEmb()
    ok = check("…", f"{QUATRO[0]} [1]. {QUATRO[1]} [2].", "explanation", CH, e, 0.0)
    assert ok["passed"]  # EM TERMOS SIMPLES não entra em factual, então não precisa de marcador
    falha = check("…", f"{QUATRO[0]} [1]. {QUATRO[1]}.", "explanation", CH, e, 0.0)
    assert falha["problems"] == [cobertura(QUATRO[1] + ".")]
    assert check("x", None, "explanation", CH, e, 0.6)["problems"][0].startswith("V2: faltou o bloco")


def test_separador_limites_conhecidos():
    # decimal sem espaço não quebra a frase
    assert check("A acurácia foi 92.5 por cento [1].", None, "factual",
                 [Evidence(1, 3, 0, "acurácia 92.5 por cento", 0.8)], FakeEmb(), 0.0)["passed"]
    # LIMITAÇÃO CONHECIDA (conservadora): "et al. " quebra a frase; a parte "Wei et al." fica sem marcador e reprova
    assert check("Wei et al. mostraram o efeito [1].", None, "factual", CH, FakeEmb(), 0.0)["problems"] == [cobertura("Wei et al.")]
    # marcador depois do ponto vai para a frase seguinte; a anterior fica descoberta
    assert check(f"{QUATRO[0]}. [1] {QUATRO[1]} [2].", None, "factual", CH, FakeEmb(), 0.0)["problems"] == [cobertura(QUATRO[0] + ".")]


def test_grafo_rejeita_cobertura_incompleta_e_termina_em_insuficiente():
    llm = FakeLLM(V6_ANSWER)  # o leitor repete a resposta da versão 6 nas duas tentativas
    st = run(llm, evidence=EV7, settings=Settings(grounding_threshold=0.6))
    assert st["trace"] == ["router", "researcher", "reader", "verifier", "reader", "verifier", "insufficient"]
    assert st["status"] == "insufficient" and st["citations"] == [] and len(llm.calls) == 2
    assert cobertura(*v6_descobertas()) in llm.calls[1]  # o feedback explica o problema ao modelo


# Feedback acionável da cobertura: diz quais frases precisam de marcador, sem afrouxar a regra.

def test_feedback_lista_so_as_frases_descobertas():
    draft = f"{QUATRO[0]} [1]. {QUATRO[1]}. {QUATRO[2]} [2]. {QUATRO[3]}."
    msg = check(draft, None, "factual", CH, FakeEmb(), 0.0)["problems"][0]
    assert msg.startswith("V2: 2 frase(s) com afirmação sem marcador:")
    assert f"«{QUATRO[1]}.»" in msg and f"«{QUATRO[3]}.»" in msg
    assert QUATRO[0] not in msg and QUATRO[2] not in msg  # frases com marcador ficam fora da lista


def test_fragmentos_limitados_a_60_caracteres():
    longa = "Esta frase sem marcador é deliberadamente longa para ultrapassar sessenta caracteres no total"
    msg = check(f"{QUATRO[0]} [1]. {longa}.", None, "factual", CH, FakeEmb(), 0.0)["problems"][0]
    fragmentos = __import__("re").findall(r"«([^»]*)»", msg)
    assert fragmentos == [longa[:60]] and len(fragmentos[0]) == 60


def test_feedback_pede_evidencia_que_sustenta_e_nao_so_marcador():
    msg = check(f"{QUATRO[0]} [1]. {QUATRO[1]}.", None, "factual", CH, FakeEmb(), 0.0)["problems"][0]
    assert "frases completas" in msg and "evidência que realmente a sustenta" in msg
    assert "um marcador que não corresponde a essa evidência não basta" in msg


def test_resposta_coberta_mantem_o_comportamento_anterior():
    for draft, esperado in [(GOOD, {"passed": True, "problems": []}),
                            (CASOS["V4a"], check(CASOS["V4a"], None, "factual", CH, FakeEmb(), 0.6))]:
        assert check(draft, None, "factual", CH, FakeEmb(), 0.6) == esperado
    assert check(CASOS["V4b"], None, "factual", CH, FakeEmb(), 0.6)["problems"][0].startswith("V4b")


def test_log_do_verificador_nao_traz_o_texto_das_frases(caplog):
    caplog.set_level(logging.INFO, logger="app.agents.verifier")
    run(FakeLLM(V6_ANSWER), evidence=EV7, settings=Settings(grounding_threshold=0.6))
    text = "\n".join(r.getMessage() for r in caplog.records if r.name == "app.agents.verifier")
    assert "stage=V2" in text
    for frase in v6_descobertas():
        assert frase[:30] not in text  # fragmentos só no feedback do Reader, nunca no log
