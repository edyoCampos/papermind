"""Uso: python -m scripts.ingest data/artigo.pdf"""
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import IngestionError
from app.ingestion import ingest_pdf


def main(path: str) -> int:
    p = Path(path)
    try:
        result = ingest_pdf(p.read_bytes(), p.name, get_settings())
    except IngestionError as exc:
        print(f"ERRO: {exc.user_message}")
        return 1
    print(f"páginas: {result.page_count} · chunks: {len(result.chunks)}")
    for c in result.chunks[:3]:
        print(f"[p.{c.page_number} #{c.chunk_index}] {c.content[:100]}")
    from app.core.errors import PaperMindError
    from app.services.indexing import index_document, register_document

    doc_id = register_document(p.name)
    try:
        index_document(doc_id, p.read_bytes(), p.name)
    except PaperMindError as exc:
        print(f"ERRO: {exc.user_message}")
        return 1
    print(f"document_id: {doc_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
