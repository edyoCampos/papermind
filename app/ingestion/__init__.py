"""Ingestão de PDF: função pura, sem banco nem rede."""
import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.ingestion.chunking import Chunk, chunk_pages
from app.ingestion.extract import extract_pages
from app.ingestion.validation import validate_upload

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    page_count: int
    chunks: list[Chunk]


def ingest_pdf(data: bytes, filename: str, settings: Settings) -> IngestResult:
    validate_upload(data, filename, settings.max_upload_mb)
    page_count, pages = extract_pages(data, settings.max_pages)
    chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
    log.info("ingestão: %s, %d páginas, %d chunks", filename, page_count, len(chunks))
    return IngestResult(page_count, chunks)
