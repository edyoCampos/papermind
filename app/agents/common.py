import re
from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import Settings
from app.core.errors import ModelUnavailableError
from app.rag.llm import MODEL_DOWN
from app.rag.retriever import RetrievalResult

MARKER = re.compile(r"\[(\d+)\]")


@dataclass
class Deps:
    """Dependências injetáveis: nos testes entram versões falsas, sem Ollama."""
    settings: Settings
    retrieve: Callable[[str, str], RetrievalResult]
    llm: Callable[[str], str]
    embedder: Any  # embed_query(str) e embed_documents(list[str])


def safe(name: str, fn):
    """Converte falha do modelo local em status=error, sem exceção crua (RF-15)."""
    def wrapped(state):
        try:
            return fn(state)
        except (ModelUnavailableError, ConnectionError, OSError):
            return {"status": "error", "error_message": MODEL_DOWN, "trace": [name]}
    wrapped.__name__ = name
    return wrapped
