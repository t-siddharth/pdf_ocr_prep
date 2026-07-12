"""System-dependency checks."""

from __future__ import annotations

import platform
import shutil

from .errors import MissingDependencyError

_INSTALL_HINTS = {
    "Darwin": "brew install ocrmypdf",
    "Linux": "sudo apt install ocrmypdf (or your distro's equivalent)",
}
_DOCS_URL = "https://ocrmypdf.readthedocs.io/en/latest/installation.html"


def check_ocrmypdf() -> str:
    """Return the path to the ocrmypdf binary, or raise with an install hint."""
    exe = shutil.which("ocrmypdf")
    if exe is None:
        hint = _INSTALL_HINTS.get(platform.system(), f"see {_DOCS_URL}")
        raise MissingDependencyError(
            f"ocrmypdf not found on PATH. Install it with: {hint} "
            "(this also pulls in tesseract, ghostscript, qpdf, and poppler)."
        )
    return exe
