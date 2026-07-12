"""Exception types for pdfocr."""


class PdfocrError(Exception):
    """Base class for all pdfocr errors."""


class InvalidPdfError(PdfocrError):
    """The file is missing, corrupt, not a PDF, or has no pages."""


class EncryptedPdfError(PdfocrError):
    """The PDF is password-protected and cannot be read."""


class MissingDependencyError(PdfocrError):
    """A required system binary (ocrmypdf) is not installed."""


class ConversionError(PdfocrError):
    """ocrmypdf failed while processing a file."""
