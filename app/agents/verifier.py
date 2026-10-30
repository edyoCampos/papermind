import logging
import math
import re

from app.agents.common import MARKER, Deps

log = logging.getLogger(__name__)
NUM = re.compile(r"\d+(?:[.,]\d+)?")
SENT = re.compile(r"(?<=[.!?])\s+")
LETTER = re.compile(r"[^\W\d_]")  # qualquer letra, inclusive acentuada
# Só para diagnóstico: colchetes com dígito fora do formato [n], como [1, 2], [ 1 ] ou [1-3].
MALFORMED = re.compile(r"\[(?!\d+\])[^\[\]\n]{0,12}\d[^\[\]\n]{0,12}\]")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in NUM.findall(text)}


def _cos(a, b) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def check(draft: str, article_part: str | None, intent: str, evidence, embedder, grounding: float) -> dict:
    """Confronta a resposta com os trechos recuperados (V1..V4)."""
    problems: list[str] = []
    if draft.strip().strip(".").upper() == "SEM_EVIDENCIA":
        return {"passed": False, "problems": ["V1: o modelo declarou falta de evidência."]}
    factual = article_part if intent == "explanation" else draft
    if intent == "explanation" and not factual:
        return {"passed": False, "problems": ["V2: faltou o bloco 'NO ARTIGO:' com citações."]}
    if not LETTER.search(MARKER.sub("", factual or "")):  # só marcadores, espaços ou pontuação
        return {"passed": False, "problems": ["V2: a resposta não tem nenhuma afirmação em texto, só marcadores ou pontuação."]}
    if not MARKER.search(factual):
        return {"passed": False, "problems": ["V2: a resposta não tem nenhum marcador [n]."]}
    # cobertura: toda frase com texto precisa do seu marcador; frases só com marcador não contam como afirmação
    uncovered = [s for s in SENT.split(factual) if LETTER.search(MARKER.sub("", s)) and not MARKER.search(s)]
    if uncovered:
        # só vai para o feedback do Reader; o log registra apenas o código (describe)
        frases = "; ".join(f"«{s.strip()[:60]}»" for s in uncovered)
        return {"passed": False, "problems": [
            f"V2: {len(uncovered)} frase(s) com afirmação sem marcador: {frases}. Reescreva a resposta em frases "
            "completas e termine cada afirmação factual com o marcador da evidência que realmente a sustenta; "
            "um marcador que não corresponde a essa evidência não basta."]}
    for sentence in SENT.split(factual):
        refs = [int(n) for n in MARKER.findall(sentence)]
        if not refs:
            continue
        bad = [n for n in refs if not 1 <= n <= len(evidence)]
        if bad:
            problems.append(f"V3: marcador(es) {bad} não existem; use só 1..{len(evidence)}.")
            continue
        cited = [evidence[n - 1].content for n in refs]
        clean = MARKER.sub("", sentence).strip()
        missing = _numbers(clean) - _numbers(" ".join(cited))
        if missing:
            problems.append(f"V4a: número(s) {sorted(missing)} não aparecem nos trechos citados.")
        if grounding > 0 and clean:
            qv = embedder.embed_query(clean)
            best = max(_cos(qv, cv) for cv in embedder.embed_documents(cited))
            if best < grounding:
                problems.append(f"V4b: a frase '{clean[:60]}' não é sustentada pelos trechos citados.")
    return {"passed": not problems, "problems": problems}


def describe(draft: str, article_part: str | None, intent: str, evidence, verification: dict) -> dict:
    """Resume o resultado já calculado por check() só com códigos e contagens, sem texto."""
    codes = list(dict.fromkeys(p.split(":", 1)[0] for p in verification["problems"]))
    factual = (article_part if intent == "explanation" else draft) or ""
    refs = [int(n) for n in MARKER.findall(factual)]
    invalid = sorted({n for n in refs if not 1 <= n <= len(evidence)})
    malformed = len(MALFORMED.findall(factual))
    sentences = [s for s in SENT.split(factual) if s.strip()]
    if intent == "explanation" and not article_part:
        markers = "sem_bloco_no_artigo"
    elif not refs:
        markers = "malformado" if malformed else "ausente"
    elif invalid:
        markers = "fora_do_intervalo"
    else:
        markers = "ok"
    return {"result": "APROVADA" if verification["passed"] else "REPROVADA",
            "stage": codes[0] if codes else "-", "codes": codes, "markers": markers,
            "valid": len(refs) - sum(1 for n in refs if n in invalid), "invalid": invalid,
            "malformed": malformed, "sentences_marked": sum(1 for s in sentences if MARKER.search(s)),
            "sentences": len(sentences), "evidence": len(evidence), "draft_chars": len(draft)}


