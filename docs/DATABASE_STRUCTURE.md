# Database Structure Documentation

**Last Updated**: November 7, 2025
**Author**: Database Cleanup & Optimization Project

---

## Overview

The ISBN Lot Optimizer uses **3 active SQLite databases** to manage book inventory, training data, and deduplication tracking. This document describes the official database architecture after cleanup and consolidation in November 2025.

---

## Official Databases

### 1. catalog.db
**Location**: `~/.isbn_lot_optimizer/catalog.db`

**Purpose**: Active book inventory - books you currently own or are scanning

**Primary Table**: `books`

**Schema Highlights**:
```sql
CREATE TABLE books (
    isbn TEXT PRIMARY KEY,
    title TEXT,
    authors TEXT,
    publication_year INTEGER,
    condition TEXT,

    -- ML Predictions
    estimated_price REAL,
    probability_label TEXT,        -- 'HIGH', 'MEDIUM', 'LOW'
    probability_score REAL,

    -- Market Data
    ebay_active_count INTEGER,
    ebay_sold_count INTEGER,
    sold_comps_count INTEGER,
    sold_comps_median REAL,

    -- Book Attributes (user-selected)
    cover_type TEXT,               -- 'Hardcover', 'Paperback', 'Mass Market'
    signed INTEGER DEFAULT 0,      -- 0/1 boolean
    printing TEXT,                 -- '1st', '2nd', etc.

    -- JSON Blobs
    metadata_json TEXT,
    market_json TEXT,
    bookscouter_json TEXT,

    -- User Status
    status TEXT DEFAULT 'ACCEPT',   -- 'ACCEPT', 'REJECT', 'SKIP'

    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    market_fetched_at TEXT,
    ...
);
```

**Additional Tables**:
- `lots`: Lot configurations for eBay listings
- `scan_history`: Historical scan records
- `series_peers`: Series information for books
- `sold_listings`: Individual eBay sold listings with parsed attributes

**Who Uses It**:
- iOS scanning app
- Web API (`isbn_web`)
- BookService (`isbn_lot_optimizer/service.py`)

**Data Lifecycle**:
- Can be deleted and rebuilt without losing training data
- Primary source of user decisions (ACCEPT/REJECT)
- Synced to metadata_cache.db via organic growth system

---

### 2. metadata_cache.db
**Location**: `~/.isbn_lot_optimizer/metadata_cache.db`

**Purpose**: Unified ML training database (Nov 2025 migration)

**Primary Table**: `cached_books`

**Schema Highlights**:
```sql
CREATE TABLE cached_books (
    isbn TEXT PRIMARY KEY,
    title TEXT,
    authors TEXT,
    publisher TEXT,
    publication_year INTEGER,
    binding TEXT,
    page_count INTEGER,

    -- Market Data (added Nov 2025)
    estimated_price REAL,
    sold_comps_count INTEGER,
    sold_comps_median REAL,
    market_json TEXT,
    bookscouter_json TEXT,

    -- Book Attributes (added Nov 2025)
    cover_type TEXT,
    signed INTEGER DEFAULT 0,
    printing TEXT,

    -- Training Quality Tracking (added Nov 2025)
    training_quality_score REAL DEFAULT 0.0,
    in_training INTEGER DEFAULT 0,   -- Quality gate flag
    market_fetched_at TEXT,
    metadata_fetched_at TEXT,
    last_enrichment_at TEXT,

    -- Metadata
    quality_score REAL DEFAULT 0.0,
    source TEXT,                     -- 'google_books', 'openlibrary', etc.
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    ...
);
```

**Who Uses It**:
- ML training scripts (`scripts/train_price_model.py`)
- Organic growth system (`shared/organic_growth.py`)
- MetadataCacheDB class (`isbn_lot_optimizer/metadata_cache_db.py`)

**Data Lifecycle**:
- **SOURCE OF TRUTH** for ML training - cannot be deleted
- Automatically enriched via organic growth system
- Training-eligible books marked with `in_training=1`
- Quality score thresholds: `training_quality_score >= 0.5` for eligibility

**Current Stats** (as of Nov 7, 2025):
- Total ISBNs: 19,384
- Training-eligible: 72 books (with `in_training=1`)
- Avg training quality score: 0.841

---

### 3. unified_index.db
**Location**: `~/.isbn_lot_optimizer/unified_index.db`

**Purpose**: Deduplication tracker - prevents duplicate API calls

**Primary Table**: `isbn_index`

**Schema**:
```sql
CREATE TABLE isbn_index (
    isbn TEXT PRIMARY KEY,
    in_training INTEGER DEFAULT 0,   -- Indexed for training
    in_cache INTEGER DEFAULT 0,       -- Indexed for metadata cache
    last_checked TEXT,                -- Last staleness check
    is_stale INTEGER DEFAULT 0,       -- Needs refresh
    ...
);
```

