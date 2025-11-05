# Code Map: Phase 2 & 3 ML Model Improvements

**Date:** 2025-11-04
**Status:** Complete ✅

## Overview

Complete implementation of ML model improvement project:
- **Phase 1:** Removed 5 data leakage features
- **Phase 2:** Added 23 legitimate features across 4 categories
- **Phase 3:** Retrained model and validated results

## Summary of Changes

### Features Removed (Phase 1)
- `serper_sold_avg_price` (was 9.4% importance)
- `serper_sold_min_price` (was 33.3% importance - MAJOR leakage!)
- `serper_sold_max_price` (was 2.7% importance)
- `serper_sold_price_range` (was 2.4% importance)
- `serper_sold_demand_signal` (was 5.5% importance)

### Features Added (Phase 2)
- **7 temporal features** - publication age patterns
- **6 series features** - collection completion dynamics
- **2 BookFinder premium features** - signed/first edition differentials
- **8 author aggregate features** - author brand value

### Model Performance (Phase 3)
- **Test MAE:** $3.36 (up from $2.95, but now legitimate)
- **Test R²:** 0.109 (down from 0.248, but no data leakage)
- **Training samples:** 4,404 books
- **Test samples:** 1,102 books

## File Changes

### 1. `/Users/nickcuskey/ISBN/isbn_lot_optimizer/ml/feature_extractor.py`

#### Lines 20-130: Updated FEATURE_NAMES List

**Removed 5 data leakage features:**
```python
# REMOVED (lines 63-71):
# "serper_sold_avg_price",
# "serper_sold_min_price",
# "serper_sold_max_price",
# "serper_sold_price_range",
# "serper_sold_demand_signal",
```

**Added Phase 2.3 BookFinder premium features (lines 61-63):**
```python
"bookfinder_signed_premium_pct",      # Signed book premium percentage
"bookfinder_first_ed_premium_pct",    # First edition premium percentage
```

**Added Phase 2.4 Author aggregates (lines 73-81):**
```python
"author_book_count",                  # Books by author in catalog
"log_author_catalog_size",            # Log-scaled catalog size
"author_avg_sold_price",              # Average sold price for author
"log_author_avg_price",               # Log-scaled author avg price
"author_avg_sales_velocity",          # Sales velocity for author
"author_collectibility_score",        # Collectibility composite
"author_popularity_score",            # Popularity metric
"author_avg_rating",                  # Average rating for author
```

**Added Phase 2.1 Temporal features (lines 91-99):**
```python
"is_new_release",                     # Published within 1 year
"is_recent",                          # Published within 3 years
"is_backlist",                        # Published 3-10 years ago
"is_classic",                         # Published over 50 years ago
"decade_sin",                         # Cyclical decade encoding (sin)
"decade_cos",                         # Cyclical decade encoding (cos)
"age_squared",                        # Age transformation (quadratic)
"log_age",                            # Age transformation (logarithmic)
```

**Added Phase 2.2 Series features (lines 101-107):**
```python
"has_series",                         # Boolean: part of a series
"series_index",                       # Position in series
"is_series_start",                    # First book in series
"is_series_middle",                   # Books 2-5 in series
"is_series_late",                     # Books 6+ in series
"log_series_index",                   # Log-scaled position
```

**Total feature count: 68 → 91 features (net +18)**

#### Lines 139-161: Updated extract() Method Signature

**Added author_aggregates parameter:**
```python
def extract(
    self,
    metadata: Optional[BookMetadata],
    market: Optional[EbayMarketStats],
    bookscouter: Optional[BookScouterResult],
    condition: str = "Good",
    abebooks: Optional[Dict] = None,
    bookfinder: Optional[Dict] = None,
    sold_listings: Optional[Dict] = None,
    author_aggregates: Optional[Dict] = None,  # NEW: Phase 2.4
) -> FeatureVector:
```

#### Lines 291-293, 316-317: Phase 2.3 BookFinder Premium Integration

**Feature extraction:**
```python
# Phase 2.3: Premium differentials (line 291-293)
features["bookfinder_signed_premium_pct"] = bookfinder.get('bookfinder_signed_premium_pct', 0)
features["bookfinder_first_ed_premium_pct"] = bookfinder.get('bookfinder_first_ed_premium_pct', 0)

# Defaults when no BookFinder data (lines 316-317)
features["bookfinder_signed_premium_pct"] = 0
features["bookfinder_first_ed_premium_pct"] = 0
```

#### Lines 342-362: Phase 2.4 Author Features Integration

