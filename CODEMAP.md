# CODEMAP

## Top Level
- `README.md` – Project overview and setup instructions.
- `CODEMAP.md` – This file.
- `requirements.txt` – Locked dependency spec for the application.
- `isbn_lot_optimizer/` – Core package containing the GUI, service layer, and utilities.
- `.env` – Optional environment overrides (not tracked).

## Package Layout (`isbn_lot_optimizer/`)
- `__main__.py` – Module entrypoint so `python -m isbn_lot_optimizer` launches the app.
- `app.py` – CLI argument parsing, environment bootstrapping, and service orchestration.
- `gui.py` – Tkinter application that manages scanning, lot display, status bar progress,
  and integration with the `BookService`.
- `service.py` – Domain logic for book storage, metadata/market refresh, and lot
  recomputation. Exposes hooks used by both GUI and CLI flows.
- `database.py` – SQLite access layer covering schema creation and query helpers.
- `db.py` – Light-weight connection utilities used by maintenance scripts.
- `models.py` – Data classes representing books, lots, markets, and metadata payloads.
- `metadata.py` – Google Books/Open Library lookups plus enrichment helpers.
- `market.py` & `lot_market.py` – eBay API integrations and market snapshot builders.
- `lots.py` & `lot_scoring.py` – Lot generation strategies and scoring heuristics.
- `series_index.py`, `series_catalog.py`, `series_finder.py` – Series detection and caching.
- `clipboard_import.py` – Clipboard parsing utilities for quick ISBN entry.
- `utils.py` – ISBN normalisation and helper routines shared across modules.
- `author_aliases.py`, `probability.py` – Supporting data and probability scoring logic.

## Data & Persistence
- Default SQLite catalogue path: `~/.isbn_lot_optimizer/catalog.db` (created on demand).
- Cover thumbnails cached under `~/.isbn_lot_optimizer/covers/` with SHA-256 filenames.

## Background Tasks & Progress
- Long-running jobs (cover prefetch, refresh, imports) run in background threads.
- Progress is routed through `_start_progress`, `_update_progress`, and
  `_finish_progress` in `gui.py`; service-level loops can provide callbacks (e.g.
  `BookService.refresh_books(progress_cb=...)`).

## Testing & Tooling
- No dedicated test suite yet; run `python -m py_compile isbn_lot_optimizer/*.py`
  for a fast syntax check.
- Add focused scripts under `scripts/` or `tests/` in future iterations to expand
  automation coverage.
