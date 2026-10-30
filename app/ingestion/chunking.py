from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.extract import PageText


@dataclass
class Chunk:
    chunk_index: int  # 0..N-1 no documento
    page_number: int
    content: str
    char_count: int


def chunk_pages(pages: list[PageText], chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Divide cada página separadamente: nenhum chunk cruza páginas."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks: list[Chunk] = []
    for page in pages:
        if not page.text:
            continue
        for piece in splitter.split_text(page.text):
            chunks.append(Chunk(len(chunks), page.page_number, piece, len(piece)))
    return chunks
