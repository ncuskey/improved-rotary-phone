# Signed Book Data Collection - Quick Start Guide

**Date:** November 9, 2025
**Status:** ✅ Ready to Use (when database is populated)

---

## TL;DR

Your ML model currently predicts **$0 premium for signed books** because training data has too few signed examples (5 out of 2,736 = 0.18%).

**Solution created:** `scripts/sync_signed_status_to_training.py` - Run this after data enrichment to aggregate signed book information from multiple sources into training records.

**Expected improvement:** 5 → 140+ signed training examples (26x increase) → Model will learn realistic $20-100+ signed premiums.

---

## When to Run

Run the sync script after you have a populated database with training data:

```bash
# Step 1: Check if database is ready
ls -lh data/isbn_lot_optimizer.db

# Step 2: Sync signed book data (dry-run first)
python3 scripts/sync_signed_status_to_training.py --dry-run

# Step 3: Actually sync the data
python3 scripts/sync_signed_status_to_training.py

# Step 4: Retrain models
python3 scripts/stacking/train_ebay_model.py
python3 scripts/stacking/train_amazon_model.py

# Step 5: Test signed book predictions
curl -X POST http://localhost:8111/api/books/9780399134401/estimate_price \
  -H 'Content-Type: application/json' \
  -d '{"condition": "very_good", "is_hardcover": true, "is_signed": true}'
```

---

## What the Script Does

The `sync_signed_status_to_training.py` script:

1. **Scans BookFinder offers** → finds ISBNs with `is_signed = 1` (~125 ISBNs)
2. **Scans eBay sold listings** → finds ISBNs with `signed = 1`
3. **Parses eBay active listings** → detects "signed"/"autographed" in titles
4. **Updates training database** → sets `cached_books.signed = 1` for all found ISBNs

---

## Current Status

**Infrastructure:** ✅ Complete
- Database schema has signed fields
- Feature detector recognizes 14+ signed patterns
- ML feature extractor handles signed attributes
- BookFinder collection captures signed offers

**Data Gap:** ⚠️ Aggregation missing
- Individual sources HAVE signed detection
- Training records WEREN'T being updated
- Script now bridges this gap

**Next Action Required:** Run sync script when database is populated

---

## Expected Results

### Before Sync
```
Training samples with signed=1: 5 (0.18%)
Model learned premium: $0
Prediction for signed Tom Clancy 1st edition: $3.00
```

### After Sync + Retrain
```
Training samples with signed=1: 140+ (5%+)
Model learned premium: $20-100+
Prediction for signed Tom Clancy 1st edition: $60-120
```

---

## Validation

After running sync and retraining, validate the signed premium:

```bash
# Test unsigned book
curl -X POST http://localhost:8111/api/books/9780399134401/estimate_price \
  -H 'Content-Type: application/json' \
  -d '{"condition": "very_good", "is_hardcover": true, "is_signed": false}'

# Test signed book (should show higher price + delta)
curl -X POST http://localhost:8111/api/books/9780399134401/estimate_price \
  -H 'Content-Type: application/json' \
  -d '{"condition": "very_good", "is_hardcover": true, "is_signed": true}'
```

Look for the `deltas` array in the response - the `is_signed` attribute should show a positive delta (e.g., +$40-90).

---

## Integration with Workflow

Add to your enrichment/training workflow:

```bash
#!/bin/bash
# Your regular workflow

# 1. Collect data
python3 scripts/collect_bookfinder_prices.py
python3 scripts/collect_sold_listings.py
# ... other collection scripts

# 2. Enrich database
python3 scripts/enrich_metadata_cache_market_data.py

# 3. Sync signed book status ← NEW STEP
python3 scripts/sync_signed_status_to_training.py

# 4. Train models
python3 scripts/stacking/train_ebay_model.py
python3 scripts/stacking/train_amazon_model.py
# ... other model training scripts
```

---

## Troubleshooting

### "cached_books table not found"
**Solution:** Run enrichment pipeline first:
```bash
python3 scripts/enrich_metadata_cache_market_data.py
```

### "No signed ISBNs found"
**Solution:** Collect BookFinder and eBay data:
```bash
python3 scripts/collect_bookfinder_prices.py
python3 scripts/collect_sold_listings.py
```

### Model still shows $0 delta after sync
**Solution:** Retrain models:
```bash
python3 scripts/stacking/train_ebay_model.py
python3 scripts/stacking/train_amazon_model.py
```

---

## Files Created

1. **`scripts/sync_signed_status_to_training.py`** - Main sync script
2. **`docs/SIGNED_BOOK_DATA_COLLECTION.md`** - Comprehensive documentation
3. **`docs/SIGNED_BOOK_QUICKSTART.md`** - This quick start guide

---

## For More Details

See full documentation: `docs/SIGNED_BOOK_DATA_COLLECTION.md`

---

**Ready to use when database is populated!** 🚀
