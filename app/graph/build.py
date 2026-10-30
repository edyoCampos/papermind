"""Monta o grafo do PaperMind. O desenho está em docs/architecture.md."""
from langgraph.graph import END, START, StateGraph

from app.agents.common import Deps, safe
from app.agents.finalize import finalize, insufficient
from app.agents.reader import make_reader
from app.agents.researcher import evidence_gate, make_researcher
from app.agents.router import route_after_router, router_node
from app.agents.summarizer import make_summarizer
from app.agents.verifier import make_verifier, verification_gate
from app.graph.state import PaperState


def _stop_on_error(next_node: str):
    return lambda state: "end" if state.get("status") == "error" else next_node


def build_graph(deps: Deps):
    g = StateGraph(PaperState)
    g.add_node("router", router_node)
    g.add_node("researcher", safe("researcher", make_researcher(deps)))
    g.add_node("reader", safe("reader", make_reader(deps)))
    g.add_node("verifier", safe("verifier", make_verifier(deps)))
    g.add_node("summarizer", safe("summarizer", make_summarizer(deps)))
    g.add_node("finalize", finalize)
    g.add_node("insufficient", insufficient)

    g.add_edge(START, "router")
    # Decisão 1: roteamento por intenção
    g.add_conditional_edges("router", route_after_router, {"summarizer": "summarizer", "researcher": "researcher"})
    g.add_edge("summarizer", END)
    # Decisão 2: interrupção segura sem LLM
    g.add_conditional_edges("researcher", evidence_gate,
                            {"reader": "reader", "insufficient": "insufficient", "end": END})
    g.add_conditional_edges("reader", _stop_on_error("verifier"), {"verifier": "verifier", "end": END})
    # Decisão 3: verificação com no máximo 1 reformulação
    g.add_conditional_edges("verifier", verification_gate,
                            {"finalize": "finalize", "reader": "reader", "insufficient": "insufficient", "end": END})
    g.add_edge("finalize", END)
    g.add_edge("insufficient", END)
    return g.compile()
