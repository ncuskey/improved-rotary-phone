# Strategic Training Data Collection - Phase 1 POC

**Status**: Phase 1 Proof-of-Concept
**Date**: October 29, 2025

---

## Overview

This is a **proof-of-concept** for strategically collecting high-quality training data to improve the ML price estimation model. Instead of building the full 2000+ book collection system, we're starting with 50-100 books to validate the approach.

## Why Strategic Collection?

**Current Training Data Gaps**:
- **0 signed books** → Model cannot learn signed premium
- **83% unknown format** → Missing #3 most important feature (hardcover)
- **Only 8.6% first editions** → Underrepresented valuable books
- **Limited high-value books** → Can't learn premium pricing ($30+)

**Goal**: Collect books that fill these gaps and have reliable pricing data (10+ eBay sold comps).

---

## Phase 1 POC Architecture

### Components Built

1. **`isbn_lot_optimizer/training_db.py`** - Training database manager
   - Separate `training_data.db` (independent from inventory)
   - Tables: training_books, collection_targets, logs, API tracking

2. **`isbn_lot_optimizer/collection_strategies.py`** - Target definitions
   - 11 categories totaling 2000+ books (for future)
   - Search strategies and filters

3. **`scripts/collect_training_data_poc.py`** - POC collection script
   - Collects 50-100 books from ONE category
   - Multi-source data: eBay comps + Amazon/Decodo + Metadata
   - Validates approach before scaling

### Data Sources

For each ISBN collected:

1. **eBay Sold Comps** (ground truth for training)
   - Sold count, avg price, median price
   - Min 10 sold listings in last 90 days

2. **Amazon/Decodo** (features)
   - Sales rank
   - Amazon offers/prices

3. **Google Books/OpenLibrary** (metadata)
   - Title, author, year, page count
   - Categories, ratings
   - **Physical attributes**: Hardcover/Paperback, First Edition, Signed

---

## Usage

### Option 1: Quick Test with Manual ISBN List

```bash
# Collect 20 first edition hardcovers (for quick testing)
python3 scripts/collect_training_data_poc.py \
  --category first_edition_hardcover \
  --limit 20 \
  --isbn-list \
    9780385537858 \
    9780316769488 \
    9780375831003 \
    9780385121682 \
    9780061120084 \
    # ... add more ISBNs
```

### Option 2: Load ISBNs from File

```bash
# Create ISBN list file
cat > /tmp/first_edition_isbns.txt <<EOF
9780385537858
9780316769488
9780375831003
9780385121682
9780061120084
EOF

# Collect from file
python3 scripts/collect_training_data_poc.py \
  --category first_edition_hardcover \
  --limit 50 \
  --isbn-file /tmp/first_edition_isbns.txt
```

### Option 3: Signed Books Category

```bash
python3 scripts/collect_training_data_poc.py \
  --category signed_hardcover \
  --limit 100 \
  --isbn-file /tmp/signed_book_isbns.txt
```

---

## Finding Candidate ISBNs

For POC testing, you need to provide ISBNs manually. Here's how to find good candidates:

### Method 1: eBay Manual Search

1. Go to eBay → Books & Magazines
2. Search: "first edition hardcover"
3. Filter: **Sold listings**, **Books category**, Price: $10-50
4. Find books with many sold listings (look for "X sold" in the listing)
5. Extract ISBN-13 from listing (usually in description or title)

**Example searches**:
- "signed first edition hardcover"
- "first edition Stephen King"
- "autographed book hardcover"
- "first printing hardcover fiction"

### Method 2: Popular Book Lists

Look up ISBNs for known popular/collectible books:
- Harry Potter first editions
- Stephen King signed editions
- Classic literature first editions
- Bestseller hardcovers from 2010-2020

### Method 3: Your Existing Catalog

```bash
# Export first editions from your catalog
sqlite3 ~/.isbn_lot_optimizer/catalog.db <<SQL
SELECT isbn FROM books
WHERE printing = '1st'
AND cover_type = 'Hardcover'
LIMIT 100;
SQL
```

---

## What The Script Does

1. **Loads ISBNs** from file or command line
2. **For each ISBN**:
   - Check if blacklisted (already collected or failed)
   - Fetch eBay sold comps (needs 10+ sold in 90 days)
   - If sufficient comps → collect Amazon data + metadata
   - Store in `training_data.db`
   - Add to blacklist if failed
3. **Outputs** progress and statistics

### Example Output

