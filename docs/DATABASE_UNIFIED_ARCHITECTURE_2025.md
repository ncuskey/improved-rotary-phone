# Unified Database Architecture - November 2025

## Overview

This document describes the unified database architecture implemented in November 2025, which consolidates training data into `metadata_cache.db` as a single source of truth for ML training.

## Key Changes

### Before
- **catalog.db**: Main inventory database
- **metadata_cache.db**: Lightweight metadata only (no market data)
- **training_data.db**: Separate high-quality training examples
- **Fragmentation**: Data spread across multiple databases

### After
- **catalog.db**: Active inventory (current books you own)
- **metadata_cache.db**: **Unified training database** (all historical ISBNs + market data)
- **Organic Growth**: Every scan automatically enriches training database
- **Single Source of Truth**: All ML training reads from metadata_cache.db

## Database Schemas

### metadata_cache.db (Unified Training Database)

**Table**: `cached_books` (43 columns)

#### Core Metadata (16 columns)
```sql
isbn TEXT PRIMARY KEY
title TEXT
authors TEXT
publisher TEXT
publication_year INTEGER
binding TEXT                  -- Hardcover, Paperback, Mass Market
page_count INTEGER
language TEXT
isbn13 TEXT
isbn10 TEXT
thumbnail_url TEXT
description TEXT
source TEXT                   -- google_books, openlibrary, decodo, etc.
created_at TEXT
updated_at TEXT
quality_score REAL            -- 0-1 metadata completeness score
```

#### Market Data (19 columns) **NEW**
```sql
-- Price fields
estimated_price REAL
price_reference REAL
rarity REAL

-- Probability/quality
probability_label TEXT        -- 'HIGH', 'MEDIUM', 'LOW'
probability_score REAL        -- 0.0 to 1.0

-- eBay market data
sell_through REAL
ebay_active_count INTEGER
ebay_sold_count INTEGER
ebay_currency TEXT DEFAULT 'USD'

-- Sold comps statistics
time_to_sell_days INTEGER
sold_comps_count INTEGER
sold_comps_min REAL
sold_comps_median REAL
sold_comps_max REAL
sold_comps_is_estimate INTEGER DEFAULT 0
sold_comps_source TEXT

-- JSON blobs for rich data
market_json TEXT              -- Full eBay market data
booksrun_json TEXT            -- BooksRun buyback offers
bookscouter_json TEXT         -- Amazon/BookScouter pricing
```

#### Book Attributes (3 columns) **NEW**
```sql
cover_type TEXT               -- 'Hardcover', 'Paperback', 'Mass Market'
signed INTEGER DEFAULT 0      -- 1=signed, 0=unsigned
printing TEXT                 -- '1st', '2nd', '3rd', etc.
```

#### Training Quality Tracking (5 columns) **NEW**
```sql
training_quality_score REAL DEFAULT 0.0   -- 0-1 composite quality score
in_training INTEGER DEFAULT 0             -- 1=eligible for training, 0=not eligible

-- Staleness tracking
market_fetched_at TEXT        -- Last eBay market data fetch
metadata_fetched_at TEXT      -- Last metadata refresh
last_enrichment_at TEXT       -- Last enrichment run
```

#### Indexes
```sql
-- Original indexes
CREATE INDEX idx_cached_books_isbn13 ON cached_books(isbn13)
CREATE INDEX idx_cached_books_isbn10 ON cached_books(isbn10)
CREATE INDEX idx_cached_books_source ON cached_books(source)
CREATE INDEX idx_cached_books_quality ON cached_books(quality_score)

-- NEW indexes for training
CREATE INDEX idx_training_quality ON cached_books(training_quality_score DESC)
CREATE INDEX idx_in_training ON cached_books(in_training)
CREATE INDEX idx_sold_comps_count ON cached_books(sold_comps_count DESC)
CREATE INDEX idx_sold_comps_median ON cached_books(sold_comps_median DESC)
CREATE INDEX idx_market_fetched ON cached_books(market_fetched_at)
CREATE INDEX idx_cover_type ON cached_books(cover_type)
CREATE INDEX idx_signed ON cached_books(signed)
```

### catalog.db (Active Inventory)

**Table**: `books` (similar schema to metadata_cache.db)

This database contains:
- Books you currently own
- Active inventory for selling
- Real-time market data
- User decisions (ACCEPT/REJECT/SKIP)

