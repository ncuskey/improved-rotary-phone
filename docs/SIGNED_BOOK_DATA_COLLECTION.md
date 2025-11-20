# Signed Book Data Collection and ML Integration

**Date:** November 9, 2025 (Updated: November 19, 2025)
**Status:** ✅ System Implemented + Award Winners Database Expansion
**Scripts:**
- `scripts/sync_signed_status_to_training.py` - Sync signed status to training data
- `scripts/import_award_winners.py` - Import famous authors from CSV (NEW: 2025-11-19)

---

## Recent Update (2025-11-19): Famous Authors Database Expansion

**Database Growth:** 11 → 36 authors (227% increase)

### Award Winners Import System
- Created automated CSV import tool with tier-based signed book multipliers
- Added 25 contemporary award-winning authors (2023-2024)
- Award tiers: Major awards (12-15x), Genre awards (8x), Children's awards (6x)

### Authors Added:
- **National Book Award winners**: Percival Everett, Jason De León, Lena Khalaf Tuffaha, Shifa Saltagi Safadi
- **Booker Prize**: Samantha Harvey (15x), Jenny Erpenbeck (12x)
- **National Book Critics Circle**: Lorrie Moore, Safiya Sinclair, Jonny Steinberg, Kim Hyesoon
- **Hugo/Nebula winners**: Emily Tesh, Vajra Chandrasekera, Ai Jiang, Naomi Kritzer, R.S.A. Garcia, T. Kingfisher
- **Women's Prize**: V.V. Ganeshananthan
- **Newbery/Caldecott**: Dave Eggers, Vashti Harrison
- And 10 more contemporary literary award winners

### Usage:
```bash
# Import award winners from CSV
python3 scripts/import_award_winners.py /path/to/award_winners.csv

# Auto-confirm mode
python3 scripts/import_award_winners.py /path/to/award_winners.csv --yes
```

---

## Original Problem Statement

The ML model was predicting **$0 premium for signed books** because only 5 signed books (0.18%) existed in 2,736 training samples - far too few for the model to learn the pattern.

**Example**: A signed Tom Clancy first edition worth $50-150 was predicted at $3.00.

---

## Root Cause Analysis

### Infrastructure: ✅ Already Exists
- **Database schema**: All tables have `signed` or `is_signed` fields
- **Feature detection**: `shared/feature_detector.py` detects 14+ signed/autograph patterns
- **ML features**: `isbn_lot_optimizer/ml/feature_extractor.py` extracts signed features
- **Data sources**: BookFinder, eBay sold/active listings, vendor data

### The Gap: Data Aggregation
While infrastructure was complete, signed status wasn't being aggregated from data sources to training records:

1. **BookFinder signed offers** (125 ISBNs with signed copies) ❌ Not synced to `cached_books.signed`
2. **eBay sold listings** (individual listings have signed detection) ❌ Not aggregated to training records
3. **eBay active listings** (titles contain "signed"/"autographed") ❌ Not parsed and synced

---

## Solution: Signed Status Sync Script

### Overview

The `sync_signed_status_to_training.py` script aggregates signed book information from multiple sources and updates the training database.

### Data Sources Processed

1. **BookFinder Offers** (`bookfinder_offers` table)
   - Direct field: `is_signed = 1`
   - Most reliable source
   - ~125 unique signed ISBNs

2. **eBay Sold Listings** (`sold_listings` table)
   - Direct field: `signed = 1`
   - Parsed from listing titles using `feature_detector`
   - Historical sales data

3. **eBay Active Listings** (`ebay_active_listings` table)
   - Parsed from listing `title` field
   - Uses `feature_detector.is_signed()` to detect patterns
   - Current market listings

4. **Future**: Vendor enrichment data (AbeBooks, Alibris, ZVAB)
   - Can be added as data sources expand

---

## Usage

### Basic Usage

```bash
# Sync signed status to training database
python3 scripts/sync_signed_status_to_training.py

# Dry run (see what would be updated without making changes)
python3 scripts/sync_signed_status_to_training.py --dry-run

# Specify database path
python3 scripts/sync_signed_status_to_training.py --db data/isbn_lot_optimizer.db
```

### When to Run

Run this script:

1. **After bulk data collection**: When you've collected new eBay sold comps, BookFinder offers, or vendor data
2. **Before model training**: To ensure training data has latest signed book flags
3. **As part of enrichment pipeline**: Integrate into automated enrichment workflow
4. **Monthly maintenance**: Regular sync to catch new signed book listings

### Example Output

```
================================================================================
SYNCING SIGNED BOOK STATUS TO TRAINING DATA
================================================================================

Training database: 2736 total books in cached_books
Current signed books: 5 (0.18%)

Collecting signed ISBNs from data sources...
  ✓ BookFinder: 125 signed ISBNs
  ✓ Sold listings: 47 signed ISBNs
  ✓ Active listings: 23 signed ISBNs (parsed from titles)

Total unique signed ISBNs found: 142
ISBNs to update (currently signed=0): 137

Updating signed=1 for 137 ISBNs...
✓ Updated 137 records

New signed book count: 142 (5.19%)
Improvement: +137 signed books

================================================================================
SYNC COMPLETE
================================================================================
```

---