```
======================================================================
STRATEGIC TRAINING DATA COLLECTION - PHASE 1 POC
======================================================================
Category: First edition hardcover books (non-signed)
Target count: 50 books
Minimum comps: 10

Found 75 candidate ISBNs

[1/75] Processing 9780385537858
  9780385537858: 24 sold comps found
  9780385537858: Amazon rank 12450
  9780385537858: ✓ Stored in training database

[2/75] Processing 9780316769488
  9780316769488: 18 sold comps found
  9780316769488: Amazon rank 8920
  9780316769488: ✓ Stored in training database

...

Progress: 50/50 books collected

======================================================================
COLLECTION COMPLETE
======================================================================
Successfully collected: 50 books
Insufficient comps: 15
Data collection failed: 8
Blacklisted: 2

Training database now has 50 books
  - Signed books: 0
  - First editions: 50
```

---

## After Collection: Retrain Model

Once you've collected 50-100 books, retrain the model to see improvement:

### 1. Verify Training Data

```bash
# Check what was collected
python3 -c "
from isbn_lot_optimizer.training_db import TrainingDataManager
db = TrainingDataManager()
stats = db.get_stats()

print(f'Total books: {stats[\"total_books\"]}')
print(f'By category: {stats[\"by_category\"]}')
print(f'By cover type: {stats[\"by_cover_type\"]}')
print(f'Signed books: {stats[\"signed_books\"]}')
print(f'First editions: {stats[\"first_editions\"]}')
"
```

### 2. Update Training Script

Modify `scripts/train_price_model.py` to load from BOTH databases:

```python
# Add after line 40
# Also load from training_data.db
training_db = Path.home() / '.isbn_lot_optimizer' / 'training_data.db'
if training_db.exists():
    conn_training = sqlite3.connect(training_db)
    cursor_training = conn_training.cursor()
    cursor_training.execute(query)  # Same query
    training_rows = cursor_training.fetchall()
    conn_training.close()

    print(f"Loaded {len(training_rows)} books from training_data.db")
    rows.extend(training_rows)
```

### 3. Retrain

```bash
python3 scripts/train_price_model.py
```

### 4. Compare Results

**Before POC** (current model):
- Test MAE: $3.75
- Test R²: -0.027
- Feature importance: is_hardcover 9.02%, is_first_edition 2.69%, is_signed 0%

**After POC** (expected improvements):
- Test MAE: $3.40 - $3.60 (5-10% better)
- Test R²: 0.05 - 0.15 (moving towards positive)
- Feature importance: Better learned weights for filled gaps

---

## Success Criteria for POC

✅ **Technical Validation**:
- [ ] Successfully collect 50+ books
- [ ] All books have 10+ eBay sold comps
- [ ] Amazon + metadata collected for 80%+ of books
- [ ] Data stored in training_data.db

✅ **Quality Validation**:
- [ ] Collected books fill target gap (e.g., first editions)
- [ ] Price range: $10-50 (not all low-value)
- [ ] Variety of titles/authors (not all from one series)

✅ **Model Improvement**:
- [ ] Retrained model shows lower MAE
- [ ] Feature importance increases for target attributes
- [ ] Predictions more accurate on test set

---

## Next Steps After POC

**If POC succeeds**:

1. **Expand to Priority 1 Categories** (850 books)
   - Signed hardcovers: 200
   - First edition hardcovers: 400
   - Mass market paperbacks: 150
   - Trade paperbacks: 100

2. **Build Full eBay Search Integration**
   - Automate ISBN discovery via eBay Browse API
   - No more manual ISBN lists

3. **Add Batch Processing**
   - Run 100-200 books/day over 10-15 days
   - Respect API rate limits

4. **Scale to 2000+ Books**
   - All 11 categories
   - Comprehensive training dataset

**If POC shows issues**:
- Refine search strategies
- Adjust comp thresholds
- Improve data collection error handling

---

## Files Created

```
isbn_lot_optimizer/
  ├── training_db.py              # Training database manager
  ├── collection_strategies.py    # Target definitions & search strategies

scripts/
  └── collect_training_data_poc.py  # Phase 1 POC collector

~/.isbn_lot_optimizer/
  └── training_data.db             # Separate training database (created on first run)
```

---

## FAQ

**Q: Why separate from catalog.db?**
A: Training data is strategic collection specifically for ML, separate from your actual inventory. This keeps concerns separated.

**Q: How long does collection take?**
A: ~30-60 seconds per book (API calls + rate limiting). 50 books = 25-50 minutes.

**Q: What if a book has no sold comps?**
A: It's skipped and blacklisted. We only want books with reliable pricing data (10+ comps).

**Q: Can I collect multiple categories in POC?**
A: Yes, run the script multiple times with different `--category` values.

**Q: Does this affect my inventory catalog.db?**
A: No, it only writes to training_data.db. Completely separate.

---

## Known Limitations (POC)

- ❌ No automated eBay ISBN discovery (must provide ISBNs manually)
- ❌ No parallel processing (collects sequentially)
- ❌ Basic rate limiting (1 second between books)
- ❌ No resume/checkpoint support
- ❌ Limited error recovery

These will be addressed in the full implementation if POC succeeds.
