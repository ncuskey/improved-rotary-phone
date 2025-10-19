# Improved Rotary Phone (ISBN Lot Optimizer)

Improved Rotary Phone—formerly LotHelper—is a desktop, CLI, and web toolkit for
cataloguing second-hand books, estimating resale value, and assembling
profitable eBay lots. The application includes a Tkinter GUI, FastAPI web interface,
and background service that persists scans, retrieves market intelligence, and updates
lot recommendations in real time.

## Highlights
- **Multi-Interface Support**: Tkinter desktop GUI, FastAPI web interface, and CLI tools
- **3D Interactive Carousel**: Beautiful lot details page with 3D book carousel featuring real book covers
- **Mobile Camera Scanner**: Smartphone camera integration for ISBN scanning (OCR working, barcode scanning in progress)
- **Database Statistics**: Comprehensive metrics showing storage usage, API efficiency, data coverage, and freshness
- **Smart Series Detection**: Hardcover API integration with caching and intelligent rate limiting
- **Amazon Sales Rank**: BookScouter integration with batch refresh and probability scoring
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

## Mobile Camera Scanner & iOS App

The web interface includes a mobile-optimized camera scanner for ISBN detection, and a native iOS app provides full barcode scanning with real-time eBay pricing:

### Web Scanner
- **✅ OCR Text Recognition**: Successfully extracts ISBNs from book cover text
- **❌ Barcode Scanning**: Currently not working (see `CAMERA_SCANNER_TODO.md`)
- **📱 Mobile-First Design**: Optimized for smartphone use
- **🔄 Fallback Options**: Manual input when camera fails

**Status**: OCR functionality is working well, but barcode scanning needs fixes. See `CAMERA_SCANNER_README.md` for detailed documentation and `CAMERA_SCANNER_TODO.md` for known issues and next steps.

### iOS App (LotHelper)
- **✅ Dual Input Modes**:
  - Camera mode with native barcode scanning, OCR text recognition, and tap-to-focus
  - Text entry mode for Bluetooth barcode scanners with auto-focus workflow
  - Auto-refocuses after every scan (success or error) for hands-free operation
  - Toggle between modes via toolbar, preference persists
- **📊 Full-Screen Analysis View**: Complete transparency into decision-making:
  - Camera disappears after scan to maximize analysis space
  - Accept/Reject buttons at very top (no scrolling needed)
  - Buy/Don't Buy advice immediately visible
  - Confidence score breakdown with all justification reasons
  - Data source attribution (eBay live, BookScouter, backend estimates)
  - Decision factors section explaining why BUY or DON'T BUY
  - Market intelligence with rarity, categories, author, publisher
- **💰 eBay Fee-Based Profit Analysis**:
  - Accurate net profit after eBay fees (13.25% + $0.30)
  - Shipping not deducted (buyer pays shipping in our store)
  - Two-path comparison: eBay Route vs Buyback Route
  - Complete breakdown: Sale → Fees → Cost → Net
  - Uses live eBay median pricing when available
  - Shows "(Live)" or "(Est.)" indicator for price transparency
- **💵 Smart Profit Calculator**:
  - Set price once with $0.25 increment picker ($0.00 - $50.00)
  - Works with $0 (free books from donations, estate sales)
  - Price persists across all scans for batch purchasing
  - Buyback-first priority: Any positive buyback = instant BUY
  - Shows vendor name: "Guaranteed $X.XX profit via VendorName"
- **🎯 Intelligent Buy Logic**:
  - RULE 1: Buyback profit > $0 → BUY (zero risk, guaranteed)
  - RULE 2: eBay net profit ≥ $10 → BUY (strong)
  - RULE 3: Net $5-10 → Conditional (needs high confidence)
  - Ignores confidence scores when buyback profit exists
- **⚡ Always-Ready Scanning**: Continuous rapid scanning without button taps
  - Auto-accepts previous BUY when new scan arrives
  - Auto-rejects previous DON'T BUY when new scan arrives
  - Perfect for high-volume scanning sessions
- **✅ Accept/Reject Workflow**: Make informed keep/reject decisions with full analysis
- **🚀 Professional Launch**: Branded splash screen with loading status updates
- **🔒 Secure Token Management**: eBay OAuth tokens handled server-side via token broker
- **📱 Modern SwiftUI**: Beautiful, accessible interface with haptic feedback and sound effects
- **🔊 Custom Audio Feedback**: Custom cash register sound for BUY recommendations
- **🔄 Seamless Integration**: Syncs with backend catalog via REST API

