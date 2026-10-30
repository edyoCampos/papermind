"""Carga e validação de eval/articles.json e eval/questions.json."""
import json
from pathlib import Path

TYPES = {"direta", "sintese", "conceito", "sem_resposta"}
MODES = {"auto", "factual", "explanation"}
STATUSES = {"answered", "insufficient"}
ARTICLE_FIELDS = ("id", "title", "url", "license", "path")
QUESTION_FIELDS = ("id", "article_id", "type", "question", "mode", "expected_status", "expected_pages")


class EvalDataError(Exception):
    pass


def _load(path: str) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise EvalDataError(f"Crie {path} (veja docs/decisions.md).") from None
    except ValueError as exc:
        raise EvalDataError(f"{path}: JSON inválido ({exc}).") from None
    if not isinstance(data, list):
        raise EvalDataError(f"{path}: esperava uma lista.")
    return data


def load_articles(path: str = "eval/articles.json") -> list[dict]:
    items = _load(path)
    for i, a in enumerate(items):
        for f in ARTICLE_FIELDS:
            if not a.get(f):
                raise EvalDataError(f"{path}: item {i + 1} sem o campo '{f}'.")
    return items


def load_questions(path: str = "eval/questions.json") -> list[dict]:
    items = _load(path)
    for i, q in enumerate(items):
        ref = q.get("id", f"#{i + 1}")
        for f in QUESTION_FIELDS:
            if f not in q:
                raise EvalDataError(f"{path}: item {ref} sem o campo '{f}'.")
        if q["type"] not in TYPES or q["mode"] not in MODES or q["expected_status"] not in STATUSES:
            raise EvalDataError(f"{path}: item {ref} com type, mode ou expected_status inválido.")
        if not isinstance(q["expected_pages"], list) or not all(isinstance(p, int) for p in q["expected_pages"]):
            raise EvalDataError(f"{path}: item {ref} com expected_pages inválido.")
        if q["type"] == "sem_resposta" and (q["expected_status"] != "insufficient" or q["expected_pages"]):
            raise EvalDataError(f"{path}: item {ref} 'sem_resposta' deve ter insufficient e páginas vazias.")
    return items


def check_composition(items: list[dict]) -> list[str]:
    """Avisos sobre o conjunto final (20 itens, ≥4 sem_resposta, ≥4 conceito, ≥6 calibration)."""
    w = []
    count = lambda t: sum(1 for q in items if q["type"] == t)  # noqa: E731
    if len(items) != 20:
        w.append(f"o conjunto tem {len(items)} itens; o esperado é 20")
    if count("sem_resposta") < 4:
        w.append("menos de 4 perguntas 'sem_resposta'")
    if count("conceito") < 4:
        w.append("menos de 4 perguntas 'conceito'")
    if sum(1 for q in items if q.get("calibration")) < 6:
        w.append("menos de 6 perguntas com calibration=true")
    return w