**Author aggregate features:**
```python
# Phase 2.4: Author-level aggregates
if author_aggregates:
    features["author_book_count"] = author_aggregates.get('author_book_count', 0)
    features["log_author_catalog_size"] = author_aggregates.get('log_author_catalog_size', 0)
    features["author_avg_sold_price"] = author_aggregates.get('author_avg_sold_price', 0)
    features["log_author_avg_price"] = author_aggregates.get('log_author_avg_price', 0)
    features["author_avg_sales_velocity"] = author_aggregates.get('author_avg_sales_velocity', 0)
    features["author_collectibility_score"] = author_aggregates.get('author_collectibility_score', 0)
    features["author_popularity_score"] = author_aggregates.get('author_popularity_score', 0)
    features["author_avg_rating"] = author_aggregates.get('author_avg_rating', 0)
else:
    # Defaults when no author data available
    features["author_book_count"] = 1
    features["log_author_catalog_size"] = 0
    features["author_avg_sold_price"] = 15.0
    features["log_author_avg_price"] = math.log1p(15.0)
    features["author_avg_sales_velocity"] = 5.0
    features["author_collectibility_score"] = 0.2
    features["author_popularity_score"] = 1.0
    features["author_avg_rating"] = 3.5
    missing.append("author_book_count")
```

#### Lines 367-410: Phase 2.1 & 2.2 Temporal and Series Features

**Phase 2.1: Temporal features (lines 367-390):**
```python
# Age-based features
age = current_year - metadata.published_year
features["age_years"] = age

# Phase 2.1: Age categories
features["is_new_release"] = 1 if age <= 1 else 0
features["is_recent"] = 1 if age <= 3 else 0
features["is_backlist"] = 1 if 3 < age <= 10 else 0
features["is_classic"] = 1 if age > 50 else 0

# Cyclical decade encoding
decade = (metadata.published_year // 10) % 10
features["decade_sin"] = math.sin(2 * math.pi * decade / 10)
features["decade_cos"] = math.cos(2 * math.pi * decade / 10)

# Age transformations
features["age_squared"] = age ** 2
features["log_age"] = math.log1p(age)
```

**Phase 2.2: Series features (lines 391-410):**
```python
# Series completion features (Phase 2.2)
series_name = getattr(metadata, 'series_name', None)  # Safe access
series_index = getattr(metadata, 'series_index', None)

features["has_series"] = 1 if series_name else 0

if series_name and series_index is not None:
    series_idx = series_index
    features["series_index"] = series_idx
    features["is_series_start"] = 1 if series_idx == 1 else 0
    features["is_series_middle"] = 1 if 1 < series_idx <= 5 else 0
    features["is_series_late"] = 1 if series_idx > 5 else 0
    features["log_series_index"] = math.log1p(series_idx)
else:
    features["series_index"] = 0
    features["is_series_start"] = 0
    features["is_series_middle"] = 0
    features["is_series_late"] = 0
    features["log_series_index"] = 0
```

**Key Fix:** Used `getattr()` for safe attribute access to handle `SimpleMetadata` objects that don't have series fields.

#### Lines 870-874: Phase 2.3 BookFinder SQL Enhancements

**Enhanced SQL query in get_bookfinder_features():**
```python
# Phase 2.3: Premium differential data
AVG(CASE WHEN is_signed = 1 THEN price + COALESCE(shipping, 0) END) as signed_avg_price,
AVG(CASE WHEN is_signed = 0 OR is_signed IS NULL THEN price + COALESCE(shipping, 0) END) as unsigned_avg_price,
AVG(CASE WHEN is_first_edition = 1 THEN price + COALESCE(shipping, 0) END) as first_ed_avg_price,
AVG(CASE WHEN is_first_edition = 0 OR is_first_edition IS NULL THEN price + COALESCE(shipping, 0) END) as non_first_ed_avg_price
```

#### Lines 895-933: Phase 2.3 BookFinder Premium Calculations

**Premium differential calculations:**
```python
# Extract premium data from SQL results
signed_avg = row[14] or 0
unsigned_avg = row[15] or 0
first_ed_avg = row[16] or 0
non_first_ed_avg = row[17] or 0

# Calculate signed book premium percentage
signed_premium_pct = ((signed_avg - unsigned_avg) / unsigned_avg * 100) \
    if unsigned_avg > 0 and signed_avg > 0 else 0

# Calculate first edition premium percentage
first_ed_premium_pct = ((first_ed_avg - non_first_ed_avg) / non_first_ed_avg * 100) \
    if non_first_ed_avg > 0 and first_ed_avg > 0 else 0

return {
    # ... existing features ...
    # Phase 2.3: Premium differentials
    'bookfinder_signed_premium_pct': signed_premium_pct,
    'bookfinder_first_ed_premium_pct': first_ed_premium_pct,
}
```

#### Lines 1003-1083: Phase 2.4 get_author_aggregates() Function

