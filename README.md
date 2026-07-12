# pdfocr

Detect scanned/image-only PDFs and make them searchable. For each PDF that
needs it, `pdfocr` produces:

- `<name>-searchable.pdf` — the original with an invisible OCR text layer
- `<name>.md` — a markdown sidecar of the extracted text, pages separated by `---`

Originals are never modified. PDFs that already have a real text layer are
skipped automatically.

## Install

`pdfocr` shells out to [ocrmypdf](https://ocrmypdf.readthedocs.io/), which
must be on your `PATH` along with its own dependencies (tesseract,
ghostscript, qpdf, poppler):

```sh
# macOS
brew install ocrmypdf

# Debian/Ubuntu
sudo apt install ocrmypdf
```

Non-English OCR also needs the matching tesseract language pack: `brew install
tesseract-lang` on macOS (all languages), or per-language packages on
Debian/Ubuntu (e.g. `sudo apt install tesseract-ocr-deu` for `-l deu`).

Then install the CLI (any of):

```sh
uv tool install /path/to/pdfocr     # or: pipx install /path/to/pdfocr
pip install /path/to/pdfocr
```

Requires Python 3.10+.

## Usage

```sh
pdfocr scan.pdf                     # one file → scan-searchable.pdf + scan.md
pdfocr ./inbox                      # every PDF in a folder, recursively
pdfocr ./inbox --no-recursive       # top level only
pdfocr ./inbox --dry-run            # show what would happen, change nothing
pdfocr ./inbox -o ./out             # outputs to ./out (subfolders mirrored)
pdfocr scan.pdf -l eng+deu          # tesseract language(s)
pdfocr ./inbox --verify             # integrity-check every output
pdfocr ./inbox --workers 2 --json   # parallel across files, JSON summary
```

### How detection works

Average extractable characters per page (via pypdf):

| avg chars/page | classification | behavior |
| --- | --- | --- |
| < 50 (`--min-chars`) | image-only / scanned | OCR |
| 50–200 | sparse / partial text layer | OCR (only pages lacking text) |
| ≥ 200 (`--text-threshold`) | real text layer | skipped unless `--force` |

`--force` also overwrites existing outputs. It never rasterizes: OCR still
runs with `--skip-text`, and pages that already had text get their markdown
from the existing text layer.

`*-searchable.pdf` files are ignored during folder scans, so re-running on
the same folder is safe.

### Encrypted PDFs

There is no password option — `pdfocr` never decrypts protected files. PDFs
that are encrypted but have no user password are handled transparently.
Anything that actually requires a password is reported as failed
(`encrypted PDF (password required)`), counted in the summary, and the run
exits with code 1; other files in the same run are unaffected.

To process one, decrypt it first with qpdf (installed alongside ocrmypdf),
then run `pdfocr` on the result:

```sh
qpdf --decrypt --password=SECRET locked.pdf unlocked.pdf
pdfocr unlocked.pdf
```

### Flags

| flag | default | meaning |
| --- | --- | --- |
| `--recursive` / `--no-recursive` | recursive | folder scan depth |
| `--force` | off | process full-text PDFs, overwrite outputs |
| `-n`, `--dry-run` | off | report only; works without ocrmypdf installed |
| `-o`, `--output-dir DIR` | alongside input | output location (structure mirrored) |
| `-l`, `--lang` | `eng` | tesseract language(s), e.g. `eng+deu` |
| `--min-chars` | 50 | image-only threshold |
| `--text-threshold` | 200 | already-searchable threshold |
| `--verify` | off | integrity-check each output (see [Data integrity](#data-integrity--source-of-truth)) |
| `--workers N` | 1 | files OCR'd in parallel (ocrmypdf already uses all cores per file) |
| `--json` | off | machine-readable summary on stdout, logs on stderr |
| `-q` / `-v` | — | quiet / verbose |
| `--version` | — | print version |

### JSON output

`--json` prints a machine-readable summary to stdout (all logs go to stderr,
so it pipes cleanly into `jq`):

```json
{
  "version": "0.1.0",
  "dry_run": false,
  "results": [
    {
      "input": "inbox/scan.pdf",
      "action": "processed",
      "reason": "",
      "pages": 3,
      "avg_chars_per_page": 0.0,
      "status": "none",
      "outputs": { "pdf": "inbox/scan-searchable.pdf", "markdown": "inbox/scan.md" }
    }
  ],
  "summary": { "processed": 1, "skipped": 0, "failed": 0, "verification_failed": 0, "total": 1 }
}
```

`action` is one of `processed`, `would_process` (dry run), `skipped`, or
`failed`; `status` is the detection result (`none`, `sparse`, `full`). With
`--verify`, each processed result also carries a `verification` object
(`{"ok": bool, "checks": [{"name", "status", "detail"}, ...]}`).

### Exit codes

| code | meaning |
| --- | --- |
| 0 | success (including "everything already searchable") |
| 1 | one or more files failed (conversion error or a `--verify` check) |
| 2 | usage error (bad path, non-PDF input, bad thresholds) |
| 3 | ocrmypdf not installed |

## Development

```sh
uv venv --python 3.13
uv pip install -e ".[dev]"
.venv/bin/pytest
```

Test fixtures are generated at runtime (reportlab, img2pdf, pillow) — no PDF
binaries are committed. Tests that run real OCR are skipped automatically if
`ocrmypdf`/`tesseract` aren't installed, so the pure-Python tests run anywhere.

## Data integrity & source of truth

**Your originals are never touched.** All output goes to new files; in any
failure scenario you can delete the outputs and re-run.

Know what each output is before deciding what to trust:

- **The searchable PDF** contains the original page images plus an invisible
  OCR text layer. It is produced as PDF/A (the ISO archival standard), which
  means the file is *rebuilt* — visually faithful, but not bit-identical to
  the input. Even where the OCR text is wrong, the image a human reads is
  the original. Suitable as a working copy or archival object.
- **The markdown sidecar is inherently lossy.** It is tesseract's best guess
  at the page pixels — typically very accurate on clean scans, silently
  imperfect on poor ones — and layout (tables, columns) is flattened.
  Treat it as a search index and reading copy, **never** as the
  authoritative record. No tool can verify OCR text against a scan; the
  pixels are the only ground truth.

Recommended hierarchy: original PDF = system of record, searchable PDF =
working copy, markdown = machine-consumable index.

### `--verify`

With `--verify`, every conversion is followed by integrity checks of the
provable properties:

| check | what it proves |
| --- | --- |
| `readable` | both PDFs open and parse |
| `page_count` | output has the same number of pages as the input |
| `markdown_pages` | the markdown has exactly one `---` section per page |
| `text_agreement` | the markdown matches the text layer embedded in the searchable PDF |
| `visual_equivalence` | rendered pages are pixel-similar to the input (via poppler; skipped if `pdftoppm` is unavailable) |

Failures are reported per file, flagged in the JSON output, and fail the run
(exit code 1). What `--verify` cannot prove is OCR *accuracy* — see above.

- Password-protected PDFs are not decrypted (see [Encrypted PDFs](#encrypted-pdfs)).
- Detection uses average extractable characters per page, so a long scanned
  document with a few digital text pages can land in the sparse band — that's
  fine in practice, since OCR only touches pages without text.
- OCR quality is tesseract's: pass the right `--lang` for non-English scans,
  and expect imperfect text from low-resolution or handwritten sources.

## License

MIT
