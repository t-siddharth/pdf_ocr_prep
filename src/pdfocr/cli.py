"""Command-line interface for pdfocr."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import __version__, convert, deps, detect, discover, verify
from .errors import (
    EncryptedPdfError,
    InvalidPdfError,
    MissingDependencyError,
    PdfocrError,
)

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_USAGE = 2
EXIT_MISSING_DEP = 3


@dataclass
class FileResult:
    """Outcome of handling one input PDF."""

    input: Path
    action: str  # processed | would_process | skipped | failed
    reason: str = ""
    pages: int = 0
    avg_chars_per_page: float = 0.0
    status: str = ""
    out_pdf: Path | None = None
    out_md: Path | None = None
    verification: dict | None = None


class _Reporter:
    """Routes human-readable output; keeps stdout clean when --json is on."""

    def __init__(self, quiet: bool, verbose: bool, json_mode: bool) -> None:
        self.quiet = quiet
        self.verbose = verbose
        self.json_mode = json_mode
        self._stream = sys.stderr if json_mode else sys.stdout

    def info(self, msg: str) -> None:
        if self.quiet or (self.json_mode and not self.verbose):
            return
        print(msg, file=self._stream)

    def error(self, msg: str) -> None:
        print(msg, file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdfocr",
        description=(
            "Detect scanned/image-only PDFs and produce a searchable PDF plus a "
            "markdown sidecar. Originals are never modified."
        ),
    )
    parser.add_argument("path", type=Path, help="a PDF file or a folder of PDFs")
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="recurse into subfolders when PATH is a folder (default: on)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="process PDFs that already have a text layer and overwrite existing outputs",
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="report what would be done, change nothing"
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="write outputs here instead of alongside inputs (folder structure is mirrored)",
    )
    parser.add_argument(
        "-l", "--lang", default="eng", help="tesseract OCR language(s), e.g. eng+deu (default: eng)"
    )
    parser.add_argument(
        "--min-chars",
        type=float,
        default=detect.DEFAULT_MIN_CHARS,
        help="below this avg chars/page a PDF counts as image-only (default: 50)",
    )
    parser.add_argument(
        "--text-threshold",
        type=float,
        default=detect.DEFAULT_TEXT_THRESHOLD,
        help="at/above this avg chars/page a PDF is skipped as already-searchable (default: 200)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="PDFs to OCR in parallel (default: 1; ocrmypdf already parallelizes across pages)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "after each conversion, check output integrity (page counts, "
            "markdown/text-layer agreement, visual equivalence) and report failures"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="print a machine-readable summary to stdout (logs go to stderr)",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("-q", "--quiet", action="store_true", help="errors only")
    verbosity.add_argument("-v", "--verbose", action="store_true", help="extra detail")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def _process_one(pdf: Path, args: argparse.Namespace) -> FileResult:
    """Detect, decide, and (unless dry-run) convert a single PDF."""
    out_pdf, out_md = discover.output_locations(pdf, args.path, args.output_dir)
    try:
        det = detect.detect_pdf(pdf, args.min_chars, args.text_threshold)
    except (EncryptedPdfError, InvalidPdfError) as exc:
        return FileResult(input=pdf, action="failed", reason=str(exc))

    result = FileResult(
        input=pdf,
        action="",
        pages=det.pages,
        avg_chars_per_page=round(det.avg_chars_per_page, 1),
        status=det.status.value,
        out_pdf=out_pdf,
        out_md=out_md,
    )
    if det.status is detect.TextLayerStatus.FULL and not args.force:
        result.action = "skipped"
        result.reason = f"has text layer ({det.avg_chars_per_page:.0f} chars/page)"
        return result
    if (out_pdf.exists() or out_md.exists()) and not args.force:
        result.action = "skipped"
        result.reason = "output already exists (use --force to overwrite)"
        return result
    if args.dry_run:
        result.action = "would_process"
        result.reason = f"{det.status.value}, {det.avg_chars_per_page:.0f} chars/page"
        return result
    try:
        convert.convert_pdf(pdf, out_pdf, out_md, args.lang)
    except PdfocrError as exc:
        result.action = "failed"
        result.reason = str(exc)
        return result
    result.action = "processed"
    if args.verify:
        result.verification = verify.verify_conversion(pdf, out_pdf, out_md).to_dict()
    return result


def _report_result(res: FileResult, rep: _Reporter) -> None:
    name = str(res.input)
    if res.action == "processed":
        assert res.out_pdf is not None and res.out_md is not None
        if res.verification is None:
            rep.info(f"{name} → {res.out_pdf.name}, {res.out_md.name}")
        elif res.verification["ok"]:
            rep.info(f"{name} → {res.out_pdf.name}, {res.out_md.name} [verified]")
        else:
            failures = "; ".join(
                f"{c['name']}: {c['detail']}" if c["detail"] else c["name"]
                for c in res.verification["checks"]
                if c["status"] == "failed"
            )
            rep.error(f"{name}: verification FAILED — {failures}")
    elif res.action == "would_process":
        rep.info(f"{name}: would OCR ({res.reason})")
    elif res.action == "skipped":
        rep.info(f"{name}: skipped ({res.reason})")
    else:
        rep.error(f"{name}: FAILED — {res.reason}")


def _json_payload(results: list[FileResult], args: argparse.Namespace) -> dict:
    counts = {
        "processed": sum(r.action in ("processed", "would_process") for r in results),
        "skipped": sum(r.action == "skipped" for r in results),
        "failed": sum(r.action == "failed" for r in results),
        "verification_failed": sum(
            r.verification is not None and not r.verification["ok"] for r in results
        ),
        "total": len(results),
    }
    return {
        "version": __version__,
        "dry_run": args.dry_run,
        "results": [
            {
                "input": str(r.input),
                "action": r.action,
                "reason": r.reason,
                "pages": r.pages,
                "avg_chars_per_page": r.avg_chars_per_page,
                "status": r.status,
                "outputs": (
                    {"pdf": str(r.out_pdf), "markdown": str(r.out_md)}
                    if r.action in ("processed", "would_process")
                    else None
                ),
                "verification": r.verification,
            }
            for r in results
        ],
        "summary": counts,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rep = _Reporter(args.quiet, args.verbose, args.json_output)

    if args.min_chars > args.text_threshold:
        rep.error("pdfocr: --min-chars cannot exceed --text-threshold")
        return EXIT_USAGE
    if args.workers < 1:
        rep.error("pdfocr: --workers must be at least 1")
        return EXIT_USAGE

    try:
        pdfs = discover.find_pdfs(args.path, args.recursive)
    except (FileNotFoundError, ValueError) as exc:
        rep.error(f"pdfocr: {exc}")
        return EXIT_USAGE

    if not args.dry_run and pdfs:
        try:
            deps.check_ocrmypdf()
        except MissingDependencyError as exc:
            rep.error(f"pdfocr: {exc}")
            return EXIT_MISSING_DEP

    results: list[FileResult] = []
    try:
        if args.workers > 1 and len(pdfs) > 1:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for res in pool.map(lambda p: _process_one(p, args), pdfs):
                    _report_result(res, rep)
                    results.append(res)
        else:
            for pdf in pdfs:
                res = _process_one(pdf, args)
                _report_result(res, rep)
                results.append(res)
    except KeyboardInterrupt:
        rep.error("pdfocr: interrupted")
        return 130

    payload = _json_payload(results, args)
    counts = payload["summary"]
    if args.json_output:
        print(json.dumps(payload, indent=2))
    else:
        suffix = " (dry run)" if args.dry_run else ""
        verify_part = (
            f", {counts['verification_failed']} failed verification" if args.verify else ""
        )
        rep.info(
            f"\nSummary: {counts['processed']} processed, "
            f"{counts['skipped']} skipped, {counts['failed']} failed{verify_part}{suffix}"
        )
    return (
        EXIT_FAILURES
        if counts["failed"] or counts["verification_failed"]
        else EXIT_OK
    )


if __name__ == "__main__":
    sys.exit(main())
