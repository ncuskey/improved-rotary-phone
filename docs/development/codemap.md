# CODEMAP

**Last Updated:** 2025-10-26 (Keyword Ranking & SEO Title Optimization)

## Top Level
- `README.md` – Project overview, quick start, and links to documentation
- `.mdc` – Model context file for AI assistants (architecture, patterns, conventions)
- `requirements.txt` – Python dependencies
- **`shared/`** – Common business logic used by all apps (14 modules)
- **`isbn_lot_optimizer/`** – Desktop GUI application and app-specific logic
- **`isbn_web/`** – FastAPI web application with HTMX/Alpine.js frontend
- **`LotHelperApp/`** – SwiftUI iOS application
- `lothelper/` – CLI tools (BooksRun bulk quotes)
- `token-broker/` – Node.js OAuth service for iOS app
- `scripts/` – Data management scripts (series scraping, validation)
- `tests/` – Pytest unit tests and shell integration tests
- `docs/` – Organized documentation (setup, deployment, features, development)
- `data/` – Large data files (bookseries_complete.json, can be regenerated)
- `.env` – Optional environment overrides (auto-loaded via python-dotenv)

## Shared Module (`shared/`)

Common business logic used by all three applications. **14 modules total:**

### Core Infrastructure
- **`database.py`** – `DatabaseManager` class with connection pooling, schema creation, query helpers
  - Scan history: `log_scan()`, `get_scan_history()`, `get_scan_locations()`, `get_scan_stats()`
  - Table: `scan_history` (17 fields with location data, 4 indexes)
- **`models.py`** – Data classes: `BookMetadata`, `LotSuggestion`, `BookEvaluation`, `EbayMarketStats`, etc.

### Utilities
- **`utils.py`** – ISBN normalization/validation, CSV reading, ISBN-10 to ISBN-13 conversion
- **`constants.py`** – Shared constants, patterns (TITLE_NORMALIZER, COVER_CHOICES), API fallback keys

### API Clients
- **`bookscouter.py`** – BookScouter API client (multi-vendor buyback offers, 14+ vendors, rate-limited 60/min)
- **`booksrun.py`** – BooksRun API client (simple SELL endpoint support)

### Author System
- **`author_aliases.py`** – Author name canonicalization with manual alias mapping (e.g., "Robert Galbraith" → "J. K. Rowling")

### Series System (6 modules)
- **`series_database.py`** – Series SQLite database operations
- **`series_matcher.py`** – Fuzzy matching algorithms for books/series/authors
- **`series_integration.py`** – Integration helpers for apps (match_and_attach_series, enrich_evaluation_with_series)
- **`series_index.py`** – Series indexing, volume parsing from titles
- **`series_catalog.py`** – Series catalog management
- **`series_finder.py`** – Series finding and attachment logic

**All shared modules use absolute imports (e.g., `from shared.database import DatabaseManager`) and have no dependencies on app-specific packages.**

## Desktop Application (`isbn_lot_optimizer/`)

Tkinter desktop GUI and supporting desktop-specific logic. **20 modules remaining after restructure:**

### Application Entry
- **`__main__.py`** – Module entrypoint: `python -m isbn_lot_optimizer`
- **`app.py`** – CLI argument parsing, dotenv bootstrap, service orchestration
  - Flags: `--database`, `--gui/--no-gui`, `--scan`, `--import`, `--condition`, `--edition`
  - Metadata: `--refresh-metadata`, `--refresh-metadata-missing`, `--limit`
  - eBay: `--ebay-app-id`, `--ebay-global-id`, `--ebay-delay`, `--ebay-entries`
  - Lots: `--refresh-lot-signals`
  - Series: `--refresh-series`
  - Authors: `--author-search`, `--author-threshold`, `--list-author-clusters`

### User Interface
- **`gui.py`** (153KB) – Tkinter desktop application
  - Book scanning, lot display, author cleanup, BookScouter refresh
  - Progress bar for background tasks (`_start_progress`, `_update_progress`, `_finish_progress`)
  - Cover thumbnail display (Pillow-backed, cached in `~/.isbn_lot_optimizer/covers/`)
  - Bulk Buyback Helper dialog (vendor optimization)

