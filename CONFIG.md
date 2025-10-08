# Configuration

The app uses a local SQLite database with a few on-disk caches. A `.env` file in the repo root is auto-loaded on startup (python-dotenv), and shell exports also work.

## Database and Caches
- Catalog DB: `~/.isbn_lot_optimizer/catalog.db` (created on demand)
- Cover cache: `~/.isbn_lot_optimizer/covers/`
- eBay Browse OAuth token cache: `~/.isbn_lot_optimizer/ebay_bearer.json`
- Lot market snapshot cache: `~/.isbn_lot_optimizer/lot_cache.json`

Tables (created as needed): `books`, `lots`

## Environment Variables

### Primary Variables
- **EBAY_APP_ID** (optional): eBay Finding API App ID for sold/unsold history and pricing statistics.
- **EBAY_CLIENT_ID** / **EBAY_CLIENT_SECRET** (optional): eBay Browse API client credentials to enable active comps and median pricing.
- **EBAY_MARKETPLACE** (optional): eBay marketplace ID for Browse API requests. Default: `EBAY_US` (aka `EBAY-US` in Finding).
- **BOOKSCOUTER_API_KEY** or **apiKey** (optional): BookScouter API key for multi-vendor buyback offers (replaces BooksRun). GUI refresh and Bulk Buyback Helper.
- **BOOKSCOUTER_DELAY** (optional): Delay in seconds between BookScouter API calls. Default: `1.1` (to stay within 60 calls/minute limit).
- **BOOKSRUN_KEY** (optional): BooksRun API key for SELL quote fetching (`lothelper` CLI only - GUI now uses BookScouter).
- **BOOKSRUN_AFFILIATE_ID** (optional): BooksRun affiliate ID for tracking.
- **HARDCOVER_API_TOKEN** (optional but recommended): Hardcover API token used for series detection. Include the "Bearer " prefix, e.g. `Bearer eyJ...`.
- **HARDCOVER_GRAPHQL_ENDPOINT** (optional): Override the Hardcover API endpoint. Default: `https://api.hardcover.app/graphql`.
- **HTTP_PROXY** / **HTTPS_PROXY** (optional): Route HTTP(S) requests through a proxy when needed.

### Deprecated Variables (for backward compatibility)
- ~~BOOKSRUN_API_KEY~~ - Use **BOOKSRUN_KEY** instead
- ~~BOOKSRUN_AFK~~ - Use **BOOKSRUN_AFFILIATE_ID** instead

Create a local `.env` (or export in your shell) to set variables, e.g.:
```bash
# Finding API (sold/unsold)
export EBAY_APP_ID=your-finding-app-id

# Browse API (active comps)
export EBAY_CLIENT_ID=your-browse-client-id
export EBAY_CLIENT_SECRET=your-browse-client-secret
export EBAY_MARKETPLACE=EBAY_US

# BookScouter (multi-vendor buyback - replaces BooksRun in GUI)
export BOOKSCOUTER_API_KEY=your-bookscouter-api-key
export BOOKSCOUTER_DELAY=1.1

# BooksRun (bulk SELL quotes via lothelper CLI)
export BOOKSRUN_KEY=your-booksrun-api-key

# Optional proxy
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080
```

## Hardcover Series Integration

- Purpose: Detect and persist series metadata using Hardcover’s GraphQL search.
- Env:
  - `HARDCOVER_API_TOKEN` must be set; include the "Bearer " prefix.
  - `.env` in the repo root is auto-loaded; shell exports also work.
- Persistence (created on demand):
  - books: `series_name`, `series_slug`, `series_id_hardcover`, `series_position` (REAL), `series_confidence` (REAL), `series_last_checked` (TIMESTAMP)
  - `series_peers` table: stores peer titles for a series (ordered by position when available; title otherwise)
  - `hc_cache` table: caches API payloads with 7 day TTL to reduce repeated calls
