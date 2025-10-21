# Configuration

Complete guide to configuring the ISBN Lot Optimizer.

---

## Overview

The app uses:
- Local SQLite database (`~/.isbn_lot_optimizer/catalog.db`)
- On-disk caches for covers, tokens, and market data
- Environment variables for API keys and settings
- Auto-loaded `.env` file (python-dotenv)

---

## Database and Caches

### Primary Database
**Location:** `~/.isbn_lot_optimizer/catalog.db`
- Created automatically on first run
- Contains: `books`, `lots`, `series`, `authors`, and related tables

### Cache Directories
- **Covers:** `~/.isbn_lot_optimizer/covers/` - Book cover thumbnails (SHA-256 filenames)
- **eBay tokens:** `~/.isbn_lot_optimizer/ebay_bearer.json` - OAuth bearer token cache
- **Lot market:** `~/.isbn_lot_optimizer/lot_cache.json` - Market snapshot cache
- **Hardcover API:** `hc_cache` table in database - 7-day TTL

---

## Environment Variables

### eBay Integration

#### Finding API (Sold/Unsold History)
```bash
# Finding API App ID for historical sold/unsold data
export EBAY_APP_ID=your-finding-app-id
```

**Features when configured:**
- Sold/unsold counts and prices
- Historical pricing statistics
- Sell-through rates

#### Browse API (Active Listings)
```bash
# Browse API credentials for active marketplace data
export EBAY_CLIENT_ID=your-browse-client-id
export EBAY_CLIENT_SECRET=your-browse-client-secret
export EBAY_MARKETPLACE=EBAY_US  # Optional, default: EBAY_US
```

**Features when configured:**
- Active listing counts
- Current median prices
- Live market intelligence
- OAuth token auto-management

**Supported Marketplaces:**
- `EBAY_US` - United States (default)
- `EBAY_GB` - United Kingdom
- `EBAY_DE` - Germany
- `EBAY_AU` - Australia
- `EBAY_CA` - Canada
- etc.

### Buyback Integration

#### BookScouter (Multi-Vendor - Recommended for GUI)
```bash
# BookScouter API for multi-vendor buyback aggregation
export BOOKSCOUTER_API_KEY=your-bookscouter-api-key

# Optional: Adjust rate limiting (default: 1.1s to stay under 60/min limit)
export BOOKSCOUTER_DELAY=1.1
```

**Features:**
- 14+ vendor quotes (BooksRun, eCampus, Valore, TextbookRush, etc.)
- GUI integration with "Refresh BookScouter" button
- Bulk Buyback Helper optimization tool
- Rate limits: 60 calls/minute, 7000 calls/day

#### BooksRun (CLI Only)
```bash
# BooksRun API for bulk CLI quotes
export BOOKSRUN_KEY=your-booksrun-api-key
export BOOKSRUN_AFFILIATE_ID=your-affiliate-id  # Optional
```

**Note:** GUI now uses BookScouter. BooksRun is only for `lothelper` CLI tool.

### Series Detection

#### Hardcover API
```bash
# Hardcover GraphQL API for series metadata
export HARDCOVER_API_TOKEN=Bearer your-hardcover-token

# Optional: Override endpoint
export HARDCOVER_GRAPHQL_ENDPOINT=https://api.hardcover.app/graphql
```

**Features:**
- Automatic series detection
- Series position tracking
- Peer book discovery
- 7-day cache with 1 req/sec rate limiting

**Get a token:** https://hardcover.app/settings

### Proxy Configuration

```bash
# Route API requests through proxy
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080
```

### Deprecated Variables

For backward compatibility, these old names still work but will show warnings:

```bash
# OLD (deprecated)          # NEW (use instead)
BOOKSRUN_API_KEY            BOOKSRUN_KEY
BOOKSRUN_AFK                BOOKSRUN_AFFILIATE_ID
```

---

## .env File Example

Create `.env` in project root:

```bash
# eBay APIs
EBAY_APP_ID=YourApp-FindingA-PRD-1234567890
EBAY_CLIENT_ID=YourApp-BrowseAP-PRD-9876543210
EBAY_CLIENT_SECRET=PRD-1234567890ab-cd12-ef34-gh56-789012345678
EBAY_MARKETPLACE=EBAY_US

# BookScouter (multi-vendor buyback)
BOOKSCOUTER_API_KEY=your_bookscouter_key_here
BOOKSCOUTER_DELAY=1.1

# BooksRun (CLI bulk quotes)
BOOKSRUN_KEY=your_booksrun_key_here
BOOKSRUN_AFFILIATE_ID=your_affiliate_id

# Hardcover (series detection)
HARDCOVER_API_TOKEN=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Optional proxy
# HTTP_PROXY=http://proxy:8080
# HTTPS_PROXY=http://proxy:8080
```

**Note:** `.env` is auto-loaded on startup. Shell exports override `.env` values.

---

## Feature Configuration

### Hardcover Series Integration

**Purpose:** Detect and persist series metadata using Hardcover's GraphQL API.

**Database Schema:**
- **books table columns:**
  - `series_name` - Series title
  - `series_slug` - URL-friendly slug
  - `series_id_hardcover` - Hardcover series ID
  - `series_position` - Position in series (REAL, supports decimals like 0.5)
  - `series_confidence` - Match confidence (0.0-1.0)
  - `series_last_checked` - Last check timestamp

- **series_peers table:** Stores peer titles for series (ordered by position/title)
- **hc_cache table:** Caches API payloads (7-day TTL)

**Rate Limiting:**
- 1 request/second with burst of 5
- Automatic backoff/retry on HTTP 429