### Core Services
- **`service.py`** (130KB) – `BookService` class: main business logic
  - Book storage, metadata/market refresh, lot recomputation
  - HTTP session reuse, database connection lifecycle
  - Scan history: `log_scan()` method, auto-logging on ACCEPT
  - Incremental lot updates: `update_lots_for_isbn()` with 3-phase optimization
    - Phase 1: Build all skeletons without pricing (~0.13s, no API calls)
    - Phase 2: Filter to affected lots (~0.00s)
    - Phase 3: Enrich only affected lots with pricing (~0.00-2s, 0-3 API calls)
  - `build_lot_candidates(fetch_pricing=True)` – Supports fast skeleton mode
  - `_enrich_candidates_with_pricing()` – Selective pricing enrichment helper
  - Used by both GUI and CLI
- **`metadata.py`** (26KB) – Google Books/Open Library API integration
- **`probability.py`** (18KB) – Probability scoring (condition weights, demand keywords, bundling rules)

### Market Data
- **`market.py`** – eBay Finding API (sold/unsold pricing) + Browse API (active comps)
- **`ebay_sold_comps.py`** – eBay sold comparisons
- **`ebay_auth.py`** – Client credentials OAuth for eBay Browse API
- **`lot_market.py`** – Lot-level market snapshots with caching

### eBay Listing Integration (✅ Sprint 2 Complete)
- **`ebay_sell.py`** (600+ lines) – eBay Sell API client for Inventory and Offer management
  - `EbaySellClient` class with Inventory and Offer API methods
  - Inventory location management (auto-creates default location)
  - Create/update/delete inventory items with condition and weight
  - Create/publish/delete offers with business policies
  - High-level `create_and_publish_book_listing()` method
  - Condition format handling (text for inventory, numeric for offers)
- **`ebay_listing.py`** (460 lines) – High-level listing service orchestration
  - `EbayListingService` class coordinating AI, eBay APIs, and database
  - Integrates with AI listing generator for content creation
  - Database persistence with ebay_listings table (includes SEO keyword tracking)
  - Draft saving on errors, status tracking (draft/active/sold/ended)
  - Performance metrics (TTS, price accuracy) calculation
  - `use_seo_optimization` parameter for keyword-optimized titles
- **`keyword_analyzer.py`** (462 lines) – ✨ NEW: Keyword ranking and SEO optimization
  - `KeywordAnalyzer` class for eBay marketplace keyword analysis
  - 4-factor scoring algorithm: frequency (40%), price (30%), velocity (20%), competition (10%)
  - Extracts keywords from 100-200 eBay listings per ISBN
  - Ranks keywords 1-10 scale based on search value
  - 24-hour caching for performance (1000x speedup)
  - Filters 100+ stopwords (common words + eBay-specific terms)
  - `calculate_title_score()` utility for scoring titles
  - `format_keyword_report()` for analysis display
- **`ai/listing_generator.py`** (602 lines) – AI-powered listing content generation
  - `EbayListingGenerator` class using Llama 3.1 8B via Ollama
  - Standard SEO-optimized title generation (max 80 chars)
  - ✨ NEW: `generate_seo_title()` method with keyword ranking
    - Generates 5 title variations using top 30 keywords
    - Scores each variation and selects highest-scoring
    - SEO-style titles (keyword-packed, readable)
    - Example: "Storm Swords Martin GRRM Song Ice Fire Fantasy" (score: 48.7)
    - Generation time ~8 seconds (vs 2-3s for standard)
  - Engaging description generation (200-400 words)
  - Highlight extraction and condition-aware content

### Lot Generation
- **`lots.py`** – Lot generation strategies with 3-phase architecture:
  - `_compose_lot_without_pricing()` – Fast skeleton generation (no eBay API calls)
  - `_enrich_lot_with_pricing()` – Slow pricing enrichment (eBay API calls)
  - `_compose_lot()` – Wrapper with `fetch_pricing` parameter (default True)
  - `generate_lot_suggestions()` – Main entry point with `fetch_pricing` parameter
  - `build_lots_with_strategies()` – Strategy-based generation with `fetch_pricing` parameter
