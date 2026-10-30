import operator
from typing import Annotated, Literal, TypedDict

from app.repositories.chunks import Evidence


class Citation(TypedDict):
    ref: int
    page_number: int
    chunk_id: int
    excerpt: str
    similarity: float


class PaperState(TypedDict, total=False):
    document_id: str
    request_type: Literal["question", "summary"]
    question: str | None
    mode: Literal["auto", "factual", "explanation"]
    intent: Literal["factual", "explanation", "summary"] | None
    evidence: list[Evidence]
    nearest: list[Evidence]  # trechos mais próximos, só para a mensagem de insuficiência
    relevant: bool
    max_similarity: float
    draft: str | None
    article_part: str | None
    simple_explanation: str | None
    verification: dict | None  # {passed, problems}
    attempts: int
    answer: str | None
    citations: list[Citation]
    summary: dict | None
    status: Literal["answered", "insufficient", "error"] | None
    message: str | None
    error_message: str | None
    trace: Annotated[list[str], operator.add]
