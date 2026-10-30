import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import (DatabaseUnavailableError, DocumentNotFoundError, DocumentNotReadyError,
                             FileTooLargeError, IngestionError, ModelUnavailableError)

log = logging.getLogger(__name__)

# Ordem importa: classes mais específicas primeiro.
STATUS = [
    (FileTooLargeError, 413),
    (IngestionError, 400),
    (DocumentNotFoundError, 404),
    (DocumentNotReadyError, 409),
    (ModelUnavailableError, 503),
    (DatabaseUnavailableError, 503),
]


def _reply(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def register_handlers(app: FastAPI) -> None:
    for exc_class, status in STATUS:
        def handler(request: Request, exc, status=status):
            return _reply(status, exc.user_message)
        app.add_exception_handler(exc_class, handler)

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        locs = {str(p) for e in exc.errors() for p in e["loc"]}
        if "file" in locs:
            return _reply(422, "Envie um arquivo PDF no campo 'file'.")
        if "question" in locs:
            return _reply(422, "A pergunta deve ter entre 1 e 1000 caracteres.")
        return _reply(422, "Requisição inválida. Confira os campos enviados.")

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("erro inesperado em %s %s", request.method, request.url.path)
        return _reply(500, "Erro interno. Veja o log da API.")