- **`lot_scoring.py`** – Lot scoring heuristics
- **`series_lots.py`** – Series-based lot generation (desktop-specific)
- **`book_routing.py`** – Book routing decisions

### Desktop-Specific Features
- **`clipboard_import.py`** – Clipboard parsing for quick ISBN entry
- **`bulk_helper.py`** – Vendor bundle optimization (greedy assignment, respects minimums)

### Supporting
- **`author_match.py`** – Author matching logic

### Hardcover Integration
- **`services/hardcover.py`** – Hardcover GraphQL client (rate-limited, retries, parsing)
- **`services/series_resolver.py`** – Series caching (7d TTL), Hardcover lookups, peer upsert

**Desktop app imports from shared:** `from shared.database import DatabaseManager`, `from shared.models import BookMetadata`, etc.

## Web Application (`isbn_web/`)

FastAPI + Jinja2 + HTMX + Alpine.js web interface with REST API for iOS app.

### Application Structure
- **`main.py`** – FastAPI application entry point
- **`config.py`** – Configuration management
- **`api/`** – API routes and dependencies
  - `routes/books.py` – Book scanning, CRUD, series integration, metadata search, scan history
    - Scan history endpoints: `POST /api/books/log-scan`, `GET /api/books/scan-history`, `GET /api/books/scan-locations`, `GET /api/books/scan-stats`
  - `routes/lots.py` – Lot generation and display
  - `routes/actions.py` – Bulk actions (delete, import CSV)
  - `dependencies.py` – Thread-safe database manager for web requests
- **`templates/`** – Jinja2 templates
  - `index.html` – Main page with 3D carousel
  - `components/` – Reusable HTMX components
- **`static/`** – CSS, JS (minimal, prefer inline)
- **`services/`** – Web-specific services
  - `cover_cache.py` – Cover image caching with HTTP redirect support

### Features
- 3D book carousel with momentum scrolling
- Mobile camera scanner (media capture API)
- Metadata search API (`POST /api/books/search-metadata`) for title/author lookup
- HTMX for dynamic updates
- Alpine.js for reactive components
- RESTful API endpoints for iOS app
- Series integration via `shared.series_integration`

**Web app imports from shared:** `from shared.series_integration import match_and_attach_series`, `from shared.utils import normalise_isbn`

## iOS Application (`LotHelperApp/`)

SwiftUI native iOS application with barcode/OCR scanning.

### Key Files
- **`BookAPI.swift`** – REST API client for backend communication (includes metadata search and scan history)
  - Scan history methods: `logScan()`, `getScanHistory()`, `getScanLocations()`, `getScanStats()`
- **`LocationManager.swift`** – Core Location integration with GPS tracking and reverse geocoding
  - ObservableObject with @Published location data
  - Location caching via @AppStorage
  - CLLocationManagerDelegate implementation
- **`ScannerReviewView.swift`** – Scanner interface and triage workflow
  - Location tracking on scan accept/reject
  - Auto-logs REJECT decisions with location data
- **`ScanHistoryView.swift`** – Scan history browser with location filtering
  - Accept/reject filtering, location-based summaries
  - Statistics dashboard with acceptance rates
- **`BooksTabView.swift`** – Books library with search and sorting
- **`LotRecommendationsView.swift`** – Lot recommendations with strategy filtering
- **`CacheManager.swift`** – SwiftData cache with NotificationCenter updates
- **`CachedBook.swift`** – SwiftData model with BooksRun offers and timestamps
- **`SettingsView.swift`** – App configuration
- **`ContentView.swift`** – Main navigation

### Features
- Barcode scanning via camera
- OCR text extraction
- Real-time eBay pricing via token broker
- Books library with search (title/author/ISBN/series) and 8 sort options
- Lot filtering by strategy (author, series complete/partial/incomplete, value)
- Metadata search for books without barcodes (title/author → ISBN + references)
- SwiftData caching with real-time updates
- Enhanced BooksRun buyback offer tracking
- Triage workflow (Keep/Sell/List/Donate)
- **Location-based scan history with GPS tracking**
  - Automatic location tracking on all scans (with user permission)
  - Complete audit trail (ACCEPT and REJECT decisions)
  - Store performance analytics and acceptance rates
  - Reverse geocoding to location names
  - Location caching for offline use
