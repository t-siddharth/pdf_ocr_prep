"""Verification (--verify) tests: the tool must detect tampered/broken outputs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pdfocr.cli import EXIT_FAILURES, EXIT_OK, main
from pdfocr.convert import sidecar_to_markdown
from pdfocr.verify import verify_conversion

HAS_OCR_STACK = bool(shutil.which("ocrmypdf")) and bool(shutil.which("tesseract"))


class TestSidecarPageAlignment:
    """Markdown must have exactly one section per document page."""

    def test_trailing_blank_page_keeps_its_section(self) -> None:
        # sidecar for a 2-page doc whose second page is blank
        result = sidecar_to_markdown("one\f\f", ["", ""])
        assert result.removesuffix("\n").split("\n\n---\n\n") == ["one", ""]

    def test_short_sidecar_padded_to_page_count(self) -> None:
        result = sidecar_to_markdown("one", ["", "text layer two"])
        assert result == "one\n\n---\n\ntext layer two\n"


class TestVerificationCatchesTampering:
    """Verification runs without OCR binaries when outputs are hand-built."""

    def test_wrong_markdown_fails_text_agreement(
        self, tmp_path: Path, text_pdf: Path
    ) -> None:
        src = tmp_path / "doc.pdf"
        out_pdf = tmp_path / "doc-searchable.pdf"
        shutil.copyfile(text_pdf, src)
        shutil.copyfile(text_pdf, out_pdf)  # structurally valid "conversion"
        out_md = tmp_path / "doc.md"
        out_md.write_text("completely unrelated text\n\n---\n\nmore wrong text\n")
        report = verify_conversion(src, out_pdf, out_md)
        assert not report.ok
        assert any(
            c.name == "text_agreement" and c.status == "failed" for c in report.checks
        )

    def test_truncated_output_fails_page_count(
        self, tmp_path: Path, text_pdf: Path
    ) -> None:
        from pypdf import PdfReader, PdfWriter

        src = tmp_path / "doc.pdf"
        shutil.copyfile(text_pdf, src)
        out_pdf = tmp_path / "doc-searchable.pdf"
        writer = PdfWriter()
        writer.add_page(PdfReader(str(src)).pages[0])  # drop page 2
        with out_pdf.open("wb") as fh:
            writer.write(fh)
        out_md = tmp_path / "doc.md"
        out_md.write_text("anything\n")
        report = verify_conversion(src, out_pdf, out_md)
        assert not report.ok
        assert any(
            c.name == "page_count" and c.status == "failed" for c in report.checks
        )

    def test_cli_exit_code_on_verification_failure(
        self, tmp_path: Path, image_pdf: Path, monkeypatch, capsys
    ) -> None:
        src = tmp_path / "scan.pdf"
        shutil.copyfile(image_pdf, src)

        def fake_convert(pdf: Path, out_pdf: Path, out_md: Path, lang: str) -> None:
            shutil.copyfile(pdf, out_pdf)
            out_md.write_text("text that matches no text layer at all\n")

        monkeypatch.setattr("pdfocr.convert.convert_pdf", fake_convert)
        monkeypatch.setattr("pdfocr.deps.check_ocrmypdf", lambda: "ocrmypdf")
        assert main([str(src), "--verify"]) == EXIT_FAILURES
        assert "verification FAILED" in capsys.readouterr().err


@pytest.mark.skipif(not HAS_OCR_STACK, reason="ocrmypdf/tesseract not installed")
class TestVerifyRealConversions:
    def test_verified_conversion_passes(
        self, tmp_path: Path, image_pdf2: Path, capsys
    ) -> None:
        src = tmp_path / "scan.pdf"
        shutil.copyfile(image_pdf2, src)
        assert main([str(src), "--verify", "--json"]) == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        verification = payload["results"][0]["verification"]
        assert verification["ok"] is True
        statuses = {c["name"]: c["status"] for c in verification["checks"]}
        assert statuses["page_count"] == "passed"
        assert statuses["markdown_pages"] == "passed"
        assert statuses["text_agreement"] == "passed"
        assert statuses["visual_equivalence"] in ("passed", "skipped")
        assert payload["summary"]["verification_failed"] == 0

    def test_human_output_marks_verified(
        self, tmp_path: Path, image_pdf: Path, capsys
    ) -> None:
        src = tmp_path / "scan.pdf"
        shutil.copyfile(image_pdf, src)
        assert main([str(src), "--verify"]) == EXIT_OK
        assert "[verified]" in capsys.readouterr().out
