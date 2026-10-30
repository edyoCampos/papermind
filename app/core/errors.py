"""Erros de domínio. `user_message` é exibida sem alteração pela API e pela interface."""


class PaperMindError(Exception):
    user_message = "Ocorreu um erro inesperado."

    def __init__(self, user_message: str | None = None):
        self.user_message = user_message or self.user_message
        super().__init__(self.user_message)


class IngestionError(PaperMindError):
    pass


class InvalidPdfError(IngestionError):
    user_message = "O arquivo enviado não é um PDF. Envie um arquivo .pdf."


class FileTooLargeError(IngestionError):
    pass


class TooManyPagesError(IngestionError):
    pass


class NoExtractableTextError(IngestionError):
    user_message = (
        "Não foi possível extrair texto deste PDF. Ele parece ser digitalizado (imagem); "
        "OCR não faz parte desta versão."
    )


class DatabaseUnavailableError(PaperMindError):
    user_message = "Banco indisponível em postgres:5432. Rode 'docker compose up -d postgres'."


class ModelUnavailableError(PaperMindError):
    user_message = "Ollama indisponível em http://ollama:11434. Rode 'docker compose up -d ollama'."


class DocumentNotFoundError(PaperMindError):
    user_message = "Documento não encontrado."


class DocumentNotReadyError(PaperMindError):
    user_message = "O documento ainda não está pronto."
