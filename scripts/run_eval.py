"""Uso: python -m scripts.run_eval   (roda as perguntas de eval/questions.json sem usar o cache)"""
import datetime
import sys
import time
from pathlib import Path

from scripts.eval_data import EvalDataError, check_composition, load_articles, load_questions

RUBRIC = ["C1", "C2", "C3", "C4", "C5"]


def page_hit(row: dict) -> str:
    if row["expected_status"] != "answered" or not row["expected_pages"]:
        return "n/a"
    return "sim" if set(row["cited_pages"]) & set(row["expected_pages"]) else "não"


def build_report(rows: list[dict], warnings: list[str]) -> str:
    errors = sum(1 for r in rows if r["status"] == "error")
    matched = sum(1 for r in rows if r["status"] == r["expected_status"])
    lines = [f"# Avaliação — {datetime.date.today().isoformat()}", "",
             f"Perguntas: {len(rows)} · status igual ao esperado: {matched} · erros: {errors}", ""]
    lines += [f"> Aviso: {w}" for w in warnings] + ([""] if warnings else [])
    lines += ["Rubrica manual (0/1): C1 correção factual · C2 afirmações sustentadas · C3 citação corresponde à página "
              "e ao trecho · C4 clareza · C5 comportamento correto na insuficiência. Aprovada = todos os critérios "
              "aplicáveis em 1 (sem_resposta: só C5).", ""]
    head = ["id", "tipo", "pergunta", "status (obtido × esperado)", "resposta", "páginas citadas",
            "acerto de página", "trace", "max_similarity", "tempo (s)"] + RUBRIC
    lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = [r["id"], r["type"], r["question"], f'{r["status"]} × {r["expected_status"]}',
                 (r["answer"] or "").replace("\n", " ").replace("|", "/"), ", ".join(map(str, r["cited_pages"])),
                 page_hit(r), " → ".join(r["trace"]), f'{r["max_similarity"]:.3f}', f'{r["seconds"]:.1f}'] + [""] * 5
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def run_one(q: dict, document_id: str, answer_question) -> dict:
    t0 = time.time()
    row = {**q, "cited_pages": [], "answer": "", "trace": [], "max_similarity": 0.0}
    try:
        st = answer_question(document_id, q["question"], q["mode"])
        row.update(status=st.get("status", "error"), trace=st.get("trace", []),
                   max_similarity=st.get("max_similarity", 0.0),
                   cited_pages=sorted({c["page_number"] for c in st.get("citations", [])}))
        row["answer"] = st.get("answer") or st.get("article_part") or st.get("message") or st.get("error_message") or ""
    except Exception as exc:  # noqa: BLE001  a pergunta vira 'error' e a avaliação continua
        row.update(status="error", answer=f"{type(exc).__name__}: {exc}")
    row["seconds"] = time.time() - t0
    return row


def main() -> int:
    try:
        articles, questions = load_articles(), load_questions()
    except EvalDataError as exc:
        print(f"ERRO: {exc}")
        return 1
    if not questions:
        print("ERRO: eval/questions.json está vazio. Crie as perguntas (veja docs/decisions.md e docs/demo-script.md).")
        return 1
    from app.services.indexing import index_document, register_document
    from app.services.qa import answer_question

    docs: dict[str, str | None] = {}
    for a in articles:
        p = Path(a["path"])
        if not p.exists():
            print(f"Artigo ausente: {a['title']}. Baixe de {a['url']} para {a['path']}.")
            docs[a["id"]] = None
            continue
        doc = register_document(p.name)
        index_document(doc, p.read_bytes(), p.name)
        docs[a["id"]] = str(doc)
        print(f"{a['id']} indexado: document_id={doc}")
    rows = []
    for n, q in enumerate(questions, 1):
        doc = docs.get(q["article_id"])
        row = (run_one(q, doc, answer_question) if doc else
               {**q, "status": "error", "answer": "artigo ausente", "cited_pages": [], "trace": [],
                "max_similarity": 0.0, "seconds": 0.0})
        rows.append(row)
        print(f"[{n}/{len(questions)}] {q['id']} ... {row['status']} (esperado: {q['expected_status']}) {row['seconds']:.1f} s")
    out = Path("eval/results") / f"{datetime.date.today().isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report(rows, check_composition(questions)))
    print(f"Relatório: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