- Syncs with backend API

### Integration
- Uses `token-broker/` on port 8787 for OAuth
- Requires audio file in bundle: `Cha-Ching.mp3`
- Communicates with web app API

## CLI Tools (`lothelper/`)

Auxiliary command-line tools for bulk operations.

- **`__main__.py`** – Entrypoint: `python -m lothelper ...`
- **`cli/booksrun_sell.py`** – Bulk BooksRun SELL quotes
  - Args: `--in`, `--out`, `--format {csv,parquet}`, `--sleep`
  - Requires `BOOKSRUN_KEY` environment variable
  - Reads CSV with `isbn` column, outputs CSV/Parquet with quotes
- **`utils/io.py`** – CSV and Parquet helpers
- **`vendors/booksrun_client.py`** – BooksRun client with retries and error handling

## Scripts (`scripts/`)

Data management and utility scripts.

### Series Data Management
- **`scrape_bookseries_org.py`** – Scrapes BookSeries.org for complete series data
- **`import_series_data.py`** – Imports series JSON into SQLite database
- **`match_books_to_series.py`** – Fuzzy matches books to series
- **`verify_series_lots.py`** – Validates series lot generation
- **`test_series_lots.py`** – Tests series lot algorithms

### Database Migrations
- **`migrate_ebay_listings_table.py`** – Creates ebay_listings table for tracking eBay sales
- **`migrate_keyword_scores.py`** – ✨ NEW: Adds SEO keyword tracking columns
  - Adds `title_score` (REAL) column for keyword score tracking
  - Adds `keyword_scores` (TEXT/JSON) column for keyword data
  - Creates performance index on title_score
  - Backwards-compatible (checks for existing columns)

### Utilities
- **`prefetch_covers.py`** – Bulk downloads cover images
- **`utils/check-token-ssl.sh`** – Verifies token broker SSL
- **`utils/sync_to_isbn.sh`** – Syncs files to local server

See: `scripts/README.md` for detailed documentation

## Token Broker (`token-broker/`)

Node.js OAuth service providing eBay tokens to iOS app and Python backend. **Enhanced for Sprint 2 with User OAuth support.**

- **`server.js`** (500+ lines) – Express server on port 8787
  - **App OAuth**: Client credentials for Browse API (iOS app)
  - **User OAuth**: Authorization code grant for Sell APIs (listing automation)
    - Authorization URL generation with CSRF protection
    - OAuth callback handler for code exchange
    - Automatic token refresh (2-hour access tokens, 18-month refresh tokens)
    - Multi-scope support: `sell.inventory`, `sell.fulfillment`, `sell.marketing`, `sell.account`
    - In-memory token storage with refresh capability
  - Endpoints: `/token/ebay-browse`, `/token/ebay-user`, `/oauth/authorize`, `/oauth/callback`, `/oauth/status`
- **`package.json`** – Node dependencies
- Auto-starts with `isbn-web` command
- Cloudflare tunnel support: `tokens.lothelper.clevergirl.app`

## Data & Persistence

### SQLite Database
**Location:** `~/.isbn_lot_optimizer/catalog.db` (created on demand)

**Key Tables:**
- `books` – Scanned books with metadata, market data, series info
  - Series columns: `series_name`, `series_slug`, `series_id_hardcover`, `series_position`, `series_confidence`, `series_last_checked`
  - BookScouter: `bookscouter_json` (full JSON with all vendor offers)
- `scan_history` – Complete audit trail of all scans (ACCEPT, REJECT, SKIP)
  - 17 fields: ISBN, decision, book details, location data (name, address, GPS coordinates)
- `ebay_listings` – eBay listing tracking (Sprint 2)
  - Core fields: `isbn`, `sku`, `offer_id`, `ebay_listing_id`, `title`, `description`, `price`, `condition`, `quantity`
  - AI metadata: `ai_generated`, `ai_model`, `generation_time_seconds`
  - Status tracking: `status` (draft/active/sold/ended), `listed_at`, `sold_at`, `ended_at`
  - Performance: `estimated_price`, `actual_sale_price`, `time_to_sell_days`, `price_accuracy_percent`
  - Error handling: `error_message` for failed listings
  - 4 indexes: isbn, scanned_at DESC, decision, location_name
  - Supports location-based analytics and "previously scanned" warnings
