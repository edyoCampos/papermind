import logging
import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from app.core.errors import InvalidPdfError, NoExtractableTextError, TooManyPagesError

log = logging.getLogger(__name__)
MIN_CHARS = 200


@dataclass
class PageText:
    page_number: int  # 1..page_count, posição física
    text: str


def normalize(text: str) -> str:
    text = re.sub(r"-\n", "", text)
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def extract_pages(data: bytes, max_pages: int) -> tuple[int, list[PageText]]:
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise InvalidPdfError("O PDF está protegido por senha. Envie uma versão sem proteção.")
        page_count = len(reader.pages)
    except InvalidPdfError:
        raise
    except Exception:
        log.exception("falha ao abrir o PDF")
        raise InvalidPdfError("O PDF está corrompido ou não pôde ser lido.") from None
    if page_count > max_pages:
        raise TooManyPagesError(f"O PDF tem {page_count} páginas; o limite é {max_pages}.")

    pages: list[PageText] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = normalize(page.extract_text() or "")
        except Exception:
            log.warning("falha ao extrair a página %d; tratada como vazia", number)
            text = ""
        pages.append(PageText(number, text))
    if sum(len(p.text) for p in pages) < MIN_CHARS:
        raise NoExtractableTextError()
    return page_count, pages
