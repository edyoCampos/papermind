import re

from app.agents.common import Deps
from app.agents.prompts import reader_prompt

_RE = re.compile(r"NO ARTIGO:\s*(.*?)\s*EM TERMOS SIMPLES:\s*(.*)", re.S)


def parse_explanation(text: str) -> tuple[str | None, str | None]:
    m = _RE.search(text)
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip()


def make_reader(deps: Deps):
    def reader(state):
        verification = state.get("verification")
        problems = verification["problems"] if verification and not verification["passed"] else None
        attempts = state.get("attempts", 0) + (1 if problems else 0)
        text = deps.llm(reader_prompt(state["intent"], state["question"], state["evidence"], problems)).strip()
        out = {"draft": text, "attempts": attempts, "article_part": None, "simple_explanation": None,
               "trace": ["reader"]}
        if state["intent"] == "explanation":
            out["article_part"], out["simple_explanation"] = parse_explanation(text)
        return out
    return reader
