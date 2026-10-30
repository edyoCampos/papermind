"""Cliente httpx da API. Falhas viram ApiError com mensagem pronta para a tela."""
import httpx

ASK_TIMEOUT = 240
SUMMARY_TIMEOUT = 600


class ApiError(Exception):
    pass


def _request(base: str, method: str, path: str, timeout: float, transport=None, **kw) -> dict:
    try:
        with httpx.Client(base_url=base, timeout=timeout, transport=transport) as c:
            r = c.request(method, path, **kw)
    except httpx.ConnectError:
        raise ApiError(f"Não foi possível conectar à API em {base}. Ela está rodando?") from None
    except httpx.TimeoutException:
        raise ApiError("A resposta demorou demais. Tente uma pergunta mais curta ou verifique o Ollama.") from None
    if r.status_code >= 400:
        try:
            detail = r.json()["detail"]
        except Exception:  # noqa: BLE001
            detail = f"Erro {r.status_code} da API."
        raise ApiError(detail)
    return r.json()


def upload(base: str, filename: str, data: bytes, transport=None) -> dict:
    return _request(base, "POST", "/documents", 60, transport, files={"file": (filename, data, "application/pdf")})


def get_status(base: str, document_id: str, transport=None) -> dict:
    return _request(base, "GET", f"/documents/{document_id}", 15, transport)


def get_summary(base: str, document_id: str, transport=None) -> dict:
    return _request(base, "GET", f"/documents/{document_id}/summary", SUMMARY_TIMEOUT, transport)


def ask(base: str, document_id: str, question: str, mode: str, transport=None) -> dict:
    return _request(base, "POST", f"/documents/{document_id}/questions", ASK_TIMEOUT, transport,
                    json={"question": question, "mode": mode})
