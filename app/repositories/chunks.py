import json
from dataclasses import dataclass

import numpy as np


@dataclass
class Evidence:
    chunk_id: int
    page_number: int
    chunk_index: int
    content: str
    similarity: float


def save_chunks(conn, document_id, chunks, vectors, filename: str) -> None:
    """Grava todos os chunks do documento numa única transação."""
    with conn.transaction():
        with conn.cursor() as cur:
            for c, v in zip(chunks, vectors, strict=True):
                cur.execute(
                    "INSERT INTO document_chunks (document_id, chunk_index, page_number, content, embedding, metadata)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (str(document_id), c.chunk_index, c.page_number, c.content, np.array(v),
                     json.dumps({"filename": filename, "char_count": c.char_count})),
                )


def count_chunks(conn, document_id) -> int:
    return conn.execute("SELECT count(*) FROM document_chunks WHERE document_id = %s", (str(document_id),)).fetchone()[0]


def search(conn, document_id, query_vector, top_k: int) -> list[Evidence]:
    """Top-k por cosseno, sempre filtrado por documento."""
    rows = conn.execute(
        "SELECT id, page_number, chunk_index, content, 1 - (embedding <=> %s) AS similarity"
        " FROM document_chunks WHERE document_id = %s ORDER BY embedding <=> %s LIMIT %s",
        (np.array(query_vector), str(document_id), np.array(query_vector), top_k),
    ).fetchall()
    return [Evidence(r[0], r[1], r[2], r[3], float(r[4])) for r in rows]


def by_indices(conn, document_id, chunk_indices: list[int], query_vector) -> list[Evidence]:
    """Chunks do documento pelos índices, com a similaridade real à consulta (usado para os vizinhos)."""
    if not chunk_indices:
        return []
    rows = conn.execute(
        "SELECT id, page_number, chunk_index, content, 1 - (embedding <=> %s) AS similarity"
        " FROM document_chunks WHERE document_id = %s AND chunk_index = ANY(%s)",
        (np.array(query_vector), str(document_id), list(chunk_indices)),
    ).fetchall()
    return [Evidence(r[0], r[1], r[2], r[3], float(r[4])) for r in rows]


def chunks_by_page(conn, document_id) -> list[Evidence]:
    rows = conn.execute(
        "SELECT id, page_number, chunk_index, content, 0 FROM document_chunks WHERE document_id = %s ORDER BY chunk_index",
        (str(document_id),),
    ).fetchall()
    return [Evidence(r[0], r[1], r[2], r[3], 0.0) for r in rows]
