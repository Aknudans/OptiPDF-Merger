# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

OptiPDF Merger is a small CLI pipeline (Spanish docstrings/output) that merges every PDF in a folder into one document, then shrinks it below a target size. Three stages, each its own module, always run in this order:

```
input_pdfs/*.pdf
  -> merger.py      merge_pdfs()              -> output/merged.pdf
  -> optimizer.py   deduplicate_if_available() -> output/deduped.pdf
  -> compressor.py  compress_pdf()             -> output/final.pdf
```

`src/main.py` (`run_pipeline`) wires these three together and is the only place that orchestrates the full three-stage pipeline for the CLI; `src/config.py` holds the shared defaults (`DEFAULT_INPUT_DIR="input_pdfs"`, `DEFAULT_OUTPUT_DIR="output"`, `DEFAULT_MAX_SIZE_MB=20`) so the limit isn't duplicated across modules. `src/webapp.py` is a second, independent entry point: a browser GUI over the same three stage functions (`merge_pdfs`, `deduplicate_if_available`, `compress_pdf`) for users who don't want the CLI — see "Implemented: browser-based GUI" below.

**Note:** `README.md` describes the optimization step as PyMuPDF-based font/image deduplication. The actual implementation in `src/optimizer.py` uses **qpdf** (`--stream-data=compress --object-streams=generate --remove-unreferenced-resources=yes`) for lossless stream recompression instead. Trust the code over the README for this step (README not yet updated to match).

## Implemented: browser-based GUI (`src/webapp.py`)

A local Flask server, separate from the CLI (`src/main.py` is untouched), gives non-technical users a browser UI instead of argparse flags. Run it with `python -m src.webapp` or the `run_gui.bat` wrapper (mirrors `run.bat`); `webapp.run()` opens `http://127.0.0.1:5000` in the user's default browser automatically (`webbrowser.open` on a `threading.Timer`, so it fires after the Flask dev server has started listening) and binds to `127.0.0.1` only (not exposed on the network).

Two flows, deliberately kept separate rather than one form with a mode toggle:

- `/fusion` (GET shows the form, POST processes it): a multi-file picker (`<input type="file" multiple>`) requiring **2+** PDFs. Runs the full pipeline for real — `merge_pdfs` -> `deduplicate_if_available` -> `compress_pdf` — against a `tempfile.TemporaryDirectory` working folder.
- `/compresion`: a single-file picker for a PDF the user already has. Skips `merge_pdfs` entirely and runs only `deduplicate_if_available` -> `compress_pdf`.

On success, neither route serves the file directly as the POST response. Instead, both render a **results page** (`_result_body`, wide layout, `max-width: 900px` vs. the 480px default) with two things side by side: a download link/button and a **console log panel** showing the same phase-by-phase messages a CLI run would print (so the user can confirm the result matches what they expected — e.g. that qpdf actually ran, which GhostScript phase stopped things, the resulting size — before trusting the download). Mechanics:

- The whole pipeline call (`merge_pdfs`/`deduplicate_if_available`/`compress_pdf`) runs inside `contextlib.redirect_stdout(log_buffer)` **and** `contextlib.redirect_stderr(log_buffer)` simultaneously, into the same `io.StringIO`. Both are required: `tqdm.write()` (the phase messages) goes to **stdout** by default, but the `tqdm(...)` progress bar itself goes to **stderr** by default — verified empirically, not assumed. Missing either one loses half the picture.
- The captured raw text contains `\r`-driven progress-bar redraws (not real newlines), which would render as garbled overlapping text if dumped straight into HTML. `_clean_console_log()` resolves this by replaying the buffer character-by-character and treating `\r` as "reset the current line", `\n` as "commit it" — the same rule a real terminal follows — then drops blank lines. This is tested directly in `test_webapp.py` (`test_clean_console_log_*`) independent of Flask.
- Both routes read the final file's bytes into memory (`final_path.read_bytes()`) **before** the `TemporaryDirectory` context manager exits — sidesteps a real Windows failure mode where deleting a temp dir while a file inside it is still open can fail or race.
- The download itself is a `data:application/pdf;base64,...` URI on an `<a download="...">` link, not a `send_file` response — this was a deliberate trade-off so the same response can carry both the HTML (log + button) and the file payload without a second round-trip or server-side session/token state. Fine at the ~20MB target size range for a local single-user tool; would need rethinking (e.g. a token-keyed temp download route) if files routinely got much larger.
- `html.escape()` is applied to the log text before embedding it in the page — defense in depth against anything unexpected in filenames/messages leaking into the HTML.

