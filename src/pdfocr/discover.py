"""Input discovery and output-path computation."""

from __future__ import annotations

from pathlib import Path

_OUTPUT_MARKER = "-searchable"


def is_own_output(path: Path) -> bool:
    """True if the file looks like a pdfocr-generated searchable PDF."""
    return path.stem.lower().endswith(_OUTPUT_MARKER)


def find_pdfs(root: Path, recursive: bool = True) -> list[Path]:
    """Resolve an input path to the list of PDFs to consider.

    A single file is returned as-is (must have a .pdf extension, any case).
    A directory is scanned — recursively by default — excluding files that are
    themselves pdfocr outputs (`*-searchable.pdf`).
    """
    if not root.exists():
        raise FileNotFoundError(f"path does not exist: {root}")
    if root.is_file():
        if root.suffix.lower() != ".pdf":
            raise ValueError(f"not a PDF file: {root}")
        return [root]
    candidates = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        p
        for p in candidates
        if p.is_file() and p.suffix.lower() == ".pdf" and not is_own_output(p)
    )


def output_locations(
    pdf: Path, input_root: Path, output_dir: Path | None
) -> tuple[Path, Path]:
    """Return (searchable_pdf, markdown) paths for one input PDF.

    Defaults to alongside the input. With --output-dir and a directory input,
    the input's subdirectory structure is mirrored so same-named PDFs in
    different subfolders don't collide.
    """
    if output_dir is None:
        base = pdf.parent
    elif input_root.is_dir():
        base = output_dir / pdf.parent.relative_to(input_root)
    else:
        base = output_dir
    return base / f"{pdf.stem}{_OUTPUT_MARKER}.pdf", base / f"{pdf.stem}.md"