- `lots` – Generated lot suggestions with scoring
- `series`, `authors`, `series_books` – BookSeries.org data
- `book_series_matches` – Fuzzy matches between books and series
- `series_peers` – Peer titles in a series (Hardcover API)
- `hc_cache` – Hardcover API response cache (7-day TTL)

### Caches
- `~/.isbn_lot_optimizer/covers/` – Book cover thumbnails (SHA-256 filenames)
- `~/.isbn_lot_optimizer/ebay_bearer.json` – eBay OAuth token
- `~/.isbn_lot_optimizer/lot_cache.json` – Lot market snapshots

### Large Data Files
- `data/bookseries_complete.json` – Complete series data from BookSeries.org (can be regenerated)

## Architecture Patterns

### Import Hierarchy
```python
# Shared modules (used by all apps)
from shared.database import DatabaseManager
from shared.models import BookMetadata, LotSuggestion
from shared.utils import normalise_isbn
from shared.constants import TITLE_NORMALIZER
from shared.series_integration import match_and_attach_series

# Desktop app specific
from isbn_lot_optimizer.service import BookService
from isbn_lot_optimizer.metadata import fetch_metadata

# Web app specific
from isbn_web.services.cover_cache import CoverCacheService
```

### Background Tasks (Desktop GUI)
Long-running operations use progress callback pattern:
```python
def long_operation(progress_cb):
    progress_cb("Starting...")
    # do work
    progress_cb(f"Processed {n} items...")
    progress_cb("Complete!")

# In GUI
self._start_progress("Task Name")
threading.Thread(target=long_operation, args=(self._update_progress,)).start()
```

### Web App HTMX Patterns
```html
<!-- Swap pattern -->
<div hx-get="/api/books" hx-trigger="load" hx-swap="outerHTML">Loading...</div>

<!-- Form pattern -->
<form hx-post="/api/books/scan" hx-target="#book-table" hx-swap="outerHTML">
  <input name="isbn" required>
</form>

<!-- Delete pattern -->
<button hx-delete="/api/books/{isbn}" hx-target="closest tr" hx-swap="outerHTML swap:1s">
  Delete
</button>
```

## Key Features

### BookScouter Multi-Vendor Buyback
- Replaces single-vendor BooksRun in GUI
- API rate limit: 60 calls/minute (1.1s delay), 7000 calls/day
- Returns offers from 14+ vendors (BooksRun, eCampus, Valore, TextbookRush, etc.)
- GUI shows best offer, vendor count, top 3 offers per book
- Real-time status bar updates during refresh

### Bulk Buyback Helper
- Tools menu optimization feature
- Maximizes profit by assigning books to highest bidders
- Respects vendor minimums ($5-$10 per vendor)
- Greedy algorithm prioritizes high-value vendors
- Tabbed interface with per-vendor bundles
- Tracks unassigned books

### Series Integration
Two complementary systems:
1. **Hardcover API** – GraphQL, single book queries, real-time
2. **BookSeries.org** – Scraped data, bulk matching, comprehensive

Both store data in shared database, accessible via `shared.series_integration`

## CLI Entrypoints

### Desktop App
```bash
# Launch GUI
python -m isbn_lot_optimizer

# Stats
python -m isbn_lot_optimizer --no-gui --stats

# Scan book
python -m isbn_lot_optimizer --no-gui --scan 9780316769488

# Refresh metadata
python -m isbn_lot_optimizer --no-gui --refresh-metadata --limit 100

# Refresh series
python -m isbn_lot_optimizer --no-gui --refresh-series --limit 500

# Generate lots
python -m isbn_lot_optimizer --no-gui --refresh-lot-signals
```

### Web App
```bash
# Development server
uvicorn isbn_web.main:app --reload --port 8000

# Production (via Procfile)
web: uvicorn isbn_web.main:app --host 0.0.0.0 --port $PORT
```

### CLI Tools
```bash
# BooksRun bulk quotes
python -m lothelper booksrun-sell --in isbns.csv --out quotes.csv

# With parquet output
python -m lothelper booksrun-sell --in isbns.csv --out quotes.parquet --format parquet
```