Error handling is deliberately narrow and maps to what can actually go wrong: `merge_pdfs`' `FileNotFoundError`/`ValueError` (e.g., uploads that fail the `.pdf` extension filter and leave the temp input folder empty) and `compressor.GhostScriptNotFoundError` are caught at the route level and re-rendered as an inline `.error` box on the same form — never a raw 500/stack trace. Uploaded filenames are passed through `werkzeug.utils.secure_filename` before touching the filesystem.

`tests/test_webapp.py` covers this with Flask's `test_client()`, monkeypatching `webapp.merge_pdfs` / `webapp.deduplicate_if_available` / `webapp.compress_pdf` directly (same "patch the name the module imported" rule as `compressor.py` — see Testing conventions below) — except the "no valid PDFs after filtering" test, which deliberately leaves `merge_pdfs` unpatched so the real `ValueError` path executes.

**Flask is now a dependency** (added to `requeriments.txt`); nothing else in the CLI pipeline needs it.

## Implemented: qpdf as a real compression stage + 100 DPI quality floor

The pipeline now guarantees images are never downsampled below **`MIN_DPI_FLOOR = 100`** (`src/compressor.py`), and uses qpdf as a genuine additional *lossless* compression stage rather than just an optional pre-pass. Background on the "360p" → "100 DPI" decision: "360p" is a video-resolution term (total pixel count, e.g. 640×360) that doesn't map cleanly to DPI (a page-size-independent density) — translating it literally for a typical Letter/A4 page works out to ~42 DPI, too low for legible text/signatures in the scanned contracts under `input_pdfs/`. 100 DPI was chosen instead as a middle ground between screen-only quality (72–96 DPI, roughly GhostScript's own `/screen` preset) and the archival/OCR-legible standard (150 DPI).

`compress_pdf` (`src/compressor.py`) now runs 5 phases, stopping at the first one under `max_size_mb`:

1–3. `/prepress` → `/printer` → `/ebook` (`COMPRESSION_PHASES`), unchanged — GhostScript's own defaults for these three presets (300/300/150 DPI) already sit above the floor.
4. `/screen`, but with `floor_dpi: MIN_DPI_FLOOR` set on the phase entry — this forces `_build_downsample_args(100)` as `extra_args`, which override GhostScript's own `/screen` default (~72 DPI, below the floor) so images never actually cross under 100 DPI even in this most-aggressive standard preset.
5. If phases 1–4 still don't reach the target, a **qpdf lossless squeeze** (`_attempt_qpdf_squeeze`) runs on the phase-4 output — it calls `optimizer.deduplicate_pdf` again (same lossless recompression used as the pre-pass in `main.py`, imported into `compressor.py`), writing to a `<name>.qpdf.tmp` sibling file and replacing the original in place. This is the "extra lossless compression push" instead of the old approach of downsampling further (which used to go from 60 DPI down to a 10 DPI floor and is now removed).

If qpdf isn't installed, phase 5 is skipped with a warning (`is_qpdf_available()` gate, same graceful-degradation pattern as the `optimizer.py` pre-pass) and the phase-4 result is kept as final — the function still never raises just because the size target wasn't met.