**CLI Usage:**
```bash
# Refresh series for books
python -m isbn_lot_optimizer --refresh-series --limit 500

# Standalone backfill script
python -m isbn_lot_optimizer.scripts.backfill_series \
  --db ~/.isbn_lot_optimizer/catalog.db \
  --limit 500 \
  --only-missing \
  --stale-days 30
```

**GUI Usage:**
- Auto-enrichment after successful scan/import
- Background thread updates database
- Detail pane shows "Series · #position" chip when available

**Notes:**
- Books without series are marked checked to avoid reprocessing
- If token missing, series features are disabled

### BookScouter Integration

**GUI Features:**
- **Refresh Button:** "Refresh BookScouter (All)" updates all books
- **Display:** Shows best offer, vendor count, top 3 offers per book
- **Status Bar:** Real-time updates with book details during refresh
- **Rate Limiting:** 1.1s delay (60 calls/minute compliant)

**Bulk Buyback Helper:**
- **Location:** Tools → Bulk Buyback Helper…
- **Purpose:** Optimize book assignments across vendors
- **Algorithm:** Greedy assignment maximizing total profit
- **Respects:** Vendor minimums ($5-$10 per vendor)
- **Shows:** Bundles per vendor with values and book lists
- **Tracks:** Unassigned books (below minimums or no offers)

**API Details:**
- **Rate limits:** 60 calls/minute, 7000 calls/day
- **Vendors (14+):** BooksRun, eCampus, Valore, TextbookRush, ValoreBooks, SellBackYourBook, BookByte, TextbookRecycling, Powell's Books, Cash4Books, BookDeal, MyBookBuyer, Ziffit, World of Books
- **Storage:** Full vendor data in `bookscouter_json` column

**Requirements:**
- `BOOKSCOUTER_API_KEY` or `apiKey` in environment

### BooksRun CLI Integration

**Purpose:** Direct BooksRun SELL quotes via CLI (not GUI).

**Usage:**
```bash
python -m lothelper booksrun-sell \
  --in isbns.csv \
  --out quotes.csv \
  --format csv \
  --sleep 0.2
```

**Formats:** CSV or Parquet output

**Requirements:**
- `BOOKSRUN_KEY` in environment
- Input CSV with `isbn` column

**Note:** GUI now uses BookScouter instead

### eBay Integration Details

**Finding API:**
- Sold/unsold counts and pricing
- Configured with `EBAY_APP_ID`

**Browse API:**
- Active comps and median pricing
- Configured with `EBAY_CLIENT_ID` + `EBAY_CLIENT_SECRET`
- Bearer tokens cached in `ebay_bearer.json`

**Lot Market Snapshots:**
- Combines Browse active medians + Finding sold medians
- Author/series/theme queries
- Cached in `lot_cache.json`

**Notes:**
- If `EBAY_CLIENT_ID/SECRET` missing: Browse features disabled (warning shown)
- If `EBAY_APP_ID` missing: Sold/unsold stats skipped, Browse may still work
- Dotenv doesn't override existing shell variables

---

## Code-Level Tunables

These settings are configured in the source code:

### Probability Scoring (`probability.py`)

**Single-Item Minimum Price:**
- Books < $10 flagged for bundling
- Sets `suppress_single` and adds negative score
- Suggests combining into lots

**Condition Weights:**
```python
CONDITION_WEIGHTS = {
    "Like New": 1.2,
    "Very Good": 1.0,
    "Good": 0.9,
    "Acceptable": 0.7,
}
```

**Demand Keywords:**
```python
HIGH_DEMAND_KEYWORDS = [
    "harry potter", "tolkien", "signed", "first edition",
    "rare", "collectible", "vintage", # etc.
]
```

**Edition Boosts:**
- "first" or "1st" edition
- "signed" editions
- "limited" editions

### Author Cleanup

**GUI Tool:** Tools → Author Cleanup…

**Features:**
- Interactive cluster-by-cluster review
- Per-cluster approve/reject
- Optional book thumbnails (Pillow + requests)
- Thumbnail cache: `~/.isbn_lot_optimizer/covers/`
- SHA-256 filenames for efficient caching

**Dependencies:**
- Pillow (image support)
- requests (fetching)
- Both in `requirements.txt`

---

## Authentication (Optional)

Add HTTP Basic Auth to web interface:

### 1. Install Dependencies

```bash
pip install python-multipart
```

### 2. Add to `isbn_web/main.py`

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "yourpassword")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    return credentials.username

# Add to routes
@app.get("/", dependencies=[Depends(verify_credentials)])
async def read_root():
    # Your code here
```

### 3. Set Credentials

Store credentials in `.env`:
```bash
WEB_USERNAME=admin
WEB_PASSWORD=your_secure_password_here
```

Then load in code:
```python
import os
correct_username = secrets.compare_digest(
    credentials.username,
    os.getenv("WEB_USERNAME", "admin")
)
correct_password = secrets.compare_digest(
    credentials.password,
    os.getenv("WEB_PASSWORD", "changeme")
)
```

---

## Summary

### Required
- None! App works without any environment variables

### Recommended
- `HARDCOVER_API_TOKEN` - Series detection
- `BOOKSCOUTER_API_KEY` - Multi-vendor buyback quotes
- `EBAY_CLIENT_ID/SECRET` - Live market data

### Optional Enhancement
- `EBAY_APP_ID` - Historical sold data
- `BOOKSRUN_KEY` - CLI bulk quotes
- Proxy settings if needed

### Storage Locations
- **Database:** `~/.isbn_lot_optimizer/catalog.db`
- **Covers:** `~/.isbn_lot_optimizer/covers/`
- **Tokens:** `~/.isbn_lot_optimizer/ebay_bearer.json`
- **Cache:** `~/.isbn_lot_optimizer/lot_cache.json`

---

**Next:** [Installation Guide](installation.md) | [Deployment Options](../deployment/overview.md)
