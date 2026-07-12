# pdfocr CLI — New Session Handoff Prompt

**Prior session ID:** `local_a5aad371-f9fb-4f9d-8987-3440dd4be394`

**Updated 2026-07-12:** spec-review fixes folded in — sparse-band behavior, self-output exclusion, `--force` semantics, output-collision rules, defined exit codes, encrypted/zero-page handling, `--lang` pass-through, parallelism default, subprocess-vs-API decision.

Paste the prompt below into a fresh session to build the standalone CLI.

---

I want to convert an existing Claude skill called **pdf-ocr-prep** into a fully packaged, standalone command-line utility. Context from a prior session (`local_a5aad371-f9fb-4f9d-8987-3440dd4be394`) is below — you don't need it, the spec is self-contained.

## What the skill currently does
Two loose scripts I want to consolidate into one real CLI tool:

- `check_pdf.py` — uses pypdf to measure average extractable characters per page and classify a PDF: `<50 chars/page` = image-only/scanned (OCR recommended), `50–200` = sparse/partial text layer, `>200` = real text layer (skip OCR).
- `prep_pdf.sh` — runs `ocrmypdf --skip-text --sidecar` to add an invisible text layer, producing `<name>-searchable.pdf`, then builds a `<name>.md` markdown sidecar from the OCR text (form-feed characters split pages into `---`-separated sections). Uses tesseract, ghostscript, qpdf, poppler under the hood.

## What I want built
A single standalone CLI (Python, `argparse` or `click`) — call it `pdfocr` — that:

1. Accepts **either a single PDF file or a folder** as input. For a folder, recurse (with a `--recursive/--no-recursive` flag, default recursive) and process every `.pdf` (case-insensitive). When scanning folders, **ignore `*-searchable.pdf` files** (the tool's own output) so reprocessing a folder never produces `foo-searchable-searchable.pdf`.
2. For each PDF: detect whether it needs OCR using the same char/page heuristic (thresholds configurable via `--min-chars` / `--text-threshold`). **Anything below the text threshold (default 200 chars/page) gets OCR'd** — the sparse 50–200 band is processed, and `--skip-text` guarantees only pages without text are OCR'd. Files at/above the threshold are skipped unless `--force`.
3. For files that need it: produce `<name>-searchable.pdf` + `<name>.md` (same outputs as the skill), with a configurable `--output-dir` (default: alongside input). When recursing with `--output-dir`, **mirror the input directory structure** so same-named PDFs in different subfolders don't collide. Never overwrite an existing output without `--force`. Never modify the original.
4. Emit a summary at the end (processed / skipped / failed counts), support `--dry-run`, `--quiet/--verbose`, and defined exit codes: `0` success (including all-skipped), `1` one or more files failed, `2` usage/input error, `3` missing system dependency.
5. Handle errors cleanly (missing/corrupt PDF → clear message, not a traceback; encrypted/password-protected PDF → reported as failed with a reason, not a crash; zero-page PDF must not divide by zero), and check for the `ocrmypdf` binary up front with an actionable install hint. `--dry-run` should work without the binary present.
6. `--lang/-l` pass-through to tesseract (default `eng`) — scanned documents aren't always English.
7. `--force` never rasterizes (no `--force-ocr`): it keeps `--skip-text`, and for pages that already have a text layer the markdown sidecar is filled from pypdf-extracted text instead of ocrmypdf's `[OCR skipped on page N]` placeholders.

## Packaging requirements (the main ask — make it a *real* software utility, not scripts)
- Proper Python package with `pyproject.toml`, a `pdfocr` console-entry-point (`[project.scripts]`), pinned deps (`pypdf`, and document the system deps: `ocrmypdf`, `tesseract`, `ghostscript`, `qpdf`, `poppler`).
- Module structure (e.g. `detect.py`, `convert.py`, `cli.py`), type hints, docstrings.
- Invoke `ocrmypdf` as a **subprocess** (matches the proven command, keeps the install light) rather than importing it as a Python API dependency.
- **Tests**: pytest suite covering detection thresholds, single-file vs folder input, skip/force logic, and edge cases (nonexistent path, non-PDF, empty/blank PDF, encrypted PDF, filename with spaces, uppercase `.PDF` extension). Generate small synthetic PDF fixtures (reportlab + img2pdf for an image-only one) rather than committing binaries. Mark tests that invoke real OCR as skip-if-missing (`ocrmypdf`/`tesseract` absent) so the pure-Python tests run anywhere.
- A `README.md` with install + usage, and a `--version` flag.
- Bonus: parallel processing across files (`--workers N`, default 1 — ocrmypdf already parallelizes across pages, so don't default to CPU count), and a `--json` machine-readable summary printed to stdout with logs on stderr, so it's pipeable.

Please start by proposing the package layout and CLI surface, ask me anything genuinely ambiguous, then build it and run the test suite. Target Python 3.10+.

## Notes from the prior session worth carrying over
Three bugs already fixed in the skill (which the new tool should also avoid):

1. Raw traceback on missing/invalid input — should print a clean error and exit non-zero.
2. An undocumented intermediate `.txt` file was left behind — use a temp file + cleanup so only the documented outputs remain.
3. Case-sensitive `.pdf` extension stripping — strip `.pdf`/`.PDF`/`.Pdf` case-insensitively.

The OCR command that works is `ocrmypdf --skip-text --sidecar <txt> <in> <out>`; `--skip-text` means it won't error on PDFs that already have text.

One more edge worth knowing: with `--skip-text`, ocrmypdf exits with code 6 (`PriorOcrFoundError`) when *every* page already has text and writes no output. Under `--force` the tool should handle that by copying the PDF through unchanged and building the markdown from pypdf-extracted text.

And a sidecar gotcha found during the build (bug 4, fixed): ocrmypdf **coalesces consecutive skipped pages into one marker** — a mixed document produces `[OCR skipped on page(s) 1-2]` followed by a single form feed, not one marker per page. Naively splitting the sidecar on form feeds therefore misaligns markdown sections with pages (page 2's section silently gets page 3's OCR text). The marker must be expanded by its page range to keep the one-section-per-page mapping.