- Rate limiting and retries:
  - 1 request/second with burst of 5; automatic backoff/retry on HTTP 429
- CLI usage:
  - One-shot refresh via main app:  
    `python -m isbn_lot_optimizer --refresh-series --limit 500`
  - Standalone backfill:  
    `python -m isbn_lot_optimizer.scripts.backfill_series --db ~/.isbn_lot_optimizer/catalog.db --limit 500 --only-missing --stale-days 30`
- GUI:
  - After a successful scan or import, background enrichment updates the DB. Rows with no series are marked checked to avoid reprocessing immediately.

Notes:
- If `EBAY_CLIENT_ID/EBAY_CLIENT_SECRET` are missing, Browse features are disabled; a warning is printed on startup.
- If `EBAY_APP_ID` is not set, sold/unsold statistics via Finding API are skipped; Browse may still provide active comps.
- Dotenv loading does not override already-exported shell variables by default.

## Tunables (edit in-code)
- Single-item minimum price signal: see `probability.py` → `score_probability` (adds a strong negative and sets `suppress_single` when baseline price < $10; suggests bundling).
- Condition weights: `CONDITION_WEIGHTS` in `probability.py`.
- Demand keywords: `HIGH_DEMAND_KEYWORDS` in `probability.py`.
- Edition boosts: handled in `probability.py` for edition strings containing “first/1st”, “signed”, or “limited”.

## Author Cleanup & Thumbnails
- The GUI includes an interactive Author Cleanup reviewer (Tools → Author Cleanup…) for normalizing author names cluster-by-cluster with optional visual context.
- Thumbnails are fetched from metadata sources (Google Books / Open Library) and cached under `~/.isbn_lot_optimizer/covers/` using SHA-256 filenames.
- Image support uses `Pillow` and `requests` (both listed in `requirements.txt`). If these libraries are unavailable, the reviewer still works but omits thumbnails.

## eBay Integration Details
- Finding API is used for sold/unsold counts and average/median sold prices when `EBAY_APP_ID` is configured.
- Browse API is used for active comps and medians when `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` are configured; bearer tokens are cached in `~/.isbn_lot_optimizer/ebay_bearer.json`.
- Lot market snapshots (`lot_market.py`) combine Browse active medians and (optionally) Finding sold medians for author/series/theme queries, with results cached in `~/.isbn_lot_optimizer/lot_cache.json`.

## BookScouter Integration
- **GUI Integration**: Replaces BooksRun with multi-vendor buyback aggregation
  - "Refresh BookScouter (All)" button refreshes offers for all books
  - Displays best offer, vendor count, and top 3 offers per book
  - Real-time status updates show book details during refresh
  - Rate-limited to 60 calls/minute (1.1s delay) to comply with API limits
- **Bulk Buyback Helper**: Tools → Bulk Buyback Helper…
  - Optimizes book assignments across vendors to maximize total profit
  - Respects vendor minimums ($5-$10 per vendor)
  - Shows bundles per vendor with value calculations and book lists
  - Tracks unassigned books (below minimums or no offers)
- **API Details**:
  - Rate limit: 60 calls/minute, 7000 calls/day
  - Returns offers from 14+ vendors: BooksRun, eCampus, Valore, TextbookRush, ValoreBooks, SellBackYourBook, BookByte, TextbookRecycling, Powell's Books, Cash4Books, BookDeal, MyBookBuyer, Ziffit, World of Books
  - Data stored in `bookscouter_json` column (full vendor offer JSON)
- Requires `BOOKSCOUTER_API_KEY` or `apiKey` in environment or `.env`

## BooksRun CLI Integration
- A separate headless CLI exists under the `lothelper` package for direct BooksRun SELL quotes:
  ```bash
  python -m lothelper booksrun-sell --in isbns.csv --out booksrun_sell_quotes.csv
  ```
- Requires `BOOKSRUN_KEY` in the environment or `.env`
- **Note**: The GUI now uses BookScouter instead of BooksRun for buyback offers
