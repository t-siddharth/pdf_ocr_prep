"""CLI behavior tests — dry-run based, no OCR binaries required."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pdfocr import __version__
from pdfocr.cli import EXIT_FAILURES, EXIT_MISSING_DEP, EXIT_OK, EXIT_USAGE, main


@pytest.fixture()
def work_dir(tmp_path: Path, text_pdf: Path, image_pdf: Path) -> Path:
    """A mutable folder holding one already-searchable and one scanned PDF."""
    shutil.copyfile(text_pdf, tmp_path / "text.pdf")
    shutil.copyfile(image_pdf, tmp_path / "image.pdf")
    return tmp_path


class TestDryRun:
    def test_folder_classification(self, work_dir: Path, capsys) -> None:
        assert main([str(work_dir), "--dry-run"]) == EXIT_OK
        out = capsys.readouterr().out
        assert "image.pdf: would OCR" in out
        assert "text.pdf: skipped (has text layer" in out
        assert "1 processed, 1 skipped, 0 failed (dry run)" in out

    def test_force_includes_text_pdf(self, work_dir: Path, capsys) -> None:
        assert main([str(work_dir), "--dry-run", "--force"]) == EXIT_OK
        out = capsys.readouterr().out
        assert "text.pdf: would OCR" in out

    def test_existing_output_skipped(self, work_dir: Path, capsys) -> None:
        (work_dir / "image-searchable.pdf").write_bytes(b"%PDF-1.4")
        assert main([str(work_dir), "--dry-run"]) == EXIT_OK
        out = capsys.readouterr().out
        assert "image.pdf: skipped (output already exists" in out

    def test_threshold_override(self, work_dir: Path, sparse_pdf: Path, capsys) -> None:
        shutil.copyfile(sparse_pdf, work_dir / "sparse.pdf")
        assert main([str(work_dir), "--dry-run", "--text-threshold", "90"]) == EXIT_OK
        out = capsys.readouterr().out
        assert "sparse.pdf: skipped (has text layer" in out

    def test_works_without_ocrmypdf(self, work_dir: Path, monkeypatch) -> None:
        monkeypatch.setattr("pdfocr.deps.shutil.which", lambda _: None)
        assert main([str(work_dir), "--dry-run"]) == EXIT_OK

    def test_quiet_suppresses_output(self, work_dir: Path, capsys) -> None:
        assert main([str(work_dir), "--dry-run", "--quiet"]) == EXIT_OK
        assert capsys.readouterr().out == ""


class TestJsonOutput:
    def test_schema_and_stream_separation(self, work_dir: Path, capsys) -> None:
        assert main([str(work_dir), "--dry-run", "--json"]) == EXIT_OK
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["version"] == __version__
        assert payload["dry_run"] is True
        assert payload["summary"] == {
            "processed": 1,
            "skipped": 1,
            "failed": 0,
            "verification_failed": 0,
            "total": 2,
        }
        actions = {Path(r["input"]).name: r["action"] for r in payload["results"]}
        assert actions == {"image.pdf": "would_process", "text.pdf": "skipped"}
        processed = next(r for r in payload["results"] if r["action"] == "would_process")
        assert processed["outputs"]["pdf"].endswith("image-searchable.pdf")
        assert processed["outputs"]["markdown"].endswith("image.md")


class TestErrors:
    def test_nonexistent_path(self, tmp_path: Path, capsys) -> None:
        assert main([str(tmp_path / "nope.pdf")]) == EXIT_USAGE
        assert "does not exist" in capsys.readouterr().err

    def test_non_pdf_input(self, tmp_path: Path, capsys) -> None:
        txt = tmp_path / "notes.txt"
        txt.write_text("hello")
        assert main([str(txt)]) == EXIT_USAGE
        assert "not a PDF" in capsys.readouterr().err

    def test_bad_thresholds(self, tmp_path: Path) -> None:
        assert main([str(tmp_path), "--min-chars", "500", "--text-threshold", "100"]) == EXIT_USAGE

    def test_missing_ocrmypdf(self, work_dir: Path, monkeypatch, capsys) -> None:
        monkeypatch.setattr("pdfocr.deps.shutil.which", lambda _: None)
        assert main([str(work_dir)]) == EXIT_MISSING_DEP
        assert "ocrmypdf not found" in capsys.readouterr().err

    def test_corrupt_pdf_counts_as_failed(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        monkeypatch.setattr("pdfocr.deps.check_ocrmypdf", lambda: "ocrmypdf")
        assert main([str(bad)]) == EXIT_FAILURES
        assert "FAILED" in capsys.readouterr().err

    def test_encrypted_pdf_counts_as_failed(
        self, tmp_path: Path, encrypted_pdf: Path, monkeypatch, capsys
    ) -> None:
        target = tmp_path / "locked.pdf"
        shutil.copyfile(encrypted_pdf, target)
        monkeypatch.setattr("pdfocr.deps.check_ocrmypdf", lambda: "ocrmypdf")
        assert main([str(target)]) == EXIT_FAILURES
        assert "encrypted" in capsys.readouterr().err


class TestVersion:
    def test_version_flag(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        assert f"pdfocr {__version__}" in capsys.readouterr().out
