# Scripts Directory

Maintenance scripts and utilities for the ISBN Lot Optimizer.

---

## Data Management Scripts

### scrape_bookseries_org.py

Scrapes book series data from bookseries.org.

**Purpose:** Collect comprehensive series metadata for matching against scanned books.

**Usage:**
```bash
python scripts/scrape_bookseries_org.py --output data/bookseries_complete.json
```

**Output:** JSON file with authors, series, and books (~11MB)

**Options:**
- `--output` - Output file path (default: bookseries_complete.json)
- `--delay` - Delay between requests in seconds (default: 1.0)

**See:** [scripts/README_bookseries_scraper.md](README_bookseries_scraper.md) for details

---

### import_series_data.py

Imports scraped series data into the database.

**Purpose:** Load bookseries.org data into catalog.db for series matching.

**Usage:**
```bash
python scripts/import_series_data.py \
  --json-file data/bookseries_complete.json \
  --db ~/.isbn_lot_optimizer/catalog.db
```

**Options:**
- `--json-file` - Path to scraped JSON (default: bookseries_complete.json)
- `--db` - Database path (default: books.db)
- `--clear` - Clear existing series data before importing

**Result:** Populates `authors`, `series`, `series_books` tables

---

### match_books_to_series.py

Matches existing books in database to series.

**Purpose:** Link scanned books to their series using fuzzy matching.

**Usage:**
```bash
python scripts/match_books_to_series.py \
  --db ~/.isbn_lot_optimizer/catalog.db \
  --auto-save-threshold 0.9
```

**Options:**
- `--db` - Database path (default: ~/.isbn_lot_optimizer/catalog.db)
- `--auto-save-threshold` - Auto-save confidence threshold (default: 0.9)
- `--limit` - Limit number of books to process

**Result:** Updates `book_series_matches` table with matches

---

### prefetch_covers.py

Pre-fetches book cover thumbnails.

**Purpose:** Download and cache cover images to speed up GUI/web display.

**Usage:**
```bash
python scripts/prefetch_covers.py
```

**Behavior:**
- Reads books from `~/.isbn_lot_optimizer/catalog.db`
- Downloads covers from Google Books / Open Library
- Saves to `~/.isbn_lot_optimizer/covers/`
- Uses SHA-256 filenames for deduplication

---

## Validation Scripts

### verify_series_lots.py

Verifies series lot generation works correctly.

**Purpose:** Test series-based lot generation with sample data.

**Usage:**
```bash
python scripts/verify_series_lots.py
```

**Tests:**
- Series lot generation
- Completion tracking
- Lot naming conventions
- Have/missing book lists

---

### test_series_lots.py

Tests the series lots feature end-to-end.

**Purpose:** Integration test for series lot generation.

**Usage:**
```bash
python scripts/test_series_lots.py
```

**Tests:**
- Database setup
- Series matching
- Lot generation
- Completion calculations

---

## Utility Scripts

### utils/sync_to_isbn.sh

Syncs changes to ISBN deployment directory.

**Purpose:** Copy updated files from development to deployment directory.

**Usage:**
```bash
./scripts/utils/sync_to_isbn.sh
```

**Syncs:**
- Web templates
- API routes
- Service layer
- Restarts isbn-web server

**Note:** Specific to setup with separate deployment directory.

---

### utils/check-token-ssl.sh

Checks SSL certificate status for token broker.

**Purpose:** Verify Cloudflare SSL is active for token broker domain.

**Usage:**
```bash
./scripts/utils/check-token-ssl.sh
```

**Checks:**
- HTTPS connectivity to tokens.lothelper.clevergirl.app
- Certificate details
- Expiry date

---

## Data Files

### bookseries_authors.json

Sample author data from bookseries.org (139KB).

**Purpose:** Testing/development with smaller dataset.

---

### bookseries_sample.json

Small sample of series data (4.7KB).

**Purpose:** Quick testing without full dataset.

---

## Workflow Examples

### Initial Series Setup

```bash
# 1. Scrape bookseries.org
python scripts/scrape_bookseries_org.py --output data/bookseries_complete.json

# 2. Import into database
python scripts/import_series_data.py \
  --json-file data/bookseries_complete.json \
  --db ~/.isbn_lot_optimizer/catalog.db

# 3. Match existing books
python scripts/match_books_to_series.py \
  --db ~/.isbn_lot_optimizer/catalog.db \
  --auto-save-threshold 0.9

# 4. Verify lots generate correctly
python scripts/verify_series_lots.py
```

### Refresh Series Data

```bash
# Re-scrape (if bookseries.org updated)
python scripts/scrape_bookseries_org.py --output data/bookseries_complete.json

# Clear and re-import
python scripts/import_series_data.py \
  --json-file data/bookseries_complete.json \
  --db ~/.isbn_lot_optimizer/catalog.db \
  --clear

# Re-match books
python scripts/match_books_to_series.py
```

### Pre-fetch Covers

```bash
# Download all covers
python scripts/prefetch_covers.py

# Result: Faster GUI/web display
```

---

## Development Notes

- Scripts use `~/.isbn_lot_optimizer/catalog.db` by default
- Can override with `--db` flag
- Most scripts have `--help` for options
- Rate limits respected for external APIs (bookseries.org)
- Safe to re-run (idempotent where possible)

---

## See Also

- [Data Management](../data/README.md) - Data directory documentation
- [Bookseries Scraper Details](README_bookseries_scraper.md) - Scraper deep dive
- [Series Integration](../docs/features/series-integration-temp.md) - Feature documentation
