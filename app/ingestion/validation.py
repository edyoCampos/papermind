from app.core.errors import FileTooLargeError, InvalidPdfError


def validate_upload(data: bytes, filename: str, max_upload_mb: int) -> None:
    """Valida tamanho, extensão e assinatura, antes de qualquer parsing."""
    if len(data) > max_upload_mb * 1024 * 1024:
        mb = len(data) / (1024 * 1024)
        raise FileTooLargeError(f"O PDF tem {mb:.1f} MB; o limite é {max_upload_mb} MB.")
    if not filename.lower().endswith(".pdf") or not data.startswith(b"%PDF-"):
        raise InvalidPdfError()