### Scripts
```bash
# Scrape series data
python scripts/scrape_bookseries_org.py --output data/bookseries_complete.json

# Import to database
python scripts/import_series_data.py --json-file data/bookseries_complete.json

# Match books to series
python scripts/match_books_to_series.py --auto-save-threshold 0.9

# Prefetch covers
python scripts/prefetch_covers.py
```

## Testing

### Unit Tests
```bash
# Run all tests
pytest tests/

# Verbose
pytest tests/ -v

# Specific test
pytest tests/test_utils.py
```

### Integration Tests
```bash
# Comprehensive web app test (requires running server)
./tests/integration/test_web_comprehensive.sh

# Web scanning test
./tests/integration/test_web_scan.sh

# eBay listing integration test (Sprint 2)
# Requires: token broker running, OAuth authorized, Ollama with llama3.1:8b
python3 tests/test_ebay_listing_integration.py --dry-run  # Check prerequisites only
python3 tests/test_ebay_listing_integration.py             # Create real listing

# ✨ NEW: Keyword analyzer tests (requires eBay API credentials)
python3 tests/test_keyword_analyzer.py                     # 6 comprehensive tests
python3 tests/test_seo_title_end_to_end.py [isbn]         # End-to-end SEO title test
```

### Manual Testing
- Desktop GUI: Launch and scan books
- iOS app: Run in Xcode simulator
- Camera scanner: Test on mobile device

## Environment Variables

**Required:** None (app works with fallback credentials)

**Recommended:**
```bash
# eBay APIs
EBAY_APP_ID=...              # Finding API (sold/unsold comps)
EBAY_CLIENT_ID=...           # Browse API (active comps)
EBAY_CLIENT_SECRET=...       # OAuth + token broker

# BookScouter (multi-vendor buyback)
BOOKSCOUTER_API_KEY=...

# Hardcover (series detection)
HARDCOVER_API_TOKEN=Bearer ...

# BooksRun (CLI only, optional)
BOOKSRUN_KEY=...
BOOKSRUN_AFFILIATE_ID=...
```

See: `docs/setup/configuration.md` for complete list

## Deployment

### Local Server
Mac Mini with launchd (auto-start on login)

**Files:**
- `~/Library/LaunchAgents/com.nickcuskey.isbn-web.plist`
- Logs: `/Users/nickcuskey/ISBN/logs/`

See: `docs/setup/installation.md`

### Cloud
**Railway** (recommended) or **Render**

**Files:**
- `Procfile` – Start command
- `railway.toml` – Railway configuration
- `render.yaml` – Render configuration

See: `docs/deployment/overview.md`, `docs/deployment/railway.md`, `docs/deployment/render.md`

## Documentation Structure

```
docs/
├── setup/
│   ├── installation.md      # Local server setup, launchd
│   └── configuration.md     # Environment variables
├── deployment/
│   ├── overview.md          # Platform comparison
│   ├── railway.md           # Railway deployment
│   ├── render.md            # Render deployment
│   └── neon.md              # Neon PostgreSQL
├── apps/
│   └── [App-specific docs]
├── features/
│   └── [Feature documentation]
├── development/
│   ├── codemap.md           # This file
│   ├── changelog.md         # Historical changes
│   ├── refactoring-2025.md  # Earlier refactoring
│   └── repository-restructure-2025.md  # Phases 1-4c
└── todo/
    └── [Future plans]
```

## Recent Changes (2025-10)

### Incremental Lot Update Optimization (2025-10-25)
Complete refactoring of lot generation for 550x performance improvement:

**Architecture:**
- Separated lot structure generation from eBay pricing enrichment
- 3-phase approach: skeleton generation → filtering → selective enrichment
- Phase 1: Build ALL lot skeletons WITHOUT pricing (~0.13s, no eBay API calls)
- Phase 2: Filter to affected lots (~0.00s, simple list comprehension)
- Phase 3: Enrich ONLY affected lots with pricing (~0.00-2s, 0-3 eBay API calls)

