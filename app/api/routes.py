"""Rotas: só traduzem HTTP em chamadas de serviço. Sem lógica de negócio."""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile

from app.api.deps import Services, get_services, parse_id
from app.api.schemas import (DocumentCreated, DocumentStatus, QuestionRequest, QuestionResponse,
                             SummaryResponse)
from app.core.config import get_settings
from app.core.errors import (DocumentNotReadyError, FileTooLargeError, InvalidPdfError,
                             ModelUnavailableError, PaperMindError)
from app.ingestion.validation import validate_upload
from app.rag.llm import MODEL_DOWN

log = logging.getLogger(__name__)
router = APIRouter()

SECTION_KEYS = {"objective": "objetivo", "methodology": "metodologia", "results": "resultados",
                "limitations": "limitações", "contribution": "contribuição"}


@router.get("/health")
def health(svc: Services = Depends(get_services)):
    return svc.health()


@router.post("/documents", status_code=202, response_model=DocumentCreated)
async def upload(request: Request, tasks: BackgroundTasks, file: UploadFile,
                 svc: Services = Depends(get_services)):
    s = get_settings()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > (s.max_upload_mb + 1) * 1024 * 1024:
        raise FileTooLargeError(f"O PDF tem mais de {s.max_upload_mb} MB; o limite é {s.max_upload_mb} MB.")
    data = await file.read()
    filename = file.filename or ""
    validate_upload(data, filename, s.max_upload_mb)
    doc_id = svc.register_document(filename)

    def process():  # a falha já fica no status do documento
        try:
            svc.index_document(doc_id, data, filename)
        except PaperMindError:
            pass
        except Exception:  # noqa: BLE001
            log.exception("falha ao indexar %s", doc_id)

    tasks.add_task(process)
    return DocumentCreated(document_id=str(doc_id), filename=filename, status="received")


def _ready_document(svc: Services, document_id: str):
    doc = svc.get_document(parse_id(document_id))
    if doc.status == "error":
        raise DocumentNotReadyError(doc.error_message or "O processamento do documento falhou.")
    if doc.status != "ready":
        raise DocumentNotReadyError(f"O documento ainda está em processamento (status: {doc.status}).")
    return doc


@router.get("/documents/{document_id}", response_model=DocumentStatus)
def status(document_id: str, svc: Services = Depends(get_services)):
    doc_id = parse_id(document_id)
    doc = svc.get_document(doc_id)
    return DocumentStatus(document_id=str(doc.id), filename=doc.filename, status=doc.status,
                          page_count=doc.page_count, chunk_count=svc.count_chunks(doc_id),
                          error_message=doc.error_message)


@router.get("/documents/{document_id}/summary", response_model=SummaryResponse)
def summary(document_id: str, svc: Services = Depends(get_services)):
    _ready_document(svc, document_id)
    result = svc.get_summary(parse_id(document_id))
    if result.get("status") == "error":
        raise ModelUnavailableError(MODEL_DOWN)
    sections = {en: result["summary"][pt] for en, pt in SECTION_KEYS.items()}
    return {"document_id": parse_id(document_id), "sections": sections}


@router.post("/documents/{document_id}/questions", response_model=QuestionResponse)
def question(document_id: str, body: QuestionRequest, svc: Services = Depends(get_services)):
    _ready_document(svc, document_id)
    st = svc.answer_question(parse_id(document_id), body.question, body.mode)
    if st.get("status") == "error":
        raise ModelUnavailableError(st.get("error_message") or MODEL_DOWN)
    return st
