"""Post-conversion integrity verification.

Checks the provable properties of a conversion: page counts, agreement
between the markdown sidecar and the text layer embedded in the searchable
PDF, and visual equivalence of rendered pages. It cannot prove OCR accuracy
against the page image — no ground truth exists for a scan.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .detect import extract_page_texts
from .errors import PdfocrError

_SIMILARITY_THRESHOLD = 0.75
_PIXEL_DIFF_THRESHOLD = 12.0  # mean absolute gray-level difference, 0-255 scale
_RASTER_DPI = 30
_PAGE_SEPARATOR = "\n\n---\n\n"


@dataclass(frozen=True)
class Check:
    """One verification check and its outcome."""

    name: str
    status: str  # passed | failed | skipped
    detail: str = ""


@dataclass(frozen=True)
class VerificationReport:
    """Aggregate outcome of all checks for one conversion."""

    ok: bool
    checks: tuple[Check, ...]

    def failure_summary(self) -> str:
        return "; ".join(
            f"{c.name}: {c.detail}" if c.detail else c.name
            for c in self.checks
            if c.status == "failed"
        )

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail}
                for c in self.checks
            ],
        }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_conversion(src: Path, out_pdf: Path, out_md: Path) -> VerificationReport:
    """Run all integrity checks for one completed conversion."""
    checks: list[Check] = []
    try:
        src_texts = extract_page_texts(src)
        out_texts = extract_page_texts(out_pdf)
    except PdfocrError as exc:
        checks.append(Check("readable", "failed", str(exc)))
        return VerificationReport(False, tuple(checks))
    checks.append(Check("readable", "passed"))

    pages_match = len(src_texts) == len(out_texts)
    checks.append(
        Check(
            "page_count",
            "passed" if pages_match else "failed",
            f"{len(src_texts)} pages"
            if pages_match
            else f"input has {len(src_texts)} pages, output has {len(out_texts)}",
        )
    )

    # strip exactly the one final newline: rstrip("\n") would eat the page
    # separator itself when the last page is blank
    md_text = out_md.read_text(encoding="utf-8").removesuffix("\n")
    md_sections = md_text.split(_PAGE_SEPARATOR)
    sections_match = len(md_sections) == len(src_texts)
    checks.append(
        Check(
            "markdown_pages",
            "passed" if sections_match else "failed",
            f"{len(md_sections)} sections"
            if sections_match
            else f"markdown has {len(md_sections)} sections for {len(src_texts)} pages",
        )
    )

    if pages_match and sections_match:
        low: list[str] = []
        for i, (section, page_text) in enumerate(zip(md_sections, out_texts), 1):
            a, b = _normalize(section), _normalize(page_text)
            if not a and not b:
                continue
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio < _SIMILARITY_THRESHOLD:
                low.append(f"page {i} similarity {ratio:.2f}")
        checks.append(
            Check(
                "text_agreement",
                "failed" if low else "passed",
                ", ".join(low) if low else "markdown matches embedded text layer",
            )
        )
    else:
        checks.append(Check("text_agreement", "skipped", "page counts disagree"))

    checks.append(_visual_check(src, out_pdf))

    ok = all(c.status != "failed" for c in checks)
    return VerificationReport(ok, tuple(checks))


def _visual_check(src: Path, out_pdf: Path) -> Check:
    """Rasterize both PDFs at low resolution and compare pages pixel-wise."""
    if shutil.which("pdftoppm") is None:
        return Check("visual_equivalence", "skipped", "pdftoppm not available")
    try:
        with tempfile.TemporaryDirectory(prefix="pdfocr-verify-") as tmp:
            src_pages = _rasterize(src, Path(tmp) / "src")
            out_pages = _rasterize(out_pdf, Path(tmp) / "out")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return Check("visual_equivalence", "skipped", f"raster comparison unavailable ({exc})")
    if len(src_pages) != len(out_pages):
        return Check(
            "visual_equivalence",
            "failed",
            f"rendered {len(src_pages)} input vs {len(out_pages)} output pages",
        )
    worst = 0.0
    for i, (a, b) in enumerate(zip(src_pages, out_pages), 1):
        diff = _mean_abs_diff(a, b)
        if diff is None:
            return Check("visual_equivalence", "failed", f"page {i}: raster sizes differ")
        worst = max(worst, diff)
        if diff > _PIXEL_DIFF_THRESHOLD:
            return Check(
                "visual_equivalence", "failed", f"page {i}: mean pixel diff {diff:.1f}"
            )
    return Check("visual_equivalence", "passed", f"max mean pixel diff {worst:.1f}")


def _rasterize(pdf: Path, prefix: Path) -> list[tuple[int, int, bytes]]:
    """Render every page to grayscale via pdftoppm; return (w, h, pixels) per page."""
    subprocess.run(
        ["pdftoppm", "-gray", "-r", str(_RASTER_DPI), str(pdf), str(prefix)],
        check=True,
        capture_output=True,
    )
    files = sorted(prefix.parent.glob(f"{prefix.name}-*"))
    if not files:
        raise ValueError("pdftoppm produced no pages")
    return [_read_pnm(f.read_bytes()) for f in files]


def _read_pnm(data: bytes) -> tuple[int, int, bytes]:
    """Parse a binary PGM (P5) or PPM (P6) image into grayscale pixels."""
    tokens: list[bytes] = []
    i = 0
    while len(tokens) < 4:
        while i < len(data) and data[i : i + 1].isspace():
            i += 1
        if data[i : i + 1] == b"#":
            while i < len(data) and data[i] != 0x0A:
                i += 1
            continue
        j = i
        while j < len(data) and not data[j : j + 1].isspace():
            j += 1
        tokens.append(data[i:j])
        i = j
    i += 1  # single whitespace byte between maxval and raster data
    magic, width, height, maxval = tokens[0], int(tokens[1]), int(tokens[2]), int(tokens[3])
    if maxval != 255:
        raise ValueError(f"unsupported maxval {maxval}")
    raw = data[i:]
    if magic == b"P5":
        pixels = raw[: width * height]
    elif magic == b"P6":
        rgb = raw[: 3 * width * height]
        pixels = bytes(
            (rgb[k] + rgb[k + 1] + rgb[k + 2]) // 3 for k in range(0, len(rgb), 3)
        )
    else:
        raise ValueError(f"unsupported PNM format {magic!r}")
    if len(pixels) < width * height:
        raise ValueError("truncated raster data")
    return width, height, pixels


def _mean_abs_diff(
    a: tuple[int, int, bytes], b: tuple[int, int, bytes]
) -> float | None:
    """Mean absolute pixel difference over the common area; None if sizes diverge."""
    wa, ha, pa = a
    wb, hb, pb = b
    if abs(wa - wb) > 2 or abs(ha - hb) > 2:
        return None
    w, h = min(wa, wb), min(ha, hb)
    total = 0
    for row in range(h):
        ra = pa[row * wa : row * wa + w]
        rb = pb[row * wb : row * wb + w]
        total += sum(abs(x - y) for x, y in zip(ra, rb))
    return total / (w * h)