**Performance:**
- Accept operations: 77s → 0.14s (550x faster)
- eBay API calls: 122 → 0-1 per accept (99.4% reduction)
- Updated lots: 122 → 1-3 per accept (99.4% more efficient)
- Target was 20-40x speedup, achieved 550x

**Code Changes:**
- Split `_compose_lot()` into `_compose_lot_without_pricing()` and `_enrich_lot_with_pricing()`
- Added `fetch_pricing` parameter to `generate_lot_suggestions()`, `build_lots_with_strategies()`, `build_lot_candidates()`
- Created `_enrich_candidates_with_pricing()` helper in service.py
- Refactored `update_lots_for_isbn()` to use 3-phase architecture
- Maintains full backward compatibility (default `fetch_pricing=True`)

**Impact:**
- iOS app can accept books continuously without blocking
- No more 77-second waits after accepting books
- Background tasks no longer cause SQLite locking delays
- Dramatically improved user experience

**Documentation:**
- `docs/INCREMENTAL_LOT_UPDATE_RESULTS.md` – Comprehensive performance analysis
- `docs/LOT_INCREMENTAL_UPDATE_PLAN.md` – Architecture and implementation plan
- `prototypes/incremental_lots_prototype.py` – Proof of concept
- `tests/test_incremental_lot_update.py` – Test suite

See: `docs/INCREMENTAL_LOT_UPDATE_RESULTS.md` for detailed metrics and technical analysis

### Scan History with Location Tracking (2025-10-23)
Complete scan audit trail system with GPS location tracking:

**Backend:**
- New `scan_history` table in SQLite (17 fields, 4 indexes)
- Database methods: `log_scan()`, `get_scan_history()`, `get_scan_locations()`, `get_scan_stats()`
- Service layer: Auto-logging on ACCEPT, manual logging support
- REST API: 4 new endpoints for logging and querying scan history

**iOS:**
- Core Location integration with GPS tracking and reverse geocoding
- `LocationManager.swift` with location caching and permission handling
- Auto-logging REJECT decisions with location data
- `ScanHistoryView.swift` for browsing history with filtering
- Location-based analytics and acceptance rates

**Use Cases:**
- Avoid rescanning the same book
- Track which stores have best acceptance rates
- Remember where valuable books were seen
- "Previously scanned" warnings

See: `SCAN_HISTORY_FEATURE.md`, `IMPLEMENTATION_SUMMARY.md`, `iOS_INTEGRATION_COMPLETE.md`

### Repository Restructure (Phases 1-4c)
Complete cleanup and refactoring with 14 modules moved to `shared/`:

- **Phase 1:** Removed ~198MB vestigial files
- **Phase 2:** Consolidated 21 markdown files into docs/
- **Phase 3:** Organized scripts and tests
- **Phase 4a:** Created shared/ with database.py, models.py
- **Phase 4b:** Moved utils.py, constants.py to shared/
- **Phase 4c:** Moved API clients and series system (9 modules) to shared/

**Result:** Clean architecture with shared business logic, no code duplication, web app independent of desktop code.

See: `docs/development/repository-restructure-2025.md` for complete details

## Key Files to Understand

**Shared Infrastructure:**
1. `shared/database.py` – DatabaseManager (all SQL operations)
2. `shared/models.py` – Data classes
3. `shared/series_integration.py` – Series matching for apps

**Desktop App:**
4. `isbn_lot_optimizer/service.py` – Main business logic (130KB)
5. `isbn_lot_optimizer/gui.py` – Tkinter GUI (153KB)

**Web App:**
6. `isbn_web/main.py` – FastAPI entry
7. `isbn_web/api/routes/books.py` – Book API

**iOS App:**
8. `LotHelperApp/LotHelper/ScannerReviewView.swift` – Scanner

## Support

- **Documentation:** `docs/README.md` (if it exists, or browse `docs/`)
- **Configuration:** `docs/setup/configuration.md`
- **Deployment:** `docs/deployment/overview.md`
- **Development:** `.mdc` file for AI assistant context
- **Issues/TODOs:** Check `docs/todo/` files

---

**Note:** After the repository restructure, many modules previously in `isbn_lot_optimizer/` are now in `shared/`. Always import shared business logic from `shared.*`, not `isbn_lot_optimizer.*`.
