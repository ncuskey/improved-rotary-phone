# Data Leakage Fix - Phase 1 Complete

## Problem Identified

**CRITICAL DATA LEAKAGE:** The ML price prediction model was using sold prices as input features to predict sold prices - classic circular reasoning.

### Specific Issues Found

1. **feature_extractor.py (lines 314-346)**
   - Used `serper_sold_avg_price` as feature
   - Used `serper_sold_min_price` as feature (33.3% model importance!)
   - Used `serper_sold_max_price` as feature
   - Used `serper_sold_price_range` as feature
   - Used `serper_sold_demand_signal` (calculated from avg_price) as feature

2. **get_sold_listings_features() function (lines 868-933)**
   - Queried price columns from sold_listings table
   - Returned price features in dict

## Changes Made

### 1. Updated feature_extractor.py (lines 314-346)

**REMOVED these features (data leakage):**
```python
- features["serper_sold_avg_price"]
- features["serper_sold_min_price"]  # Was 33.3% model importance!
- features["serper_sold_max_price"]
- features["serper_sold_price_range"]
- features["serper_sold_demand_signal"]  # Calculated from prices
```

**KEPT these features (valid statistics):**
```python
+ features["serper_sold_count"]  # Volume - not a price
+ features["serper_sold_has_signed"]  # Boolean indicator
+ features["serper_sold_signed_pct"]  # Percentage
+ features["serper_sold_hardcover_pct"]  # Percentage
+ features["serper_sold_ebay_pct"]  # Platform distribution
```

### 2. Updated get_sold_listings_features() function

**Changed SQL query from:**
```sql
SELECT
    COUNT(*) as count,
    AVG(price) as avg_price,  -- REMOVED
    MIN(price) as min_price,  -- REMOVED
    MAX(price) as max_price,  -- REMOVED
    ...
```

**To:**
```sql
SELECT
    COUNT(*) as count,
    SUM(CASE WHEN signed = 1 THEN 1 ELSE 0 END) as signed_count,
    SUM(CASE WHEN cover_type = 'Hardcover' THEN 1 ELSE 0 END) as hardcover_count,
    SUM(CASE WHEN platform = 'ebay' THEN 1 ELSE 0 END) as ebay_count
FROM sold_listings
```

**Changed return dict to only include non-price statistics:**
```python
return {
    'serper_sold_count': count,
    'serper_sold_has_signed': 1 if signed_count > 0 else 0,
    'serper_sold_signed_pct': (signed_count / count) if count > 0 else 0,
    'serper_sold_hardcover_pct': (hardcover_count / count) if count > 0 else 0,
    'serper_sold_ebay_pct': (ebay_count / count) if count > 0 else 0,
}
```

## Impact

### What This Fixes

1. **Eliminates circular reasoning** - Model can no longer "cheat" by looking at sold prices
2. **Forces model to learn fundamentals** - Must learn book value from metadata, author, series, ratings, etc.
3. **Valid market signals retained** - Sales volume, format distribution, platform mix still inform predictions
4. **Graceful handling** - Function returns None when sold_listings table doesn't exist (table not yet populated)

### Expected Model Performance

- **Short term:** Accuracy may decrease temporarily (model was relying on leaked data)
- **Long term:** Model will learn genuine book value patterns
- **Predicted improvement:** 60-75% accuracy gain after Phase 2 features added
  - Expected MAE: $2.95 → $1.20-1.50
  - By adding temporal, series, author-level features

## Next Steps

### Phase 2: Add Legitimate Features (Pending)

1. **Temporal features**
   - Publication recency
   - Seasonal patterns
   - Market trends

2. **Series completion features**
   - Series position (book 1 of 10)
   - Series popularity metrics
   - Completion incentive value

3. **Enhanced BookFinder extraction**
   - Signed/unsigned price differential
   - First edition premiums
   - Detailed condition analysis

4. **Author-level aggregates**
   - Author average selling price
   - Author sales velocity
   - Author collectibility score

### Phase 3: Retrain and Validate

- Backup current model
- Retrain with data leakage removed
- Validate on held-out test set
- Compare before/after performance

### Phase 4: Update Model Metadata

- Update version string
- Document feature changes
- Update model metadata JSON
- Archive old model

## Files Modified

- `/Users/nickcuskey/ISBN/isbn_lot_optimizer/ml/feature_extractor.py`
  - Lines 314-346: Removed price features from sold listings section
  - Lines 868-920: Updated get_sold_listings_features() to remove price queries

## Date

2025-11-04

## Status

✅ Phase 1 Complete - Data leakage removed
⏳ Phase 2 Pending - Add legitimate features
⏳ Phase 3 Pending - Retrain model
⏳ Phase 4 Pending - Update metadata
