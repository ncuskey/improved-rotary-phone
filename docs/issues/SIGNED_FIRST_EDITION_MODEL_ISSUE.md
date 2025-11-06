# Issue: Signed Books and First Editions Show Negative Price Impact

**Date:** 2025-11-05
**Status:** 🔴 Known Limitation
**Severity:** Medium

## Problem

The ML model predicts NEGATIVE price deltas for signed books and first editions, which is logically incorrect:

```json
{
  "deltas": [
    {"attribute": "is_signed", "delta": -0.03},           // ❌ Wrong
    {"attribute": "is_first_edition", "delta": -0.02}     // ❌ Wrong
  ]
}
```

**Expected Behavior:** Signed books and first editions should typically have POSITIVE price impact (worth more than unsigned/non-first-edition copies).

## Root Cause

**Insufficient Training Data for Rare Attributes**

The model was trained with 5,518 samples, but:
- Very few (likely <1%) have `signed=true` labels
- Very few have `printing="1st"` labels
- The `metadata_cache.db` doesn't store these attributes for most books

When a feature is mostly 0 (absent), the model:
1. Can't learn reliable relationships
2. May learn spurious correlations
3. Defaults to small random weights (which happened to be negative)

## Evidence

1. **Feature Distribution:**
   - `is_signed`: Mostly 0 (absent in training data)
   - `is_first_edition`: Mostly 0 (absent in training data)

2. **Model Importance:**
   From metadata.json, signed/first edition features likely have very low importance scores, indicating the model didn't learn meaningful patterns.

3. **Data Schema:**
   The `metadata_cache.db` uses table `cached_books` which has no `signed` or `printing` columns - these attributes aren't collected for most books.

## Impact

- Users see illogical price decreases when selecting signed or first edition
- Undermines trust in price estimates
- May lead to undervaluing collectible books

## Solutions

### Short-term: Add Logical Overrides (Recommended)

Add post-processing to enforce domain constraints:

```python
# In isbn_web/api/routes/books.py, after calculating deltas:
for delta in deltas:
    if delta["attribute"] in ["is_signed", "is_first_edition"]:
        # Enforce minimum positive delta for rare attributes
        if delta["delta"] < 0:
            # Apply conservative 5% price boost for signed, 3% for first edition
            if delta["attribute"] == "is_signed":
                delta["delta"] = round(baseline_price * 0.05, 2)
            elif delta["attribute"] == "is_first_edition":
                delta["delta"] = round(baseline_price * 0.03, 2)
```

**Pros:**
- Quick fix
- Ensures logical behavior
- Conservative estimates (better than negative)

**Cons:**
- Not data-driven
- Fixed percentages may not reflect true market

### Medium-term: Collect More Training Data

1. **Scrape BookFinder signed/first edition offers:**
   - Already collecting `bookfinder_signed_count` and `bookfinder_first_edition_count`
   - Add sold listings with these attributes to training data

2. **Use external data sources:**
   - AbeBooks has detailed collectibility info
   - Biblio specializes in rare/signed books
   - eBay sold listings with "signed" in title/description

3. **Manual labeling:**
   - Add signed/first edition flags to catalog books where known
   - Use title/description parsing: "SIGNED", "1st Edition", "First Printing"

### Long-term: Feature Engineering

1. **Use proxy features instead of direct flags:**
   - `bookfinder_signed_premium_pct`: % premium for signed copies (already collected)
   - `bookfinder_first_ed_premium_pct`: % premium for first editions (already collected)
   - These are continuous features with better distribution

2. **Collect comparative data:**
   - For each book, collect prices for BOTH signed and unsigned
   - Train model to predict the signed/unsigned RATIO
   - Apply ratio as multiplier

## Recommended Action

**Immediate:** Add logical overrides for signed/first edition (5% and 3% boosts)

**Next Sprint:**
1. Add signed/first edition detection from book descriptions
2. Collect 100+ examples of signed book sold prices
3. Retrain model with balanced sampling

## Related Code

- Feature extraction: `isbn_lot_optimizer/ml/feature_extractor.py:528-529`
- Delta calculation: `isbn_web/api/routes/books.py:1336-1363`
- Training script: `scripts/train_price_model.py`

## References

- BookFinder already collecting premium percentages
- Top feature is `serper_sold_ebay_pct` (28.98%) - not signed/first edition
- Collectibility features exist but underutilized