## Integration with Enrichment Pipeline

### Option 1: Manual Integration

Add to your enrichment workflow:

```bash
# After enrichment completes
python3 scripts/enrich_metadata_cache_market_data.py

# Sync signed status
python3 scripts/sync_signed_status_to_training.py

# Retrain models
python3 scripts/stacking/train_ebay_model.py
```

### Option 2: Automated Integration (TODO)

Update `scripts/enrich_metadata_cache_market_data.py` to call signed sync automatically:

```python
# At end of enrichment script
from sync_signed_status_to_training import sync_signed_status

print("\nSyncing signed book status...")
sync_signed_status('data/isbn_lot_optimizer.db', dry_run=False)
```

---

## Feature Detection Patterns

The `shared/feature_detector.py` module detects these signed book patterns:

### Basic Patterns
- "signed"
- "autographed"
- "inscribed"

### Qualified Patterns
- "hand signed"
- "author signed"
- "signed by author"
- "signed by the author"

### Abbreviations
- "s/a"
- "sgnd"

### Bookplate Patterns
- "signed bookplate"
- "autographed bookplate"

### Detection Logic
- Case-insensitive
- Word boundary matching (avoids false positives like "designed")
- Handles variations with/without spaces

---

## Impact on ML Models

### Before Sync
- **Training samples with signed=1**: 5 (0.18%)
- **Model learned premium**: $0.00
- **Prediction for signed Clancy 1st edition**: $3.00

### After Sync (Expected)
- **Training samples with signed=1**: 140+ (5%+)
- **Model learned premium**: $20-100+ (realistic)
- **Prediction for signed Clancy 1st edition**: $60-120

### Why 5% is Sufficient
- ML models need ~50-100 examples minimum to learn a pattern
- 140 signed books across 2,700 training samples = adequate signal
- Signed books are inherently rare (real market: ~2-5% of listings)

---

## Validation and Testing

### Validate Sync Results

```bash
# Check signed book count
sqlite3 data/isbn_lot_optimizer.db "SELECT COUNT(*) FROM cached_books WHERE signed = 1"

# List signed books
sqlite3 data/isbn_lot_optimizer.db "SELECT isbn, title FROM cached_books WHERE signed = 1 LIMIT 10"

# Check signed premium learning
curl -X POST http://localhost:8111/api/books/{ISBN}/estimate_price \
  -H 'Content-Type: application/json' \
  -d '{"condition": "very_good", "is_hardcover": true, "is_signed": true}'
```

### Expected Delta
After retraining, signed books should show significant price delta:
- **Unsigned**: $10
- **Signed**: $50-100 (delta: +$40-90)

---

## Troubleshooting

### Issue: "cached_books table not found"

**Cause**: Database hasn't been initialized yet

**Solution**: Run enrichment pipeline first to populate database:
```bash
python3 scripts/enrich_metadata_cache_market_data.py
```

### Issue: "No signed ISBNs found"

**Cause**: Data sources don't have signed book data yet

**Solution**:
1. Collect BookFinder offers: `python3 scripts/collect_bookfinder_prices.py`
2. Collect eBay sold comps: `python3 scripts/collect_sold_listings.py`
3. Re-run sync script

### Issue: Model still shows $0 delta for signed

**Cause**: Models not retrained after sync

**Solution**: Retrain models with new signed book data:
```bash
python3 scripts/stacking/train_ebay_model.py
python3 scripts/stacking/train_amazon_model.py
# ... other specialist models
```

---

## Future Enhancements

### Priority 1: Vendor Enrichment Integration
- Parse AbeBooks listing descriptions for signed keywords
- Check Alibris "signed" field in API responses
- Extract ZVAB signed status from enrichment data

### Priority 2: Confidence Scoring
- Add confidence score for signed detection (0.0-1.0)
- Higher confidence for direct fields (BookFinder `is_signed=1`)
- Lower confidence for title parsing (potential false positives)

### Priority 3: Signed Premium Analysis
- Calculate actual signed premium from sold comps
- Track signed vs unsigned price ratios by author/genre
- Use ratios to validate model predictions

### Priority 4: Real-time Detection
- Integrate signed detection into eBay scraping pipeline
- Parse titles during collection, not as post-processing
- Add signed detection to Amazon FBM collection

---

## Files Modified/Created

### New Files
- **`scripts/sync_signed_status_to_training.py`**: Main sync script
- **`docs/SIGNED_BOOK_DATA_COLLECTION.md`**: This documentation

### Existing Files (No Changes Needed)
- **`shared/feature_detector.py`**: Already has signed detection
- **`isbn_lot_optimizer/ml/feature_extractor.py`**: Already extracts signed features
- **`scripts/stacking/data_loader.py`**: Already loads signed field

---

## References

- **Feature Detection**: `shared/feature_detector.py:is_signed()`
- **ML Feature Extraction**: `isbn_lot_optimizer/ml/feature_extractor.py:get_features()`
- **Training Data Loader**: `scripts/stacking/data_loader.py:load_training_data()`
- **Database Schema**: `docs/DATABASE_STRUCTURE.md`

---

**Author:** ML Pipeline Team
**Date:** November 9, 2025
**Version:** 1.0
**Status:** Production-ready
