from app.agents.common import MARKER

MSG_FACTUAL = "O artigo não traz evidência suficiente para responder a essa pergunta."
MSG_EXPLANATION = ("O artigo não traz evidência suficiente sobre esse termo. "
                   "Esta versão não oferece explicação sem apoio no artigo.")


def build_citations(text: str, evidence) -> list[dict]:
    """Citações montadas dos chunks recuperados; nada vem do texto do LLM além do número [n]."""
    refs: list[int] = []
    for n in (int(x) for x in MARKER.findall(text)):
        if 1 <= n <= len(evidence) and n not in refs:
            refs.append(n)
    return [{"ref": n, "page_number": evidence[n - 1].page_number, "chunk_id": evidence[n - 1].chunk_id,
             "excerpt": evidence[n - 1].content[:300], "similarity": evidence[n - 1].similarity} for n in refs]


def finalize(state):
    if state["intent"] == "explanation":
        answer = f"NO ARTIGO: {state['article_part']}\nEM TERMOS SIMPLES: {state['simple_explanation']}"
        factual = state["article_part"]
    else:
        answer = factual = state["draft"]
    return {"answer": answer, "citations": build_citations(factual, state["evidence"]),
            "status": "answered", "trace": ["finalize"]}


def insufficient(state):
    msg = MSG_EXPLANATION if state.get("intent") == "explanation" else MSG_FACTUAL
    return {"status": "insufficient", "message": msg, "citations": [], "trace": ["insufficient"]}