class _RecordingEmbedder:
    """Repassa cada chamada ao embedder real, sem alterá-la, e anota os vetores devolvidos (só diagnóstico)."""

    def __init__(self, inner):
        self._inner = inner
        self.calls: list[tuple[str, object]] = []

    def embed_query(self, text):
        vector = self._inner.embed_query(text)
        self.calls.append(("query", vector))
        return vector

    def embed_documents(self, texts):
        vectors = self._inner.embed_documents(texts)
        self.calls.append(("documents", vectors))
        return vectors


def similarity_diagnostics(calls, draft: str, article_part: str | None, intent: str, evidence) -> dict:
    """Similaridades já calculadas por check(), sem novas chamadas. Duas famílias distintas:
    frase_vs_trecho = a mesma conta da V4b (frase citada x trechos citados);
    recuperacao_pergunta = Evidence.similarity, da busca (pergunta x trecho)."""
    pairs = list(zip(calls[0::2], calls[1::2]))
    if len(calls) % 2 or any(q[0] != "query" or d[0] != "documents" for q, d in pairs):
        sent = None  # sequência inesperada: não arrisca um número errado
    else:
        sent = [max(_cos(q[1], cv) for cv in d[1]) for q, d in pairs]
    factual = (article_part if intent == "explanation" else draft) or ""
    cited = sorted({int(n) for n in MARKER.findall(factual) if 1 <= int(n) <= len(evidence)})
    return {"frase_vs_trecho": sent,
            "recuperacao_citados": [evidence[n - 1].similarity for n in cited],
            "recuperacao_max": max((e.similarity for e in evidence), default=None)}


def _fmt(values) -> str:
    return "-" if not values else "[" + ",".join(f"{x:.3f}" for x in values) + "]"


def make_verifier(deps: Deps):
    def verifier(state):
        recorder = _RecordingEmbedder(deps.embedder)
        v = check(state["draft"], state.get("article_part"), state["intent"], state["evidence"],
                  recorder, deps.settings.grounding_threshold)
        d = describe(state["draft"], state.get("article_part"), state["intent"], state["evidence"], v)
        s = similarity_diagnostics(recorder.calls, state["draft"], state.get("article_part"), state["intent"],
                                   state["evidence"])
        sent = s["frase_vs_trecho"]
        log.info("verifier result=%s stage=%s codes=%s markers=%s valid=%d invalid=%s malformed=%d "
                 "sentences_marked=%d/%d evidence=%d draft_chars=%d attempt=%d intent=%s doc=%s "
                 "frase_vs_trecho_citado=%s frase_vs_trecho_min=%s "
                 "recuperacao_pergunta_vs_citados=%s recuperacao_pergunta_max=%s",
                 d["result"], d["stage"], ",".join(d["codes"]) or "-", d["markers"], d["valid"], d["invalid"],
                 d["malformed"], d["sentences_marked"], d["sentences"], d["evidence"], d["draft_chars"],
                 state.get("attempts", 0), state["intent"], state.get("document_id"),
                 "indisponivel" if sent is None else _fmt(sent),
                 "-" if not sent else f"{min(sent):.3f}",
                 _fmt(s["recuperacao_citados"]),
                 "-" if s["recuperacao_max"] is None else f"{s['recuperacao_max']:.3f}")
        return {"verification": v, "trace": ["verifier"]}
    return verifier


def verification_gate(state) -> str:
    if state.get("status") == "error":
        return "end"
    v = state["verification"]
    if v["passed"]:
        return "finalize"
    if v["problems"][0].startswith("V1") or state["attempts"] >= 1:
        return "insufficient"
    return "reader"