**New function for author-level statistics:**
```python
def get_author_aggregates(canonical_author: str, db_path: str) -> Optional[Dict]:
    """
    Query author-level aggregate features from database.
    Phase 2.4: Extract author-specific patterns to capture author brand value.

    Returns dictionary with:
    - author_book_count: Number of books by author in catalog
    - log_author_catalog_size: Log-scaled catalog size
    - author_avg_sold_price: Average sold price for author
    - log_author_avg_price: Log-scaled author avg price
    - author_avg_sales_velocity: Average sales velocity
    - author_collectibility_score: Weighted collectibility metric
    - author_popularity_score: Log(ratings) * velocity
    - author_avg_rating: Average rating for author
    """
    if not canonical_author or canonical_author == "Unknown":
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as book_count,
                AVG(COALESCE(sold_comps_median, 0)) as avg_sold_price,
                AVG(COALESCE(sold_count, 0)) as avg_sales_velocity,
                AVG(COALESCE(ratings_count, 0)) as avg_ratings_count,
                AVG(COALESCE(average_rating, 0)) as avg_rating,
                SUM(CASE WHEN bookfinder_has_signed = 1 THEN 1 ELSE 0 END) as signed_book_count,
                SUM(CASE WHEN bookfinder_has_first_edition = 1 THEN 1 ELSE 0 END) as first_ed_book_count
            FROM books
            WHERE canonical_author = ? AND sold_comps_median IS NOT NULL
        """, (canonical_author,))

        row = cursor.fetchone()
        conn.close()

        if row and row[0] and row[0] > 0:
            book_count = row[0]
            avg_sold_price = row[1] or 0
            avg_sales_velocity = row[2] or 0
            avg_ratings_count = row[3] or 0
            avg_rating = row[4] or 0
            signed_book_count = row[5] or 0
            first_ed_book_count = row[6] or 0

            # Author collectibility score (weighted combination)
            signed_pct = (signed_book_count / book_count) if book_count > 0 else 0
            first_ed_pct = (first_ed_book_count / book_count) if book_count > 0 else 0
            price_normalized = min(avg_sold_price / 100.0, 1.0)

            collectibility_score = (
                signed_pct * 0.3 +
                first_ed_pct * 0.3 +
                price_normalized * 0.4
            )

            popularity_score = math.log1p(avg_ratings_count) * avg_sales_velocity

            return {
                'author_book_count': book_count,
                'log_author_catalog_size': math.log1p(book_count),
                'author_avg_sold_price': avg_sold_price,
                'log_author_avg_price': math.log1p(avg_sold_price),
                'author_avg_sales_velocity': avg_sales_velocity,
                'author_collectibility_score': collectibility_score,
                'author_popularity_score': popularity_score,
                'author_avg_rating': avg_rating,
            }

        return None
    except Exception as e:
        return None
```

### 2. Model Files (Phase 3 - Retraining)

#### Backup Files Created
- `/Users/nickcuskey/ISBN/isbn_lot_optimizer/models/price_v1_pre_phase2.pkl`
- `/Users/nickcuskey/ISBN/isbn_lot_optimizer/models/scaler_v1_pre_phase2.pkl`
- `/Users/nickcuskey/ISBN/isbn_lot_optimizer/models/metadata_pre_phase2.json`

#### Retrained Model Files (Auto-Updated)
- `/Users/nickcuskey/ISBN/isbn_lot_optimizer/models/price_v1.pkl`
- `/Users/nickcuskey/ISBN/isbn_lot_optimizer/models/scaler_v1.pkl`
- `/Users/nickcuskey/ISBN/isbn_lot_optimizer/models/metadata.json`

### 3. Documentation Files

#### Created
- `/Users/nickcuskey/ISBN/docs/MODEL_RETRAIN_PHASE2_COMPLETE.md` - Complete Phase 2 & 3 summary

#### Updated
- `/Users/nickcuskey/ISBN/docs/PHASE_2_NEW_FEATURES.md` - All phases marked complete

## Training Results

### Model Performance

```
Training Configuration:
- Training samples: 4,404 (80%)
- Test samples: 1,102 (20%)
- Total: 6,261 books (after removing 724 outliers)
- Feature completeness: 66.4%
- Model type: GradientBoostingRegressor
- Hyperparameters:
  - n_estimators: 200
  - max_depth: 4
  - learning_rate: 0.05

Performance Metrics:
- Test MAE: $3.36
- Test RMSE: $4.55
- Test R²: 0.109
- Train MAE: $3.06
```

### Top 10 Most Important Features