**eBay Token Broker**: A lightweight Node.js service (`token-broker/`) provides OAuth tokens to the iOS app, keeping your eBay Production credentials secure on the server. Auto-starts with `isbn` or `isbn-web` commands.

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
   export EBAY_CLIENT_ID=your-browse-client-id         # Browse API (active comps) + Token Broker
   export EBAY_CLIENT_SECRET=your-browse-client-secret # Token Broker
   export EBAY_MARKETPLACE=EBAY_US                     # Optional (default: EBAY_US)

   # BooksRun (for SELL quotes)
   export BOOKSRUN_KEY=your-booksrun-api-key

   # BookScouter (for multi-vendor quotes and Amazon rank)
   export BOOKSCOUTER_API_KEY=your-bookscouter-api-key

   # Hardcover API (for series metadata)
   export HARDCOVER_API_TOKEN=your-hardcover-jwt-token  # Get from hardcover.app settings

   # Optional proxy settings
   export HTTP_PROXY=http://proxy:8080
   export HTTPS_PROXY=http://proxy:8080
   ```

   **Token Broker**: The eBay token broker (`token-broker/`) auto-starts when you run `isbn` or `isbn-web`. It provides OAuth tokens to the iOS app on port 8787. No additional setup required—just set `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` in `.env`.

3. Launch the application:
   
   **Desktop GUI:**
   ```bash
   python -m isbn_lot_optimizer
   ```
   - Scan or type an ISBN, choose a condition, and press Enter. The app persists
     the book, runs metadata + market lookups, refreshes lot recommendations,
     and updates the status bar as background jobs complete.
   - If `EBAY_CLIENT_ID/EBAY_CLIENT_SECRET` are missing, Browse API features are disabled (a warning is printed).
   - Finding API sold/unsold stats are used when `EBAY_APP_ID` is present.
   
   **Web Interface:**
   ```bash
   uvicorn isbn_web.main:app --reload
   ```
   - Navigate to `http://localhost:8000` for the web dashboard
   - Features a modern, responsive interface with:
     - Book scanning and catalog management
     - Interactive lot generation and optimization
     - **3D Book Carousel**: Beautiful lot details page with real book covers
     - HTMX-powered dynamic updates without page refreshes
     - Alpine.js for interactive components

   **Mobile / API integrations:**
   - `POST /isbn` – Scan-or-return core metadata for a single ISBN; the backend will
     persist a fresh scan when the book is missing.
   - `GET /api/books/all` – JSON payload of every stored book (matches GUI list order).
   - `GET /api/lots/list.json` – JSON payload of the saved lot suggestions, including
     embedded book metadata when available.
   - These endpoints power the LotHelper iOS prototype; restart `isbn-web` after
     deploying changes so the routes are reloaded.
   - **iOS UI tip:** ship a minimal `LaunchScreen.storyboard` (white `systemBackground`
     fill) and keep `UIWindow.appearance().backgroundColor = .systemBackground` so the
     app renders flush with the device safe areas instead of letterboxing on hardware.

## 3D Book Carousel

The web interface features a stunning 3D interactive carousel for viewing lot details:

### Features
- **Real Book Covers**: Displays actual book cover thumbnails from Open Library
- **3D Perspective**: Books arranged in a 3D arc with perspective transforms
- **Interactive Navigation**: 
  - Mouse wheel scrolling when hovering
  - Click on any book to navigate
  - Arrow buttons and progress dots
  - Smooth transitions and animations
- **Smart Fallbacks**: Graceful degradation to gradient covers if thumbnails fail to load
- **Color-coded Conditions**: Visual condition badges with appropriate colors
- **Responsive Design**: Works on desktop and mobile devices

### Usage
1. Start the web server: `uvicorn isbn_web.main:app --reload`
2. Navigate to the lots page and click on any lot
3. Click "View Full Details" to see the 3D carousel
4. **Desktop**: Use mouse wheel, click navigation, or arrow buttons to browse books
5. **Mobile**: Swipe left/right to navigate, or use touch-friendly arrow buttons

### Mobile Features
- **Touch Gestures**: Swipe left/right to navigate through books
- **Responsive Design**: Optimized layout for mobile screens
- **Touch-Friendly UI**: 44px minimum touch targets for accessibility
- **Performance Optimized**: Reduced 3D complexity for mobile GPUs
- **Progressive Enhancement**: Works on all devices with graceful degradation

