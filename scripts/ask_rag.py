"""Uso: python -m scripts.ask_rag <document_id> "<pergunta>" """
import sys

from app.core.errors import PaperMindError
from app.rag.retriever import retrieve


def main(document_id: str, question: str) -> int:
    try:
        r = retrieve(document_id, question)
    except PaperMindError as exc:
        print(f"ERRO: {exc.user_message}")
        return 1
    print(f"relevante: {r.relevant} · similaridade máxima: {r.max_similarity:.3f}")
    for e in r.evidence:
        print(f"[p.{e.page_number} · {e.similarity:.3f}] {e.content[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
