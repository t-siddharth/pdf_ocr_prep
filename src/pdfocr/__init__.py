"""pdfocr — detect scanned PDFs and add a searchable text layer + markdown sidecar."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pdfocr")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0+dev"
