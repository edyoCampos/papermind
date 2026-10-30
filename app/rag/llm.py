import httpx
import ollama
from langchain_ollama import ChatOllama

from app.core.config import Settings, get_settings
from app.core.errors import ModelUnavailableError

MODEL_DOWN = "Modelo local indisponível. Verifique o serviço ollama com 'docker compose ps'."


def make_llm(settings: Settings | None = None):
    """Devolve `llm(prompt) -> str`. Temperatura 0 e teto de tokens (latência em CPU)."""
    s = settings or get_settings()
    chat = ChatOllama(model=s.chat_model, base_url=s.ollama_base_url, temperature=0,
                      num_predict=s.llm_num_predict, client_kwargs={"timeout": s.llm_timeout_seconds})

    def llm(prompt: str) -> str:
        try:
            return str(chat.invoke(prompt).content)
        except (httpx.HTTPError, ConnectionError, OSError, ollama.ResponseError) as exc:
            raise ModelUnavailableError(MODEL_DOWN) from exc

    return llm