This directly changes `## Compression strategy` and the test suite below — see there for the up-to-date phase list and `tests/test_compressor.py` for how phase 4's forced floor and phase 5's qpdf squeeze are each tested independently (with `is_qpdf_available`/`deduplicate_pdf` monkeypatched on the `compressor` module, not `optimizer`, since they're imported by name into `compressor.py`).

## Commands

Run everything through the venv's interpreter (`.venv/Scripts/python.exe` on Windows) or activate it first.

```sh
# Install deps (note the filename typo: requeriments.txt, not requirements.txt)
pip install -r requeriments.txt

# Run the full pipeline with defaults (input_pdfs/ -> output/final.pdf, 20MB cap)
python -m src.main

# Custom input dir / output dir / size cap
python -m src.main path/to/pdfs --output-dir out --max-size-mb 15

# Windows convenience wrapper (checks .venv exists, then runs src.main)
run.bat

# Launch the browser GUI instead (opens http://127.0.0.1:5000 automatically)
python -m src.webapp
run_gui.bat

# Run all tests
pytest

# Run a single test file / test
pytest tests/test_compressor.py
pytest tests/test_compressor.py::test_se_detiene_en_la_primera_fase_que_cumple
```

There is no lint/format tooling configured in this repo (no ruff/black/flake8 config present).

## External binary dependencies

- **GhostScript** (`gs`, or `gswin64c`/`gswin32c` on Windows) is required by `compressor.py`. Detected via `shutil.which`; if missing, `compress_pdf` raises `GhostScriptNotFoundError` — the pipeline hard-fails at this stage.
- **qpdf** is optional and checked via `optimizer.is_qpdf_available()`. It's used twice: as the `optimizer.py` pre-pass before GhostScript (`deduplicate_if_available`, which copies the input through unchanged if qpdf is absent) and again as `compressor.py`'s phase-5 lossless squeeze (skipped with a warning if absent). Both call sites degrade gracefully instead of failing the pipeline.

Both are shelled out to via `subprocess.run`, not Python bindings, so tests mock `subprocess.run` / `shutil.which` rather than invoking the real binaries (see `tests/test_optimizer.py`, `tests/test_compressor.py`). A few tests (e.g. `test_integracion_real_deduplica_un_pdf_valido`) do call the real binary and self-skip with `pytest.skip` when it isn't on PATH.

## Compression strategy (`src/compressor.py`)

`compress_pdf` first copies the input through untouched if it's already under `max_size_mb` (no GhostScript call at all). Otherwise it walks phases in order, stopping at the first one that gets under the limit — see "Implemented: qpdf as a real compression stage + 100 DPI quality floor" above for the full 5-phase breakdown (4 GhostScript presets, the last one floor-capped at `MIN_DPI_FLOOR=100`, then a qpdf lossless squeeze). If every phase is exhausted without success, the last (most compressed, floor-respecting) attempt is left in place and a warning is printed — the function never raises for "couldn't compress enough."

Progress for both merging and compression is reported via `tqdm`; console messages inside a `tqdm` loop use `tqdm.write(...)` instead of `print(...)` to avoid corrupting the progress bar — follow this convention if you add output inside either loop.

## Testing conventions

- Tests never depend on real PDFs from `input_pdfs/`; they generate throwaway PDFs with `pypdf.PdfWriter` (`test_merger.py`) or dummy byte-sized files (`test_compressor.py`'s `write_mb` helper) inside pytest's `tmp_path`.
- `test_webapp.py` uses Flask's `app.test_client()` rather than starting a real server, and fakes the pipeline functions (`merge_pdfs`, `deduplicate_if_available`, `compress_pdf`) at the `webapp` module level rather than exercising real GhostScript/qpdf.
- External-tool behavior (GhostScript, qpdf) is faked at whatever name the calling module bound it to, which differs by module: `optimizer.py` does `import shutil` / `import subprocess`, so its tests patch `optimizer.shutil.which` / `optimizer.subprocess.run`. `compressor.py` does `from src.optimizer import deduplicate_pdf, is_qpdf_available` (name import), so its tests patch `compressor.deduplicate_pdf` / `compressor.is_qpdf_available` directly — patching `optimizer.deduplicate_pdf` instead would have no effect on `compressor.py`'s already-bound reference.