### Technical Stack
- **FastAPI**: Backend API with Jinja2 templates
- **Alpine.js**: Reactive UI components and state management
- **HTMX**: Dynamic updates without page refreshes
- **Tailwind CSS**: Modern, utility-first styling with responsive design
- **CSS 3D Transforms**: Smooth 3D animations and perspective
- **Touch Gestures**: Mobile-optimized swipe navigation
- **Progressive Enhancement**: Works on desktop and mobile devices

### Troubleshooting

#### "Lot not found" Error
If you see "Lot not found" when clicking on lots:
- Ensure the lots table template uses `{{ lot.id }}` instead of `{{ loop.index0 }}`
- Check that the route `/api/lots/{lot_id}` is working correctly
- Verify JSON feeds for mobile clients:
  - `curl http://localhost:8000/api/books/all`
  - `curl http://localhost:8000/api/lots/list.json`

#### Carousel Not Loading
If the 3D carousel doesn't appear:
- Verify Alpine.js is loaded: Check browser console for `window.Alpine`
- Ensure the `carouselData()` function exists in `base.html`
- Check that `window.lotBooksData` is populated in the page source
- Restart the server to pick up template changes

#### Mobile Issues
If the carousel has issues on mobile devices:
- **Cards positioned incorrectly**: Check if mobile transforms are being applied (console logs)
- **Swipe not working**: Verify touch events are bound and check console for touch logs
- **Performance issues**: Mobile uses reduced 3D complexity for better performance
- **Viewport issues**: Ensure proper mobile viewport meta tag is present

#### Deployment Synchronization
The `isbn-web` shortcut uses a separate directory (`/Users/nickcuskey/ISBN`):
- **Automated sync**: Run `./sync_to_isbn.sh` to sync all changes automatically
- **Manual sync**: Copy updated files from development to deployment directory
- Key files to sync: `base.html`, `lot_details.html`, `lots_table.html`, `lots.py`, `service.py`
- Restart the server after synchronization

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

# Database statistics and monitoring
python -m isbn_lot_optimizer --no-gui --stats  # Comprehensive database metrics

# Series metadata refresh (Hardcover API)
python -m isbn_lot_optimizer --no-gui --refresh-series --limit 100

# Amazon rank refresh (BookScouter API)
python -m isbn_lot_optimizer --no-gui --refresh-amazon-ranks --limit 100
python -m isbn_lot_optimizer --no-gui --refresh-amazon-ranks --force-refresh-amazon

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

## Series Enrichment (Hardcover)

The app integrates Hardcover’s GraphQL search to detect and persist series information.

- Environment:
  - Set HARDCOVER_API_TOKEN to your Hardcover API token (include the "Bearer " prefix).
    - Example in .env:
      HARDCOVER_API_TOKEN=Bearer YOUR_TOKEN
- Persistence:
  - books table gains: series_name, series_slug, series_id_hardcover, series_position (REAL, preserves decimals like 0.5), series_confidence, series_last_checked.
  - series_peers table stores peer titles for a detected series (ordered by position when available, else title).
  - hc_cache caches API payloads (7 day TTL) to reduce repeat calls.
- Rate limiting and retries:
  - 1 request/second with burst of 5. Automatic backoff/retry on HTTP 429.
- GUI:
  - After a successful scan/import, a background thread enriches series for the new records and updates the DB; the detail pane can show a chip like “Series · #position” when available.
- CLI:
  - Inline refresh from the main entrypoint:
    python -m isbn_lot_optimizer --refresh-series --limit 500
  - Standalone backfill script:
    python -m isbn_lot_optimizer.scripts.backfill_series --db ~/.isbn_lot_optimizer/catalog.db --limit 500 --only-missing --stale-days 30

Tip: If a book has no series in Hardcover, series_confidence remains 0 and series_last_checked is set so it won’t be reprocessed immediately.

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
- Source lives in `isbn_lot_optimizer/`, `lothelper/`, and `isbn_web/`; see `CODEMAP.md` for an overview.
- **Web Interface**: FastAPI application in `isbn_web/` with modern frontend stack
- Quick syntax check:
  ```bash
  python -m py_compile isbn_lot_optimizer/*.py
  python -m py_compile isbn_web/*.py
  ```
- Tests (pytest):
  ```bash
  pytest -q
  ```
- The GUI uses background threads for long-running operations. Any new service
  hooks should report progress through `_start_progress`, `_update_progress`,
  and `_finish_progress` to keep the status bar accurate.
- **Web Development**: The web interface uses HTMX for dynamic updates and Alpine.js for reactive components.

## Licensing
This repository currently ships without an explicit licence. Add one before
publishing binaries or distributing widely.
