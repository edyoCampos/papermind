import re
import unicodedata

PADROES = ("o que e", "o que sao", "o que significa", "explique", "explica", "defina",
           "qual o significado", "what is", "what are", "explain", "define")
_RE = re.compile(r"^(" + "|".join(PADROES) + r")\b")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower().strip())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def classify(request_type: str, mode: str, question: str | None) -> str:
    """Orquestrador sem LLM: tipo do pedido, depois modo explícito, depois regra de texto."""
    if request_type == "summary":
        return "summary"
    if mode in ("factual", "explanation"):
        return mode
    return "explanation" if _RE.match(_norm(question or "")) else "factual"


def router_node(state):
    intent = classify(state.get("request_type", "question"), state.get("mode", "auto"), state.get("question"))
    return {"intent": intent, "attempts": 0, "trace": ["router"]}


def route_after_router(state) -> str:
    return "summarizer" if state["intent"] == "summary" else "researcher"
