"""Uso: python -m scripts.calibrate_threshold <document_id> [eval/questions.json]
Usa os itens com calibration=true (expected_status=answered conta como respondível)."""
import sys

from app.core.config import get_settings
from app.db.connection import connect
from app.rag.embeddings import Embedder
from app.repositories import chunks as chunk_repo
from scripts.eval_data import EvalDataError, load_questions


def suggest(answerable: list[float], unanswerable: list[float]) -> float | None:
    """Ponto médio entre a menor máxima respondível e a maior máxima sem resposta."""
    if not answerable or not unanswerable:
        return None
    return (min(answerable) + max(unanswerable)) / 2


def main(document_id: str, path: str = "eval/questions.json") -> int:
    try:
        items = [q for q in load_questions(path) if q.get("calibration")]
    except EvalDataError as exc:
        print(f"ERRO: {exc}")
        return 1
    s, emb = get_settings(), Embedder()
    ok, no = [], []
    with connect() as conn:
        for q in items:
            found = chunk_repo.search(conn, document_id, emb.embed_query(q["question"]), s.top_k)
            m = max((e.similarity for e in found), default=0.0)
            answerable = q["expected_status"] == "answered"
            (ok if answerable else no).append(m)
            print(f"{'respondível' if answerable else 'sem resposta':>13} {m:.3f}  {q['question']}")
    sug = suggest(ok, no)
    if sug is None:
        print("É preciso ao menos uma pergunta de cada grupo com calibration=true (idealmente 3+3).")
        return 1
    if min(ok) <= max(no):
        print("AVISO: limiares se sobrepõem; revise o chunking ou as perguntas e registre o valor adotado.")
    print(f"limiar sugerido: {sug:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
