"""Markdown-sidecar construction and real-OCR integration tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pdfocr.cli import EXIT_OK, main
from pdfocr.convert import sidecar_to_markdown

HAS_OCR_STACK = bool(shutil.which("ocrmypdf")) and bool(shutil.which("tesseract"))


class TestSidecarToMarkdown:
    def test_form_feed_splits_pages(self) -> None:
        assert sidecar_to_markdown("page one\fpage two\f") == "page one\n\n---\n\npage two\n"

    def test_single_page(self) -> None:
        assert sidecar_to_markdown("only page") == "only page\n"

    def test_skipped_page_uses_fallback_text(self) -> None:
        sidecar = "[OCR skipped on page 1]\focr text"
        result = sidecar_to_markdown(sidecar, ["existing text layer", ""])
        assert result == "existing text layer\n\n---\n\nocr text\n"

    def test_skipped_page_without_fallback_is_blank(self) -> None:
        result = sidecar_to_markdown("[OCR skipped on page 1]\focr text")
        assert result == "\n\n---\n\nocr text\n"

    def test_blank_page_uses_fallback(self) -> None:
        assert sidecar_to_markdown("\ftwo", ["one", ""]) == "one\n\n---\n\ntwo\n"

    def test_range_marker_expands_to_multiple_pages(self) -> None:
        # ocrmypdf coalesces consecutive skipped pages into one marker
        sidecar = "[OCR skipped on page(s) 1-2]\focr text"
        result = sidecar_to_markdown(sidecar, ["alpha", "bravo", ""])
        assert result == "alpha\n\n---\n\nbravo\n\n---\n\nocr text\n"


@pytest.mark.skipif(not HAS_OCR_STACK, reason="ocrmypdf/tesseract not installed")
class TestRealOcr:
    def test_end_to_end_image_pdf(self, tmp_path: Path, image_pdf: Path, capsys) -> None:
        source = tmp_path / "scan with space.pdf"
        shutil.copyfile(image_pdf, source)
        original_bytes = source.read_bytes()

        assert main([str(source)]) == EXIT_OK

        out_pdf = tmp_path / "scan with space-searchable.pdf"
        out_md = tmp_path / "scan with space.md"
        assert out_pdf.exists() and out_md.exists()
        md_normalized = " ".join(out_md.read_text().lower().split())
        assert "hello scanned world" in md_normalized
        # original untouched, and no undocumented intermediates left behind
        assert source.read_bytes() == original_bytes
        assert list(tmp_path.glob("*.txt")) == []
        assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
            [source.name, out_pdf.name, out_md.name]
        )

    def test_searchable_output_has_text_layer(self, tmp_path: Path, image_pdf: Path) -> None:
        from pdfocr.detect import detect_pdf

        source = tmp_path / "scan.pdf"
        shutil.copyfile(image_pdf, source)
        assert main([str(source), "--quiet"]) == EXIT_OK
        result = detect_pdf(tmp_path / "scan-searchable.pdf")
        assert result.avg_chars_per_page > 0

    def test_force_on_full_text_pdf(self, tmp_path: Path, text_pdf: Path) -> None:
        source = tmp_path / "text.pdf"
        shutil.copyfile(text_pdf, source)
        assert main([str(source), "--force", "--quiet"]) == EXIT_OK
        out_md = tmp_path / "text.md"
        assert out_md.exists()
        md = out_md.read_text().lower()
        assert "lorem ipsum" in md
        assert "ocr skipped" not in md

    def test_multipage_order_and_section_count(
        self, tmp_path: Path, image_pdf2: Path
    ) -> None:
        source = tmp_path / "scan.pdf"
        shutil.copyfile(image_pdf2, source)
        assert main([str(source), "--quiet"]) == EXIT_OK
        md = (tmp_path / "scan.md").read_text()
        sections = md.rstrip("\n").split("\n\n---\n\n")
        assert len(sections) == 2
        assert "alpha" in sections[0].lower()
        assert "bravo" in sections[1].lower()

    def test_mixed_text_and_image_pages(
        self, tmp_path: Path, text_pdf: Path, image_pdf: Path
    ) -> None:
        """A PDF with 2 text pages + 1 scanned page: fallback text for the
        skipped pages, OCR for the image page, one section per page.

        The average lands above --text-threshold (the documented limitation
        of averaging), so --force is required — this is that workflow."""
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter()
        writer.append(PdfReader(str(text_pdf)))
        writer.append(PdfReader(str(image_pdf)))
        source = tmp_path / "mixed.pdf"
        with source.open("wb") as fh:
            writer.write(fh)

        assert main([str(source), "--force", "--quiet"]) == EXIT_OK
        md = (tmp_path / "mixed.md").read_text()
        sections = md.rstrip("\n").split("\n\n---\n\n")
        assert len(sections) == 3
        assert "lorem ipsum" in sections[0].lower()
        assert "lorem ipsum" in sections[1].lower()
        assert "hello" in sections[2].lower()
        assert "ocr skipped" not in md.lower()

    def test_output_dir_mirrors_tree(self, tmp_path: Path, image_pdf: Path) -> None:
        src = tmp_path / "in" / "sub"
        src.mkdir(parents=True)
        shutil.copyfile(image_pdf, src / "scan.pdf")
        out = tmp_path / "out"
        assert main([str(tmp_path / "in"), "-o", str(out), "--quiet"]) == EXIT_OK
        assert (out / "sub" / "scan-searchable.pdf").exists()
        assert (out / "sub" / "scan.md").exists()
