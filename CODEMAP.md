# CODEMAP

## Top Level
- `README.md` – Project overview, setup, CLI usage, and feature highlights.
- `CONFIG.md` – Configuration, environment variables, caches, and tunables.
- `CODEMAP.md` – This file.
- `requirements.txt` – Dependency spec for app + CLI tools and tests.
- `isbn_lot_optimizer/` – Core package containing the GUI, service layer, eBay/metadata integration, and utilities.
- `lothelper/` – Auxiliary CLI package (e.g., BooksRun bulk SELL quotes).
- `tests/` – Pytest-based tests for vendors/CLI.
- `.env` – Optional environment overrides (auto-loaded via python-dotenv).

## Package Layout (`isbn_lot_optimizer/`)
- `__main__.py` – Module entrypoint so `python -m isbn_lot_optimizer` launches the app.
- `app.py` – CLI argument parsing, dotenv bootstrapping, and service orchestration. Implements:
  - Core flags: `--database`, `--gui/--no-gui`, `--scan`, `--import`, `--condition`, `--edition`, `--skip-market`
  - Metadata refresh: `--refresh-metadata`, `--refresh-metadata-missing`, `--metadata-delay`, `--limit`
  - eBay params: `--ebay-app-id`, `--ebay-global-id`, `--ebay-delay`, `--ebay-entries`
  - Lots refresh: `--refresh-lot-signals`, `--limit`
  - Author tools: `--author-search`, `--author-threshold`, `--author-limit`, `--list-author-clusters`
- `gui.py` – Tkinter application that manages scanning, lot display, status bar progress, author cleanup, and BooksRun refresh:
  - Per-cluster, case-by-case approvals in Author Cleanup
  - Optional sample book thumbnails (Pillow/requests-backed), cached under `~/.isbn_lot_optimizer/covers/`
  - Background task progress via `_start_progress`, `_update_progress`, `_finish_progress`
- `service.py` – Domain logic for book storage, metadata/market refresh, series indexing, BooksRun refresh, and lot recomputation. Used by both GUI and CLI flows.
- `database.py` – SQLite access layer covering schema creation and query helpers (adds `booksrun_json`, lot justification, etc).
- `db.py` – Lightweight connection utilities used by maintenance scripts or simple access.
- `models.py` – Data classes representing books, lots, market stats, and metadata payloads.
- `metadata.py` – Google Books/Open Library lookups plus enrichment helpers.
- `market.py` – eBay Finding API integration (sold/unsold and pricing) with Browse API fallback for active comps; market snapshot builders.
- `lot_market.py` – Lot-level market snapshots combining eBay Browse (active medians) and Finding (sold medians) for author/series/theme queries with on-disk caching.
- `ebay_auth.py` – Client credentials OAuth for eBay Browse API with on-disk bearer token caching.
- `lots.py` & `lot_scoring.py` – Lot generation strategies and scoring heuristics.
- `series_index.py`, `series_catalog.py`, `series_finder.py` – Series detection and caching.
- `clipboard_import.py` – Clipboard parsing utilities for quick ISBN entry.
- `utils.py` – ISBN normalisation and helper routines shared across modules.
- `author_aliases.py`, `probability.py` – Supporting data and probability scoring logic (condition weights, demand keywords, single-item <$10 bundling rule).
- `booksrun.py` – Internal BooksRun integration helpers (simple SELL endpoint support).

## Auxiliary CLI Package (`lothelper/`)
- `__main__.py` – Entrypoint `python -m lothelper …` with subcommands.
- `cli/booksrun_sell.py` – Bulk BooksRun SELL quotes:
  - Args: `--in`, `--out`, `--format {csv,parquet}`, `--sleep`
  - Requires `BOOKSRUN_KEY` (via env or `.env`)
  - Reads CSV with `isbn` column; writes CSV/Parquet with quote rows.
- `utils/io.py` – CSV and Parquet helpers.
- `vendors/booksrun_client.py` – BooksRun client with retries, error handling, and env configuration.

## Data & Persistence
- Default SQLite catalogue path: `~/.isbn_lot_optimizer/catalog.db` (created on demand).
- Cover thumbnails cached under `~/.isbn_lot_optimizer/covers/` with SHA-256 filenames.
- eBay Browse OAuth token cache: `~/.isbn_lot_optimizer/ebay_bearer.json`
- Lot market snapshot cache: `~/.isbn_lot_optimizer/lot_cache.json`

## Background Tasks & Progress
- Long-running jobs (cover prefetch, refresh, imports, BooksRun refresh) run in background threads.
- Progress is routed through `_start_progress`, `_update_progress`, and `_finish_progress` in `gui.py`; service-level loops can provide callbacks (e.g. `BookService.refresh_books(progress_cb=...)`).

## CLI Entrypoints
- App (GUI/CLI): `python -m isbn_lot_optimizer`
- BooksRun bulk quotes: `python -m lothelper booksrun-sell --in isbns.csv --out quotes.csv [--format parquet] [--sleep 0.1]`

## Testing & Tooling
- Tests live under `tests/` and use `pytest`; covers BooksRun client and CLI paths.
  - Run tests: `pytest -q`
- Quick syntax check for core package:
  ```bash
  python -m py_compile isbn_lot_optimizer/*.py