**Who Uses It**:
- Unified index manager (`isbn_lot_optimizer/unified_index.py`)
- Collection scripts to avoid duplicate enrichments

**Data Lifecycle**:
- Derived from catalog.db + metadata_cache.db
- Periodically resynced (weekly recommended)
- Prevents wasted API costs

---

## Deprecated/Archived Databases

### training_data.db ❌ DEPRECATED
**Status**: Archived November 7, 2025
**Location**: `~/backups/isbn_databases_archived/training_data_archived_*.db`

**Migration**: All 177 records migrated to metadata_cache.db (38 missing ISBNs added)

**Why Deprecated**:
- Nov 2025 unification moved training data to metadata_cache.db
- Single source of truth simplifies architecture
- Backward compatibility removed from training scripts

---

## Database Relationships & Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     USER SCANS ISBN                         │
│                    (iOS App / Web)                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              1. SAVE TO catalog.db                          │
│         (DatabaseManager.upsert_book)                       │
│   - Active inventory                                        │
│   - User decisions (ACCEPT/REJECT/SKIP)                     │
│   - Real-time market data                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│       2. AUTO-SYNC TO metadata_cache.db                     │
│   (OrganicGrowthManager.sync_book_to_training_db)          │
│   - IF organic_growth enabled                               │
│   - Syncs metadata + market data                            │
│   - Calculates training_quality_score                       │
│   - Sets in_training flag                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│         3. CHECK unified_index.db                           │
│   - Deduplication tracking                                  │
│   - Prevents duplicate enrichments                          │
│   - Tracks staleness                                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│       4. ML TRAINING PIPELINE                               │
│   (scripts/train_price_model.py)                            │
│   PRIMARY SOURCE: metadata_cache.db (in_training=1)         │
│   SECONDARY: catalog.db (recent scans)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Schema Comparison

### Shared Fields (in both catalog.db and metadata_cache.db)

| Field | catalog.db | metadata_cache.db | Notes |
|-------|-----------|------------------|-------|
| isbn | ✓ | ✓ | Primary key |
| title | ✓ | ✓ | |
| authors | ✓ | ✓ | |
| publication_year | ✓ | ✓ | |
| cover_type | ✓ | ✓ | |
| signed | ✓ | ✓ | |
| printing | ✓ | ✓ | |
| sold_comps_median | ✓ | ✓ | Target variable for ML |
| sold_comps_count | ✓ | ✓ | |
| market_json | ✓ | ✓ | eBay market data |
| bookscouter_json | ✓ | ✓ | Amazon pricing |

### Catalog-Only Fields

| Field | Purpose |
|-------|---------|
| status | User decision (ACCEPT/REJECT/SKIP) |
| probability_label | ML prediction for user |
| probability_reasons | Explainable AI output |
| abebooks_min_price | AbeBooks pricing |
| abebooks_avg_price | AbeBooks pricing |
| source_json | Collection source info |

### Metadata Cache-Only Fields

| Field | Purpose |
|-------|---------|
| training_quality_score | Training eligibility score (0-1) |
| in_training | Boolean flag for training set |
| binding | Book format from metadata APIs |
| language | Language code |
| isbn13 / isbn10 | Alternate ISBN formats |
| thumbnail_url | Cover image URL |
| description | Book description |
| publisher | Publisher name |

---

## Training Data Quality Gates

Books are marked as training-eligible (`in_training=1`) when they meet these criteria:

1. **Minimum Sold Comps**: `sold_comps_count >= 8`
2. **Price Threshold**: `sold_comps_median >= $5`
3. **Quality Score**: `training_quality_score >= 0.5`
4. **Market Data Present**: `market_json IS NOT NULL`

**Quality Score Calculation** (weights):
- Has market data: 30%
- Has metadata: 20%
- Sold comps count: 25%
- Price value: 15%
- Attribute completeness: 10%

---

## Data Freshness Guidelines

### Market Data
- **Refresh Interval**: 30 days
- **Staleness Check**: Run `stale_data_alert.sh` daily
- **Priority**: Books with `sold_comps_median > $15` refreshed first

### Metadata
- **Refresh Interval**: 90 days
- **Staleness Tolerance**: Lower priority than market data

---

## Monitoring & Maintenance

### Automated Scripts

1. **Weekly Training Report** (`weekly_training_report.sh`)
   - Schedule: Mondays at 9am
   - Tracks: Record counts, quality scores, feature completeness
   - Run: `crontab -e` → `0 9 * * MON ~/ISBN/scripts/monitoring/weekly_training_report.sh`

