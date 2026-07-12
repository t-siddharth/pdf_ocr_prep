"""OCR conversion: run ocrmypdf and build the markdown sidecar."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .detect import extract_page_texts
from .errors import ConversionError, PdfocrError

# ocrmypdf's sidecar marker for pages skipped by --skip-text. One marker can
# cover a RANGE of consecutive pages ("[OCR skipped on page(s) 1-2]") with a
# single form feed, so markers must be expanded to keep page alignment.
_SKIPPED_PAGE_RE = re.compile(r"\[OCR skipped on page\(?s?\)?\s*([0-9][0-9,\s-]*)\]")


def _skipped_page_count(spec: str) -> int:
    """Number of pages covered by a marker spec like '3', '1-2', or '1, 4-6'."""
    total = 0
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            total += max(0, int(end) - int(start) + 1)
        else:
            total += 1
    return max(total, 1)

# ocrmypdf ExitCode.already_done_ocr: with --skip-text, every page already has
# text and no output file is written
_EXIT_ALREADY_HAS_TEXT = 6

_PAGE_SEPARATOR = "\n\n---\n\n"


def sidecar_to_markdown(
    sidecar_text: str, fallback_pages: list[str] | None = None
) -> str:
    """Convert ocrmypdf sidecar text (form-feed page breaks) into markdown.

    Pages the OCR pass skipped (they already had a text layer) come through as
    `[OCR skipped on page N]` placeholders; those are replaced with the
    corresponding entry from fallback_pages when available.

    When fallback_pages is given, its length is treated as the true page count
    and the output always has exactly that many sections — a trailing blank
    scanned page must still get its `---` section, or the markdown no longer
    maps one-to-one onto the document.
    """
    pages: list[str | None] = []
    for chunk in sidecar_text.split("\f"):
        marker = _SKIPPED_PAGE_RE.fullmatch(chunk.strip())
        if marker:
            pages.extend([None] * _skipped_page_count(marker.group(1)))
        else:
            pages.append(chunk)
    if fallback_pages is None:
        if pages and not (pages[-1] or "").strip():
            pages = pages[:-1]
    else:
        while len(pages) > len(fallback_pages) and not (pages[-1] or "").strip():
            pages = pages[:-1]
        while len(pages) < len(fallback_pages):
            pages.append(None)
    sections: list[str] = []
    for i, page in enumerate(pages):
        text = (page or "").strip()
        if not text or _SKIPPED_PAGE_RE.search(text):
            fallback = ""
            if fallback_pages is not None and i < len(fallback_pages):
                fallback = fallback_pages[i].strip()
            text = fallback if fallback else _SKIPPED_PAGE_RE.sub("", text).strip()
        sections.append(text)
    return _PAGE_SEPARATOR.join(sections) + "\n"


def convert_pdf(pdf: Path, out_pdf: Path, out_md: Path, lang: str = "eng") -> None:
    """OCR one PDF into out_pdf and write the markdown sidecar to out_md.

    The original file is never modified. Raises ConversionError on failure.
    """
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    try:
        fallback_pages: list[str] | None = extract_page_texts(pdf)
    except PdfocrError:
        fallback_pages = None
    with tempfile.TemporaryDirectory(prefix="pdfocr-") as tmp:
        sidecar = Path(tmp) / "sidecar.txt"
        cmd = [
            "ocrmypdf",
            "--skip-text",
            "--sidecar",
            str(sidecar),
            "--language",
            lang,
            str(pdf),
            str(out_pdf),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == _EXIT_ALREADY_HAS_TEXT:
            # Every page already has text (reachable under --force): pass the
            # PDF through unchanged and build markdown from the existing layer.
            shutil.copyfile(pdf, out_pdf)
            pages = fallback_pages or []
            out_md.write_text(
                _PAGE_SEPARATOR.join(t.strip() for t in pages) + "\n",
                encoding="utf-8",
            )
            return
        if proc.returncode != 0:
            tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
            raise ConversionError(
                f"{pdf}: ocrmypdf failed (exit {proc.returncode})\n{tail}"
            )
        sidecar_text = (
            sidecar.read_text(encoding="utf-8", errors="replace")
            if sidecar.exists()
            else ""
        )
    out_md.write_text(sidecar_to_markdown(sidecar_text, fallback_pages), encoding="utf-8")
