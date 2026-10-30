import httpx
from langchain_ollama import OllamaEmbeddings

from app.core.config import Settings, get_settings
from app.core.errors import ModelUnavailableError

BATCH = 16


class Embedder:
    """Embeddings locais com os prefixos recomendados pelo nomic-embed-text."""

    def __init__(self, settings: Settings | None = None, backend=None):
        s = settings or get_settings()
        self._backend = backend or OllamaEmbeddings(model=s.embedding_model, base_url=s.ollama_base_url)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            batch = ["search_document: " + t for t in texts[i:i + BATCH]]
            out.extend(self._call(self._backend.embed_documents, batch))
        return out

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Consulta vazia.")
        return self._call(self._backend.embed_query, "search_query: " + text)

    @staticmethod
    def _call(fn, arg):
        try:
            return fn(arg)
        except (httpx.HTTPError, ConnectionError, OSError) as exc:
            raise ModelUnavailableError("Não foi possível gerar embeddings: Ollama indisponível.") from exc
