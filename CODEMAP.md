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
- `gui.py` – Tkinter application that manages scanning, lot display, status bar progress, author cleanup, and BookScouter refresh:
  - Per-cluster, case-by-case approvals in Author Cleanup
  - Optional sample book thumbnails (Pillow/requests-backed), cached under `~/.isbn_lot_optimizer/covers/`
  - Background task progress via `_start_progress`, `_update_progress`, `_finish_progress`
  - Bulk Buyback Helper dialog for optimizing vendor book assignments
- `service.py` – Domain logic for book storage, metadata/market refresh, series indexing, BookScouter refresh, and lot recomputation. Used by both GUI and CLI flows. Manages HTTP session reuse and database connection lifecycle.
- `database.py` – SQLite access layer with connection pooling. DatabaseManager class provides schema creation, query helpers, and persistent connection reuse for improved performance.
- `models.py` – Data classes representing books, lots, market stats, metadata payloads, and BookScouter vendor offers.
- `metadata.py` – Google Books/Open Library lookups plus enrichment helpers.
- `market.py` – eBay Finding API integration (sold/unsold and pricing) with Browse API fallback for active comps; market snapshot builders.
- `lot_market.py` – Lot-level market snapshots combining eBay Browse (active medians) and Finding (sold medians) for author/series/theme queries with on-disk caching.
- `ebay_auth.py` – Client credentials OAuth for eBay Browse API with on-disk bearer token caching.
- `lots.py` & `lot_scoring.py` – Lot generation strategies and scoring heuristics.
- `series_index.py`, `series_catalog.py`, `series_finder.py` – **DEPRECATED**: Legacy local series detection (JSON-backed). Replaced by Hardcover integration in `services/`. Retained for backward compatibility only.
- `clipboard_import.py` – Clipboard parsing utilities for quick ISBN entry.
- `utils.py` – ISBN normalisation and helper routines shared across modules.
- `constants.py` – Shared constants and regex patterns (title normalization, author splitting, cover types, BooksRun fallbacks).
- `author_aliases.py` – Unified author canonicalization with manual alias mapping and regex normalization. Consolidated from multiple implementations.
- `probability.py` – Probability scoring logic (condition weights, demand keywords, single-item <$10 bundling rule).
- `booksrun.py` – Internal BooksRun integration helpers (simple SELL endpoint support).
- `bookscouter.py` – BookScouter API client for multi-vendor buyback offers (14+ vendors including BooksRun). Rate-limited to 60 calls/minute.
- `bulk_helper.py` – Vendor bundle optimization algorithm that maximizes profit while meeting vendor minimums ($5-$10 per vendor). Uses greedy assignment strategy.
- `services/hardcover.py` – Hardcover GraphQL client with conservative rate limiting, retries, and parsing helpers.
- `services/series_resolver.py` – Series schema ensure, caching (7d TTL), Hardcover lookups, peers upsert, and book row updates.

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
- Series metadata columns on `books`: `series_name`, `series_slug`, `series_id_hardcover`, `series_position`, `series_confidence`, `series_last_checked`
- BookScouter data stored in `bookscouter_json` column (full JSON blob with all vendor offers)
- `series_peers` table persists peer titles for a series (ordered by position when available; title otherwise)
- `hc_cache` table caches Hardcover payloads (7d TTL) to reduce repeated calls
- Cover thumbnails cached under `~/.isbn_lot_optimizer/covers/` with SHA-256 filenames.
- eBay Browse OAuth token cache: `~/.isbn_lot_optimizer/ebay_bearer.json`
- Lot market snapshot cache: `~/.isbn_lot_optimizer/lot_cache.json`

## Background Tasks & Progress
- Long-running jobs (cover prefetch, refresh, imports, BookScouter refresh) run in background threads.
- Progress is routed through `_start_progress`, `_update_progress`, and `_finish_progress` in `gui.py`; service-level loops can provide callbacks (e.g. `BookService.refresh_books(progress_cb=...)`) that include evaluation objects for real-time status updates.

## CLI Entrypoints
- App (GUI/CLI): `python -m isbn_lot_optimizer`
  - Series refresh one-shot: `python -m isbn_lot_optimizer --refresh-series --limit 500`
- Backfill series script: `python -m isbn_lot_optimizer.scripts.backfill_series --db ~/.isbn_lot_optimizer/catalog.db --limit 500 --only-missing --stale-days 30`
- BooksRun bulk quotes: `python -m lothelper booksrun-sell --in isbns.csv --out quotes.csv [--format parquet] [--sleep 0.1]`

## Vendor Buyback Features
- **BookScouter Integration**: Multi-vendor buyback aggregation replacing single-vendor BooksRun
  - API rate limit: 60 calls/minute (enforced with 1.1s delay), 7000 calls/day
  - Returns offers from 14+ vendors including BooksRun, eCampus, Valore, TextbookRush, etc.
  - GUI displays best offer, vendor count, and top 3 offers per book
  - Status bar shows real-time data during refresh (book title, price, best offer, vendor count)
- **Bulk Buyback Helper**: Optimization tool under Tools menu
  - Maximizes total profit by assigning books to highest bidders
  - Respects vendor minimums ($5-$10 per vendor)
  - Greedy algorithm prioritizes high-value vendors
  - Tabbed interface shows bundles per vendor with value calculations
  - Tracks unassigned books (below minimums or no offers)

## Testing & Tooling
- Tests live under `tests/` and use `pytest`; covers BooksRun client and CLI paths.
  - Run tests: `pytest -q`
- Quick syntax check for core package:
  ```bash
  python -m py_compile isbn_lot_optimizer/*.py
