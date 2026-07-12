"""Detection heuristic tests — pure Python, no OCR binaries required."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdfocr.detect import TextLayerStatus, classify_chars, detect_pdf
from pdfocr.errors import EncryptedPdfError, InvalidPdfError


class TestClassifyThresholds:
    @pytest.mark.parametrize(
        ("avg", "expected"),
        [
            (0.0, TextLayerStatus.NONE),
            (49.9, TextLayerStatus.NONE),
            (50.0, TextLayerStatus.SPARSE),
            (199.9, TextLayerStatus.SPARSE),
            (200.0, TextLayerStatus.FULL),
            (5000.0, TextLayerStatus.FULL),
        ],
    )
    def test_default_boundaries(self, avg: float, expected: TextLayerStatus) -> None:
        assert classify_chars(avg) is expected

    def test_custom_thresholds(self) -> None:
        assert classify_chars(120, min_chars=10, text_threshold=100) is TextLayerStatus.FULL
        assert classify_chars(120, min_chars=150, text_threshold=500) is TextLayerStatus.NONE


class TestDetectPdf:
    def test_text_pdf_is_full(self, text_pdf: Path) -> None:
        result = detect_pdf(text_pdf)
        assert result.status is TextLayerStatus.FULL
        assert result.pages == 2
        assert result.avg_chars_per_page > 200

    def test_sparse_pdf_is_sparse(self, sparse_pdf: Path) -> None:
        result = detect_pdf(sparse_pdf)
        assert result.status is TextLayerStatus.SPARSE

    def test_image_pdf_is_none(self, image_pdf: Path) -> None:
        result = detect_pdf(image_pdf)
        assert result.status is TextLayerStatus.NONE
        assert result.avg_chars_per_page < 50

    def test_blank_pdf_is_none(self, blank_pdf: Path) -> None:
        assert detect_pdf(blank_pdf).status is TextLayerStatus.NONE

    def test_encrypted_pdf_raises(self, encrypted_pdf: Path) -> None:
        with pytest.raises(EncryptedPdfError):
            detect_pdf(encrypted_pdf)

    def test_garbage_file_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"this is not a pdf at all")
        with pytest.raises(InvalidPdfError):
            detect_pdf(bad)

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        with pytest.raises(InvalidPdfError):
            detect_pdf(empty)