2. **Stale Data Alert** (`stale_data_alert.sh`)
   - Schedule: Daily at 6am
   - Alerts when >20% training data is stale
   - Run: `crontab -e` → `0 6 * * * ~/ISBN/scripts/monitoring/stale_data_alert.sh`

3. **Schema Consistency Check** (`schema_consistency_check.sh`)
   - Schedule: Sundays at 7am
   - Verifies shared fields stay in sync
   - Run: `crontab -e` → `0 7 * * SUN ~/ISBN/scripts/monitoring/schema_consistency_check.sh`

### Manual Diagnostics

```bash
# Run comprehensive diagnostics
./scripts/monitoring/database_diagnostics.sh

# Check specific database stats
sqlite3 ~/.isbn_lot_optimizer/metadata_cache.db "SELECT COUNT(*) FROM cached_books WHERE in_training=1"

# Find books needing enrichment
sqlite3 ~/.isbn_lot_optimizer/metadata_cache.db "SELECT isbn, title FROM cached_books WHERE in_training=1 AND cover_type IS NULL LIMIT 10"
```

---

## Database Cleanup (November 2025)

### Removed Duplicates

The following duplicate/empty databases were removed:

```
/Users/nickcuskey/ISBN/catalog.db (empty)
/Users/nickcuskey/ISBN/isbn_catalog.db (empty)
/Users/nickcuskey/ISBN/isbn_optimizer.db (empty)
/Users/nickcuskey/ISBN/training_data.db (empty)
/Users/nickcuskey/ISBN/metadata_cache.db (0 records)
/Users/nickcuskey/ISBN/isbn_lot_optimizer/books.db (empty)
/Users/nickcuskey/ISBN/isbn_lot_optimizer/catalog.db (empty)
/Users/nickcuskey/ISBN/isbn_lot_optimizer/training.db (empty)
/Users/nickcuskey/ISBN/isbn_lot_optimizer/metadata_cache.db (0 records)
/Users/nickcuskey/ISBN/isbn_lot_optimizer/data/catalog.db (empty)
```

**Result**: From 183 total .db files → 3 official databases (+ 172 backups)

### Backups

All backups stored in:
- `~/backups/isbn_databases_cleanup_*/` - Cleanup backups
- `~/.isbn_lot_optimizer/backups/` - Hourly/periodic backups (172 files)

**Cleanup Recommendation**: Archive backups older than 30 days

---

## Best Practices

### For Developers

1. **Always use official locations**: `~/.isbn_lot_optimizer/*.db`
2. **Never create .db files in project directory** - use official locations
3. **Sync shared fields**: When adding fields to catalog.db, add to metadata_cache.db too
4. **Test schema changes**: Run `schema_consistency_check.sh` after schema modifications

### For Data Collection

1. **Organic growth enabled**: Books automatically sync from catalog.db → metadata_cache.db
2. **Enrichment priority**: Focus on training-eligible books first (`in_training=1`)
3. **Avoid duplicates**: Check unified_index.db before enriching

### For ML Training

1. **Primary source**: metadata_cache.db with `in_training=1`
2. **Quality filter**: Use `training_quality_score >= 0.6` for high-quality subset
3. **Feature completeness**: Check with `weekly_training_report.sh`
4. **Stale data**: Refresh before training if >20% stale

---

## Troubleshooting

### "Database is locked" errors
```bash
# Check for stale connections
lsof | grep isbn_lot_optimizer

# Restart web server
pkill -f "uvicorn isbn_web"
```

### ISBNs not syncing to metadata_cache.db
```bash
# Check organic growth is enabled
grep "organic_growth" shared/constants.py

# Manual sync
python3 scripts/maintenance/sync_catalog_to_cache.py
```

### Training data quality degrading
```bash
# Run diagnostics
./scripts/monitoring/weekly_training_report.sh

# Identify issues
./scripts/monitoring/stale_data_alert.sh

# Bulk refresh stale data
python3 scripts/refresh_stale_market_data.py --days 30 --limit 100
```

---

## References

- [DATABASE_UNIFIED_ARCHITECTURE_2025.md](./DATABASE_UNIFIED_ARCHITECTURE_2025.md) - Original unification plan
- [shared/database.py](../shared/database.py) - DatabaseManager class
- [isbn_lot_optimizer/metadata_cache_db.py](../isbn_lot_optimizer/metadata_cache_db.py) - MetadataCacheDB class
- [scripts/monitoring/](../scripts/monitoring/) - Monitoring scripts

---

## Changelog

**November 7, 2025** - Database Cleanup & Optimization
- Removed 10 duplicate/empty databases
- Migrated 38 ISBNs from training_data.db → metadata_cache.db
- Archived training_data.db
- Created 3 monitoring scripts
- Documented official 3-database architecture
