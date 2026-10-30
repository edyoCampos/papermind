"""Interface do PaperMind: fala só com a API (httpx)."""
import os
import time

import streamlit as st

import api_client as api
import view

API_URL = os.environ.get("API_URL", "http://app:8000")
POLL_SECONDS, POLL_MAX = 2, 600

st.set_page_config(page_title="PaperMind")
st.title("PaperMind")
ss = st.session_state
for key, default in (("document_id", None), ("doc_status", None), ("summary", None), ("messages", []),
                     ("file_id", None), ("poll_started", None), ("doc_error", None), ("page_count", None)):
    ss.setdefault(key, default)


def render_answer(p: dict) -> None:
    if p["status"] == "insufficient":
        st.warning(p["message"])
        if p.get("nearest_excerpts"):
            st.caption("Trechos mais próximos encontrados (não sustentam uma resposta):")
            for line in view.nearest_lines(p["nearest_excerpts"]):
                st.markdown(f"- {line}")
    elif p["intent"] == "explanation":
        st.markdown("**No artigo**")
        st.markdown(p["article_part"])
        st.info(f"**{view.SIMPLE_LABEL}**\n\n{p['simple_explanation']}")
    else:
        st.markdown(p["answer"])
    if p["status"] == "answered" and p["citations"]:
        st.markdown("**Fontes**")
        for line in view.source_lines(p["citations"]):
            st.markdown(f"- {line}")
    st.caption(f"{view.cache_badge(p['cache_status'])} · {p.get('elapsed', 0):.1f} s")
    with st.expander("Caminho no grafo"):
        st.write(view.trace_text(p["trace"]))


def show_error(exc: api.ApiError) -> None:
    st.error(str(exc))


# 1. Upload
uploaded = st.file_uploader("Envie um artigo científico em PDF", type=["pdf"])
if uploaded is not None and uploaded.file_id != ss.file_id:
    ss.update(file_id=uploaded.file_id, summary=None, messages=[], doc_error=None, page_count=None)
    try:
        ss.document_id = api.upload(API_URL, uploaded.name, uploaded.getvalue())["document_id"]
        ss.doc_status, ss.poll_started = "received", time.time()
    except api.ApiError as exc:
        ss.document_id = ss.doc_status = None
        show_error(exc)

if ss.document_id is None:
    st.info("Envie um artigo científico em PDF para começar.")

# 2. Status
if ss.document_id and ss.doc_status not in ("ready", "error"):
    try:
        s = api.get_status(API_URL, ss.document_id)
        ss.doc_status, ss.doc_error, ss.page_count = s["status"], s["error_message"], s["page_count"]
    except api.ApiError as exc:
        show_error(exc)
    if ss.doc_status not in ("ready", "error"):
        if time.time() - ss.poll_started > POLL_MAX:
            st.error("O processamento não terminou. Reenvie o PDF.")
        else:
            with st.status(view.status_label(ss.doc_status), state="running"):
                st.write("Isso pode levar alguns minutos em CPU.")
            time.sleep(POLL_SECONDS)
            st.rerun()
if ss.doc_status == "error":
    st.error(ss.doc_error or "O processamento falhou.")
elif ss.doc_status == "ready":
    st.success(f"Pronto · {ss.page_count} página(s)")

ready = ss.doc_status == "ready"

# 3. Resumo
if ready:
    if st.button("Gerar resumo"):
        try:
            with st.spinner("Gerando o resumo; em CPU isso pode levar até 5 minutos."):
                ss.summary = api.get_summary(API_URL, ss.document_id)["sections"]
        except api.ApiError as exc:
            show_error(exc)
    if ss.summary:
        for key, title in view.SECTION_TITLES.items():
            sec = ss.summary[key]
            st.subheader(title)
            if sec["status"] == "not_found":
                st.markdown(f":gray[{'Não encontrado no artigo'}]")
            else:
                st.markdown(sec["text"])
                for line in view.source_lines(sec["citations"]):
                    st.caption(line)

# 4. Chat
mode_label = st.radio("Modo", list(view.MODES), horizontal=True)
for m in ss.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["payload"]["text"]) if m["role"] == "user" else render_answer(m["payload"])
if not ready and ss.document_id:
    st.caption("Aguarde o processamento terminar.")
question = st.chat_input("Pergunte sobre o artigo", disabled=not ready)
if question:
    ss.messages.append({"role": "user", "payload": {"text": question}})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            t0 = time.time()
            with st.spinner("Pensando…"):
                payload = api.ask(API_URL, ss.document_id, question, view.MODES[mode_label])
            payload["elapsed"] = time.time() - t0
            ss.messages.append({"role": "assistant", "payload": payload})
            render_answer(payload)
        except api.ApiError as exc:
            show_error(exc)