**Note**: catalog.db can be deleted and recreated fresh without losing training data, since all historical ISBNs are preserved in metadata_cache.db.

## Quality Gates for Training

Books are marked `in_training = 1` when they meet these criteria:

### Training Quality Score Calculation
```python
def calculate_training_quality_score(book_data):
    score = 0.0

    # eBay comp quality (0-70 points)
    if book_data.get('sold_comps_count', 0) >= 20:
        score += 0.7
    elif book_data.get('sold_comps_count', 0) >= 8:
        score += 0.4

    # Price threshold (0-30 points)
    median_price = book_data.get('sold_comps_median', 0)
    if median_price >= 15:
        score += 0.3
    elif median_price >= 5:
        score += 0.15

    return score

# Set in_training = 1 if score >= 0.6
```

### Criteria
- **Minimum eBay comps**: 8 sold listings
- **Minimum price**: $5 median sold price
- **Minimum quality score**: 0.6 (out of 1.0)

## Organic Growth System

### Data Flow

```
1. USER SCANS ISBN
   ↓
2. SCAN → catalog.db (active inventory)
   ↓
3. AUTO-SYNC → metadata_cache.db (training database)
   ↓
4. CHECK UNIFIED_INDEX (deduplication)
   ↓
5. ENRICH (if needed):
   - Metadata (Decodo/Amazon) - 1-3 seconds
   - eBay sold comps - 5-10 seconds
   - BookFinder offers - 12-18 seconds
   ↓
6. UPDATE BOTH DATABASES
   ↓
7. CALCULATE TRAINING QUALITY SCORE
   ↓
8. SET in_training FLAG (if eligible)
```

### Deduplication Strategy

**unified_index.db** tracks which ISBNs are in which databases:

```sql
CREATE TABLE isbn_index (
    isbn TEXT PRIMARY KEY,
    in_training INTEGER DEFAULT 0,       -- In metadata_cache.db
    in_cache INTEGER DEFAULT 0,          -- Legacy flag
    training_updated TEXT,               -- Last metadata_cache update
    cache_updated TEXT,
    quality_score REAL DEFAULT 0.0,
    last_checked TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Before enriching an ISBN:**
```python
def should_enrich(isbn):
    index = query_unified_index(isbn)

    if not index:
        return True  # New ISBN, always enrich

    # Check staleness
    if (now - index.training_updated) > 30_days:
        return True  # Stale data, re-enrich

    # Check if missing critical fields
    if index.quality_score < 0.5:
        return True  # Low quality, needs more data

    return False  # Already have good data, skip
```

## ML Training Pipeline

### Data Loading

**Primary Source**: `metadata_cache.db`

```python
# In scripts/stacking/data_loader.py

def load_training_data():
    conn = sqlite3.connect('metadata_cache.db')

    # Query for high-quality training examples
    query = """
        SELECT
            isbn, title, authors, metadata_json, market_json,
            sold_comps_median as target_price,
            cover_type, signed, printing
        FROM cached_books
        WHERE in_training = 1              -- Quality gate passed
          AND sold_comps_count >= 8        -- Sufficient comps
          AND sold_comps_median >= 5       -- Minimum price
          AND market_json IS NOT NULL      -- Has market data
        ORDER BY training_quality_score DESC
    """

    return pd.read_sql(query, conn)
```

### Benefits

1. **Single Source of Truth**: All training data in one place
2. **No Duplication**: unified_index prevents duplicate enrichments
3. **Automatic Growth**: Every scan enriches training database
4. **Quality Control**: Only high-quality examples used for training
5. **Staleness Tracking**: Know when to re-enrich old ISBNs

## Migration Process (November 2025)

### What Was Done

1. ✅ **Backed up all databases** to `backups/migration_20251105/`
2. ✅ **Exported historical data** (scan_history, lots) to CSV
3. ✅ **Expanded metadata_cache.db schema** (+27 columns)
4. ✅ **Created new indexes** for training queries
5. ✅ **Generated migration report**

### Files Created

- `backups/migration_20251105/catalog.db.backup-20251105-112437`
- `backups/migration_20251105/metadata_cache.db.backup-20251105-112437`
- `backups/migration_20251105/unified_index.db.backup-20251105-112437`
- `backups/migration_20251105/migration_report.txt`
- `scripts/export_historical_data.py`
- `scripts/generate_migration_report.py`
- `scripts/expand_metadata_cache_schema.py`

## Usage Examples

### Check Training Database Status

```bash
sqlite3 metadata_cache.db "
SELECT
    COUNT(*) as total_books,
    SUM(CASE WHEN in_training = 1 THEN 1 ELSE 0 END) as training_eligible,
    AVG(training_quality_score) as avg_quality
