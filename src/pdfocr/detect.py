"""Text-layer detection: measure extractable characters per page and classify."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pypdf import PdfReader

from .errors import EncryptedPdfError, InvalidPdfError

DEFAULT_MIN_CHARS = 50.0
DEFAULT_TEXT_THRESHOLD = 200.0


class TextLayerStatus(str, Enum):
    """Classification of a PDF's extractable text layer."""

    NONE = "none"  # image-only / scanned — OCR recommended
    SPARSE = "sparse"  # partial text layer — OCR fills in the image pages
    FULL = "full"  # real text layer — skip unless forced


@dataclass(frozen=True)
class DetectionResult:
    """Outcome of inspecting one PDF's text layer."""

    path: Path
    pages: int
    total_chars: int
    avg_chars_per_page: float
    status: TextLayerStatus


def classify_chars(
    avg_chars_per_page: float,
    min_chars: float = DEFAULT_MIN_CHARS,
    text_threshold: float = DEFAULT_TEXT_THRESHOLD,
) -> TextLayerStatus:
    """Classify an average chars-per-page figure against the two thresholds."""
    if avg_chars_per_page < min_chars:
        return TextLayerStatus.NONE
    if avg_chars_per_page < text_threshold:
        return TextLayerStatus.SPARSE
    return TextLayerStatus.FULL


def _open_reader(path: Path) -> PdfReader:
    """Open a PDF, translating pypdf failures into pdfocr errors."""
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise InvalidPdfError(f"{path}: cannot read PDF ({exc})") from exc
    if reader.is_encrypted:
        try:
            decrypted = reader.decrypt("")
        except Exception as exc:
            raise EncryptedPdfError(f"{path}: encrypted PDF (password required)") from exc
        if not decrypted:
            raise EncryptedPdfError(f"{path}: encrypted PDF (password required)")
    return reader


def extract_page_texts(path: Path) -> list[str]:
    """Return the extractable text of each page (empty string on a per-page failure)."""
    reader = _open_reader(path)
    texts: list[str] = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            texts.append("")
    return texts


def detect_pdf(
    path: Path,
    min_chars: float = DEFAULT_MIN_CHARS,
    text_threshold: float = DEFAULT_TEXT_THRESHOLD,
) -> DetectionResult:
    """Measure average extractable chars/page and classify the PDF's text layer.

    Raises InvalidPdfError for unreadable/zero-page files and EncryptedPdfError
    for password-protected ones.
    """
    texts = extract_page_texts(path)
    pages = len(texts)
    if pages == 0:
        raise InvalidPdfError(f"{path}: PDF has no pages")
    total = sum(len(t.strip()) for t in texts)
    avg = total / pages
    return DetectionResult(
        path=path,
        pages=pages,
        total_chars=total,
        avg_chars_per_page=avg,
        status=classify_chars(avg, min_chars, text_threshold),
    )
