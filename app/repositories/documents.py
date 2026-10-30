import json
import uuid
from dataclasses import dataclass

from app.core.errors import DocumentNotFoundError


@dataclass
class Document:
    id: uuid.UUID
    filename: str
    status: str
    error_message: str | None
    page_count: int | None
    summary: dict | None


def create_document(conn, filename: str) -> uuid.UUID:
    doc_id = uuid.uuid4()
    conn.execute("INSERT INTO documents (id, filename, status) VALUES (%s, %s, 'received')", (doc_id, filename))
    return doc_id


def get_document(conn, document_id) -> Document:
    row = conn.execute(
        "SELECT id, filename, status, error_message, page_count, summary FROM documents WHERE id = %s",
        (str(document_id),),
    ).fetchone()
    if not row:
        raise DocumentNotFoundError()
    return Document(*row)


def set_status(conn, document_id, status: str, error_message: str | None = None, page_count: int | None = None) -> None:
    conn.execute(
        "UPDATE documents SET status = %s, error_message = %s, page_count = COALESCE(%s, page_count) WHERE id = %s",
        (status, error_message, page_count, str(document_id)),
    )


def save_summary(conn, document_id, summary: dict) -> None:
    conn.execute("UPDATE documents SET summary = %s WHERE id = %s", (json.dumps(summary), str(document_id)))


def get_summary(conn, document_id) -> dict | None:
    return get_document(conn, document_id).summary
