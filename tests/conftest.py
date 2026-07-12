"""Synthetic PDF fixtures — generated at test time, no binaries committed."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


def make_text_pdf(path: Path, pages: int = 2, chars_per_page: int = 600) -> Path:
    """A PDF with a real text layer of roughly chars_per_page per page."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    filler = ("lorem ipsum dolor sit amet consectetur adipiscing elit " * 40)[
        :chars_per_page
    ]
    for _ in range(pages):
        text = c.beginText(72, 720)
        for line in textwrap.wrap(filler, 80):
            text.textLine(line)
        c.drawText(text)
        c.showPage()
    c.save()
    return path


def make_image_pdf(path: Path, messages: tuple[str, ...] = ("HELLO SCANNED WORLD",)) -> Path:
    """An image-only PDF (no text layer), one page of large text per message."""
    import img2pdf
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default(size=72)
    pngs: list[Path] = []
    for i, message in enumerate(messages):
        img = Image.new("RGB", (1600, 800), "white")
        ImageDraw.Draw(img).text((100, 300), message, fill="black", font=font)
        png = path.with_suffix(f".{i}.png")
        img.save(png)
        pngs.append(png)
    path.write_bytes(img2pdf.convert([str(p) for p in pngs]))
    for png in pngs:
        png.unlink()
    return path


def make_blank_pdf(path: Path) -> Path:
    """A valid one-page PDF with no content at all."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def make_encrypted_pdf(path: Path, source: Path) -> Path:
    """A password-protected copy of an existing PDF."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    writer.append(PdfReader(str(source)))
    writer.encrypt("secret")
    with path.open("wb") as fh:
        writer.write(fh)
    return path


@pytest.fixture(scope="session")
def fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped directory of pristine source PDFs. Tests copy, never mutate."""
    d = tmp_path_factory.mktemp("source-pdfs")
    make_text_pdf(d / "text.pdf")
    make_text_pdf(d / "sparse.pdf", chars_per_page=100)
    make_image_pdf(d / "image.pdf")
    make_image_pdf(d / "image2.pdf", ("PAGE ONE ALPHA", "PAGE TWO BRAVO"))
    make_blank_pdf(d / "blank.pdf")
    make_encrypted_pdf(d / "encrypted.pdf", d / "text.pdf")
    return d


@pytest.fixture()
def text_pdf(fixture_dir: Path) -> Path:
    return fixture_dir / "text.pdf"


@pytest.fixture()
def sparse_pdf(fixture_dir: Path) -> Path:
    return fixture_dir / "sparse.pdf"


@pytest.fixture()
def image_pdf(fixture_dir: Path) -> Path:
    return fixture_dir / "image.pdf"


@pytest.fixture()
def image_pdf2(fixture_dir: Path) -> Path:
    return fixture_dir / "image2.pdf"


@pytest.fixture()
def blank_pdf(fixture_dir: Path) -> Path:
    return fixture_dir / "blank.pdf"


@pytest.fixture()
def encrypted_pdf(fixture_dir: Path) -> Path:
    return fixture_dir / "encrypted.pdf"
