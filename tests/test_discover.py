"""Input discovery and output-path tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdfocr.discover import find_pdfs, output_locations


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    """A folder tree with mixed names, cases, and a pdfocr output to ignore."""
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "B.PDF").write_bytes(b"%PDF-1.4")
    (tmp_path / "with space.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "notes.txt").write_text("not a pdf")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.pdf").write_bytes(b"%PDF-1.4")
    (sub / "c-searchable.pdf").write_bytes(b"%PDF-1.4")
    return tmp_path


class TestFindPdfs:
    def test_recursive_finds_all_but_own_outputs(self, tree: Path) -> None:
        names = [p.name for p in find_pdfs(tree, recursive=True)]
        assert sorted(names) == ["B.PDF", "a.pdf", "c.pdf", "with space.pdf"]
        assert "c-searchable.pdf" not in names

    def test_non_recursive_stays_top_level(self, tree: Path) -> None:
        names = [p.name for p in find_pdfs(tree, recursive=False)]
        assert sorted(names) == ["B.PDF", "a.pdf", "with space.pdf"]

    def test_single_file(self, tree: Path) -> None:
        assert find_pdfs(tree / "a.pdf") == [tree / "a.pdf"]

    def test_single_file_uppercase_extension(self, tree: Path) -> None:
        assert find_pdfs(tree / "B.PDF") == [tree / "B.PDF"]

    def test_nonexistent_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            find_pdfs(tmp_path / "missing.pdf")

    def test_non_pdf_file_raises(self, tree: Path) -> None:
        with pytest.raises(ValueError):
            find_pdfs(tree / "notes.txt")


class TestOutputLocations:
    def test_default_alongside_input(self, tree: Path) -> None:
        pdf = tree / "sub" / "c.pdf"
        out_pdf, out_md = output_locations(pdf, tree, None)
        assert out_pdf == tree / "sub" / "c-searchable.pdf"
        assert out_md == tree / "sub" / "c.md"

    def test_output_dir_mirrors_structure(self, tree: Path, tmp_path_factory) -> None:
        out_dir = tmp_path_factory.mktemp("out")
        pdf = tree / "sub" / "c.pdf"
        out_pdf, out_md = output_locations(pdf, tree, out_dir)
        assert out_pdf == out_dir / "sub" / "c-searchable.pdf"
        assert out_md == out_dir / "sub" / "c.md"

    def test_uppercase_extension_stripped(self, tree: Path) -> None:
        out_pdf, out_md = output_locations(tree / "B.PDF", tree, None)
        assert out_pdf.name == "B-searchable.pdf"
        assert out_md.name == "B.md"

    def test_single_file_with_output_dir(self, tree: Path, tmp_path_factory) -> None:
        out_dir = tmp_path_factory.mktemp("out2")
        pdf = tree / "a.pdf"
        out_pdf, _ = output_locations(pdf, pdf, out_dir)
        assert out_pdf == out_dir / "a-searchable.pdf"