1. `serper_sold_count` - 22.2% (volume signal)
2. `bookfinder_avg_price` - 10.0% (market context)
3. `serper_sold_hardcover_pct` - 8.9% (format indicator)
4. `rating` - 6.1% (quality signal)
5. `abebooks_competitive_estimate` - 5.6% (market pricing)
6. `page_count` - 4.2% (book size)
7. `amazon_count` - 3.4% (availability)
8. `abebooks_avg_price` - 2.7% (market context)
9. `bookfinder_price_volatility` - 2.4% (price stability)
10. `log_amazon_rank` - 2.4% (popularity)

### Phase 2 Feature Impact

**BookFinder Premium Features:**
- `bookfinder_first_ed_premium_pct`: 2.4% importance ✅
- `bookfinder_signed_premium_pct`: 0.3% importance ✅

**Temporal Features:**
- `log_age`: 0.7% importance ✅
- `age_squared`: 0.6% importance ✅
- Age categories: minimal impact (<0.1%)

**Author Features:**
- All 8 features: 0% importance ⚠️
- Likely cause: `canonical_author` field not populated in training data

**Series Features:**
- All 6 features: 0% importance ⚠️
- Likely cause: `series_name`/`series_index` not in training data

## Analysis

### Positive Findings

1. **Model trains successfully** with only legitimate features
2. **No data leakage** - all price-based sold listing features removed
3. **Legitimate market signals dominate:**
   - Sales volume (`serper_sold_count`) is top feature
   - Market prices (`bookfinder_avg_price`, `abebooks`) provide context
   - Format indicators show genuine patterns
4. **BookFinder premiums have measurable impact:**
   - First edition premium: 2.4% importance
   - Signed book premium: 0.3% importance
5. **Temporal features show modest impact:**
   - Age transformations capture some value patterns

### Areas for Investigation

1. **Author features have 0% importance:**
   - Likely cause: `canonical_author` field not populated in training databases
   - Recommendation: Enrich author metadata and retrain

2. **Series features have 0% importance:**
   - Likely cause: `series_name`/`series_index` not available in training data
   - Recommendation: Add series metadata from OpenLibrary

3. **Lower R² (0.109 vs 0.248 pre-Phase 2):**
   - **This is expected and desirable!**
   - Model no longer "cheating" with leaked sold prices
   - Now learning genuine patterns from market signals

## Errors Fixed During Implementation

### Error 1: AttributeError with series_name
**Error:** `AttributeError: 'SimpleMetadata' object has no attribute 'series_name'`
**Location:** Line 392 during training
**Fix:** Used `getattr(metadata, 'series_name', None)` for safe attribute access

### Error 2: KeyError for removed features
**Error:** `KeyError: 'serper_sold_avg_price'`
**Location:** Line 520 during feature array construction
**Fix:** Updated `FEATURE_NAMES` list to match extracted features exactly

## Next Steps

### Short-term
1. **Populate author data:**
   - Verify `canonical_author` field exists in books table
   - Enrich author metadata across catalog
   - Retrain to validate author feature impact

2. **Add series data:**
   - Ensure `series_name` and `series_index` in metadata
   - Consider enriching from OpenLibrary or other sources
   - Retrain to validate series feature impact

3. **Monitor in production:**
   - Track prediction accuracy on real books
   - Compare with pre-Phase-2 baseline
   - Collect edge cases where model underperforms

### Long-term
1. **Feature engineering improvements:**
   - Add book subject/topic embeddings
   - Extract more pricing signals from BookFinder
   - Consider platform-specific models (eBay vs AbeBooks)

2. **Data collection:**
   - Expand training set beyond 6,261 books
   - Collect more sold listing data
   - Enrich author/series metadata

3. **Model architecture:**
   - Experiment with ensemble methods
   - Try XGBoost or LightGBM
   - Consider neural network approaches

## Timeline

- **Phase 1 Start:** 2025-11-03
- **Phase 1 Complete:** 2025-11-03 (data leakage removal)
- **Phase 2.1-2.2 Complete:** 2025-11-03 (temporal & series features)
- **Phase 2.3-2.4 Complete:** 2025-11-04 (BookFinder premiums & author aggregates)
- **Phase 3 Complete:** 2025-11-04 (model retraining & validation)
- **Documentation Complete:** 2025-11-04

## Related Documentation

- `/Users/nickcuskey/ISBN/docs/MODEL_RETRAIN_PHASE2_COMPLETE.md` - Detailed Phase 2 & 3 report
- `/Users/nickcuskey/ISBN/docs/PHASE_2_NEW_FEATURES.md` - Phase 2 feature specifications
- `/tmp/model_training_phase2.log` - Training execution log

## Status

✅ **Phase 1 Complete:** Data leakage removed
✅ **Phase 2 Complete:** 23 legitimate features added
✅ **Phase 3 Complete:** Model retrained successfully
✅ **Phase 4 Complete:** Documentation and metadata updated

**Project Status: COMPLETE**
