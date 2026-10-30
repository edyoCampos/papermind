from typing import Literal

from pydantic import BaseModel, field_validator


class DocumentCreated(BaseModel):
    document_id: str
    filename: str
    status: str


class DocumentStatus(BaseModel):
    document_id: str
    filename: str
    status: str
    page_count: int | None
    chunk_count: int
    error_message: str | None


class Citation(BaseModel):
    ref: int
    page_number: int
    chunk_id: int
    excerpt: str
    similarity: float


class Nearest(BaseModel):
    page_number: int
    excerpt: str
    similarity: float


class SummarySection(BaseModel):
    status: Literal["found", "not_found"]
    text: str
    citations: list[Citation] = []


class SummarySections(BaseModel):
    objective: SummarySection
    methodology: SummarySection
    results: SummarySection
    limitations: SummarySection
    contribution: SummarySection


class SummaryResponse(BaseModel):
    document_id: str
    sections: SummarySections


class QuestionRequest(BaseModel):
    question: str
    mode: Literal["auto", "factual", "explanation"] = "auto"

    @field_validator("question")
    @classmethod
    def _tamanho(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= 1000:
            raise ValueError("pergunta fora do tamanho")
        return v


class QuestionResponse(BaseModel):
    status: Literal["answered", "insufficient"]
    intent: Literal["factual", "explanation"]
    answer: str | None = None
    article_part: str | None = None
    simple_explanation: str | None = None
    message: str | None = None
    citations: list[Citation] = []
    nearest_excerpts: list[Nearest] = []
    trace: list[str]
    cached: bool = False
    cache_status: Literal["hit", "miss", "disabled", "unavailable"] = "disabled"
