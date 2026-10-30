from app.agents.common import MARKER, Deps
from app.agents.finalize import build_citations
from app.agents.prompts import section_prompt

SECTIONS = {
    "objetivo": "objetivo do estudo e pergunta de pesquisa",
    "metodologia": "método, dados e procedimento experimental",
    "resultados": "principais resultados e números obtidos",
    "limitações": "limitações do estudo e ameaças à validade",
    "contribuição": "contribuição e conclusão do trabalho",
}
NOT_FOUND = {"status": "not_found", "text": "Não encontrado no artigo.", "citations": []}


def make_summarizer(deps: Deps):
    def summarizer(state):
        summary = {}
        for name, query in SECTIONS.items():
            r = deps.retrieve(state["document_id"], query)
            if not r.relevant:
                summary[name] = dict(NOT_FOUND)
                continue
            text = deps.llm(section_prompt(name, r.evidence)).strip()
            refs = [int(n) for n in MARKER.findall(text)]
            valid = refs and all(1 <= n <= len(r.evidence) for n in refs)  # V3
            if text.strip(".").upper() == "SEM_EVIDENCIA" or not valid:
                summary[name] = dict(NOT_FOUND)
            else:
                summary[name] = {"status": "found", "text": text, "citations": build_citations(text, r.evidence)}
        return {"summary": summary, "status": "answered", "trace": ["summarizer"]}
    return summarizer
