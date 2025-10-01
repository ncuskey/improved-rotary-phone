# Improved Rotary Phone (ISBN Lot Optimizer)

Improved Rotary Phone—formerly LotHelper—is a desktop and CLI toolkit for
cataloguing second-hand books, estimating resale value, and assembling
profitable eBay lots. The Tkinter GUI drives a background service that persists
scans, retrieves market intelligence, and updates lot recommendations in real time.

## Highlights
- Barcode-friendly GUI for scanning ISBNs with condition and edition tracking.
- Background refresh jobs with unified progress feedback for cover prefetching,
  metadata/market updates, and BooksRun offer refresh.
- eBay market intelligence:
  - Finding API (sold/unsold history and prices) when `EBAY_APP_ID` is configured.
  - Browse API (active comps and median pricing) when `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` are configured. Marketplace selectable via `EBAY_MARKETPLACE` (default `EBAY_US`).
- Interactive Author Cleanup reviewer with per-cluster approvals and optional book thumbnails (Pillow/requests-backed).
- Monte Carlo based lot optimiser that favours cohesive sets and recency; also supports series/theme/author-based lot market snapshots.
- Persistent SQLite catalogue stored under `~/.isbn_lot_optimizer/` with optional
  CSV import/export workflows.
- Headless utilities, including a bulk BooksRun SELL quote fetcher.

## Quick Start
1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. (Optional) create a `.env` in the repository root or export variables in your shell.
   The app auto-loads `.env` via python-dotenv on startup.
   ```bash
   # eBay APIs
   export EBAY_APP_ID=your-finding-app-id              # Finding API (sold/unsold)
   export EBAY_CLIENT_ID=your-browse-client-id         # Browse API (active comps)
   export EBAY_CLIENT_SECRET=your-browse-client-secret
   export EBAY_MARKETPLACE=EBAY_US                     # Optional (default: EBAY_US)

   # BooksRun (for SELL quotes)
   export BOOKSRUN_KEY=your-booksrun-api-key

   # Optional proxy settings
   export HTTP_PROXY=http://proxy:8080
   export HTTPS_PROXY=http://proxy:8080
   ```

3. Launch the GUI:
   ```bash
   python -m isbn_lot_optimizer
   ```
   - Scan or type an ISBN, choose a condition, and press Enter. The app persists
     the book, runs metadata + market lookups, refreshes lot recommendations,
     and updates the status bar as background jobs complete.
   - If `EBAY_CLIENT_ID/EBAY_CLIENT_SECRET` are missing, Browse API features are disabled (a warning is printed).
   - Finding API sold/unsold stats are used when `EBAY_APP_ID` is present.

## Command Line Usage (isbn_lot_optimizer)
The toolkit also supports headless workflows. Representative examples:

```bash
# Import a CSV of ISBNs (columns can be a single 'isbn' header)
python -m isbn_lot_optimizer --no-gui --import data/isbn_batch.csv

# Scan a single ISBN without opening the GUI
python -m isbn_lot_optimizer --no-gui --scan 9780316769488 --condition "Very Good"

# Refresh metadata (Google Books / Open Library)
python -m isbn_lot_optimizer --no-gui --refresh-metadata --limit 100
python -m isbn_lot_optimizer --no-gui --refresh-metadata-missing --limit 500 --metadata-delay 0.1

# Refresh candidate lots with market signals (uses Finding API if EBAY_APP_ID is set;
# also uses Browse API medians when EBAY_CLIENT_ID/SECRET are set)
python -m isbn_lot_optimizer --no-gui --refresh-lot-signals --limit 50

# Author utilities from the local catalog
python -m isbn_lot_optimizer --no-gui --list-author-clusters
python -m isbn_lot_optimizer --no-gui --author-search "J K Rowling" --author-threshold 0.9 --author-limit 15

# Database location (defaults to ~/.isbn_lot_optimizer/catalog.db)
python -m isbn_lot_optimizer --database ~/.isbn_lot_optimizer/catalog.db --no-gui --scan 978...
```

Available flags (selection):
- Core: `--database`, `--gui`/`--no-gui`, `--scan`, `--import`, `--condition`, `--edition`, `--skip-market`
- eBay: `--ebay-app-id`, `--ebay-global-id` (Finding; default `EBAY-US`), `--ebay-delay`, `--ebay-entries`
- Metadata: `--metadata-delay`, `--refresh-metadata`, `--refresh-metadata-missing`, `--limit`
- Lots: `--refresh-lot-signals`, `--limit`
- Author tools: `--author-search`, `--author-threshold`, `--author-limit`, `--list-author-clusters`

## BooksRun Bulk Quotes (lothelper)
Fetch SELL quotes from BooksRun in bulk (requires `BOOKSRUN_KEY`):

```bash
# CSV -> CSV (default)
python -m lothelper booksrun-sell --in isbns.csv --out booksrun_sell_quotes.csv

# CSV -> Parquet
python -m lothelper booksrun-sell --in isbns.csv --out quotes.parquet --format parquet

# Tuning polite rate limits (sleep seconds between calls; default 0.2)
python -m lothelper booksrun-sell --in isbns.csv --out quotes.csv --sleep 0.1
```

The command reads an input CSV with an `isbn` column and writes either CSV or Parquet with per-ISBN results.

## Data & Caches
- Catalog DB (auto-created): `~/.isbn_lot_optimizer/catalog.db`
- Cover cache: `~/.isbn_lot_optimizer/covers/`
- eBay Browse OAuth token cache: `~/.isbn_lot_optimizer/ebay_bearer.json`
- Lot market snapshot cache: `~/.isbn_lot_optimizer/lot_cache.json`

## Development Notes
- Source lives in `isbn_lot_optimizer/` and `lothelper/`; see `CODEMAP.md` for an overview.
- Quick syntax check:
  ```bash
  python -m py_compile isbn_lot_optimizer/*.py
  ```
- Tests (pytest):
  ```bash
  pytest -q
  ```
- The GUI uses background threads for long-running operations. Any new service
  hooks should report progress through `_start_progress`, `_update_progress`,
  and `_finish_progress` to keep the status bar accurate.

## Licensing
This repository currently ships without an explicit licence. Add one before
publishing binaries or distributing widely.
