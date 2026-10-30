"""Formatação pura (sem Streamlit) dos dados da API."""
STATUS_LABELS = {"received": "Recebido", "extracting": "Extraindo texto", "indexing": "Indexando",
                 "ready": "Pronto", "error": "Erro"}
MODES = {"Automático": "auto", "Pergunta sobre o artigo": "factual", "Explicar termo": "explanation"}
SECTION_TITLES = {"objective": "Objetivo", "methodology": "Metodologia", "results": "Resultados",
                  "limitations": "Limitações", "contribution": "Contribuição"}
CACHE_BADGES = {"hit": "HIT", "miss": "MISS", "disabled": "cache desligado", "unavailable": "cache indisponível"}
SIMPLE_LABEL = "Explicação simplificada — gerada pelo modelo, não é afirmação do artigo"


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def cache_badge(cache_status: str) -> str:
    return CACHE_BADGES.get(cache_status, cache_status)


def source_lines(citations: list[dict]) -> list[str]:
    return [f'[{c["ref"]}] Página {c["page_number"]} — "{c["excerpt"].strip()[:200]}…"' for c in citations]


def nearest_lines(items: list[dict]) -> list[str]:
    return [f'Página {n["page_number"]} — "{n["excerpt"].strip()[:160]}…"' for n in items]


def trace_text(trace: list[str]) -> str:
    return " → ".join(trace)
