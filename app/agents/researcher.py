from app.agents.common import Deps


def make_researcher(deps: Deps):
    def researcher(state):
        r = deps.retrieve(state["document_id"], state["question"])
        return {"evidence": r.evidence, "relevant": r.relevant, "max_similarity": r.max_similarity,
                "nearest": r.candidates[:2], "trace": ["researcher"]}
    return researcher


def evidence_gate(state) -> str:
    if state.get("status") == "error":
        return "end"
    return "reader" if state["relevant"] else "insufficient"