FROM cached_books
"
```

### Find Books Needing Re-Enrichment

```bash
sqlite3 metadata_cache.db "
SELECT isbn, title, market_fetched_at
FROM cached_books
WHERE market_fetched_at < datetime('now', '-30 days')
   OR market_fetched_at IS NULL
ORDER BY quality_score DESC
LIMIT 100
"
```

### Training Quality Distribution

```bash
sqlite3 metadata_cache.db "
SELECT
    CASE
        WHEN training_quality_score >= 0.8 THEN 'Excellent (0.8-1.0)'
        WHEN training_quality_score >= 0.6 THEN 'Good (0.6-0.8)'
        WHEN training_quality_score >= 0.4 THEN 'Fair (0.4-0.6)'
        ELSE 'Poor (0.0-0.4)'
    END as quality_tier,
    COUNT(*) as count
FROM cached_books
GROUP BY quality_tier
ORDER BY quality_tier DESC
"
```

## Best Practices

### For Scanning
1. Scan books as normal - organic growth happens automatically
2. Enrichments run in background (don't block UI)
3. Check training database growth weekly

### For Enrichment Scripts
1. Always update **both** catalog.db AND metadata_cache.db
2. Check unified_index before enriching (avoid duplicates)
3. Update training quality scores after enrichment
4. Log API calls for rate limit tracking

### For ML Training
1. Use metadata_cache.db as primary data source
2. Filter by `in_training = 1` for quality examples
3. Join with catalog.db for very recent data if needed
4. Retrain models monthly as training database grows

## Troubleshooting

### Issue: Books not appearing in training database

**Check**:
```sql
SELECT isbn, in_training, training_quality_score, sold_comps_count
FROM cached_books
WHERE isbn = '9780316769174'
```

**Solution**: Book may not meet quality gates. Run enrichment to collect more data.

### Issue: Duplicate enrichments

**Check unified_index**:
```sql
SELECT * FROM isbn_index WHERE isbn = '9780316769174'
```

**Solution**: Ensure enrichment scripts query unified_index before making API calls.

### Issue: Stale training data

**Find stale books**:
```sql
SELECT COUNT(*)
FROM cached_books
WHERE in_training = 1
  AND market_fetched_at < datetime('now', '-60 days')
```

**Solution**: Run batch re-enrichment on stale training examples.

## Future Enhancements

1. **Automatic Re-Enrichment**: Scheduled job to refresh stale training data
2. **Training Database Analytics**: Dashboard showing growth and quality metrics
3. **Smart Deduplication**: Use ML to identify duplicate editions/printings
4. **Quality Feedback Loop**: Track prediction accuracy vs actual sales
5. **Active Learning**: Prioritize enrichment for books where model is uncertain

## Related Documentation

- `/docs/FEATURE_DETECTION_GUIDELINES.md` - How to detect signed/1st editions
- `/docs/ml/ML_PHASE2_PHASE3_COMPLETE.md` - Specialist model training
- `/docs/ENRICHMENT_SCRIPT_CHECKLIST.md` - Enrichment best practices
- `/scripts/debug_prediction.py` - Debug ML predictions

## Rollback Plan

If issues occur:
```bash
# 1. Restore from backups
cp backups/migration_20251105/metadata_cache.db.backup-20251105-112437 metadata_cache.db

# 2. Restore unified index
cp backups/migration_20251105/unified_index.db.backup-20251105-112437 ~/.isbn_lot_optimizer/unified_index.db

# 3. Revert code changes
git reset --hard HEAD~1
```

## Summary

- **metadata_cache.db** is now the **unified training database**
- Contains **all historical ISBNs** + market data
- **43 columns** total (16 metadata + 27 market/training)
- **Organic growth**: Every scan enriches training database
- **Quality gates** ensure only good examples used for training
- **Deduplication** prevents wasted API calls
- **Single source of truth** for all ML training

---

**Migration Date**: November 5, 2025
**Schema Version**: 2.0
**Status**: ✅ Complete
