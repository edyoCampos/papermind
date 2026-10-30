import json

import pytest

from scripts import eval_data, run_eval
from scripts.calibrate_threshold import suggest
from scripts.eval_data import EvalDataError

Q = {"id": "q01", "article_id": "a1", "type": "direta", "question": "Qual?", "mode": "auto",
     "expected_status": "answered", "expected_pages": [3]}


def write(tmp_path, data):
    p = tmp_path / "q.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_esquema_valido_e_invalido(tmp_path):
    assert eval_data.load_questions(write(tmp_path, [Q]))[0]["id"] == "q01"
    bad = {k: v for k, v in Q.items() if k != "mode"}
    with pytest.raises(EvalDataError, match="q01.*'mode'"):
        eval_data.load_questions(write(tmp_path, [bad]))
    with pytest.raises(EvalDataError, match="sem_resposta"):
        eval_data.load_questions(write(tmp_path, [{**Q, "type": "sem_resposta"}]))
    with pytest.raises(EvalDataError, match="Crie"):
        eval_data.load_questions(str(tmp_path / "nao-existe.json"))
    (tmp_path / "x.json").write_text("{quebrado")
    with pytest.raises(EvalDataError, match="JSON inválido"):
        eval_data.load_questions(str(tmp_path / "x.json"))


def test_arquivos_do_repositorio_sao_validos():
    assert isinstance(eval_data.load_questions(), list) and isinstance(eval_data.load_articles(), list)


def test_composicao_do_conjunto():
    w = eval_data.check_composition([Q])
    assert any("20" in x for x in w) and any("sem_resposta" in x for x in w) and any("calibration" in x for x in w)


def test_run_one_acerto_de_pagina_e_erro():
    ok = run_eval.run_one(Q, "d", lambda *a: {"status": "answered", "answer": "r [1]", "trace": ["router"],
                                              "citations": [{"page_number": 3}], "max_similarity": 0.7})
    assert run_eval.page_hit(ok) == "sim" and ok["status"] == "answered"

    def boom(*a):
        raise ConnectionError("down")
    err = run_eval.run_one(Q, "d", boom)
    assert err["status"] == "error" and "ConnectionError" in err["answer"]


def test_relatorio_uma_linha_por_pergunta_e_rubrica_vazia():
    rows = [run_eval.run_one(Q, "d", lambda *a: {"status": "insufficient", "message": "m", "trace": ["router"], "citations": []})]
    md = run_eval.build_report(rows, ["aviso x"])
    table = [l for l in md.splitlines() if l.startswith("| q01")]
    assert len(table) == 1 and table[0].endswith("|  |  |  |  |  |")
    assert all(f" C{i} " in md for i in range(1, 6)) and "aviso x" in md and "insufficient × answered" in md


def test_sugestao_de_limiar():
    assert suggest([0.7, 0.8], [0.3, 0.4]) == pytest.approx(0.55)
