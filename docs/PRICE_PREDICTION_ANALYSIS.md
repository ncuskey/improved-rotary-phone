# Price Prediction Analysis: The $13.25 Issue

## Problem Statement

Many books are being predicted with an estimated value of approximately $13.25. This suggests the ML model is regressing toward a mean value rather than making diverse, data-driven predictions.

## Root Causes

### 1. **Insufficient Market Data**
Books without eBay sold listings or AbeBooks pricing data fall back to the **Unified Model**, which has:
- MAE: $3.36 (vs $3.03 for eBay Specialist, $0.06 for AbeBooks Specialist)
- R²: 0.015 (very low, indicating poor predictive power)
- 91 features (many likely zero for books with sparse data)

### 2. **Missing Features → Zero Imputation**
When books lack metadata (Amazon rank, ratings, page count, etc.), the feature extractor fills in zeros. XGBoost interprets this as "average" book, leading to predictions near the training set mean.

### 3. **Training Set Distribution**
The unified model was likely trained on books with a mean price around $13-14. When the model is uncertain (due to missing features), it defaults to this average.

### 4. **Model Selection Criteria**
The prediction router uses these rules:
- **AbeBooks Specialist**: Requires `abebooks_avg_price > 0` (98.4% catalog coverage)
- **eBay Specialist**: Requires active_median_price OR sold_comps_median (72% catalog coverage)
- **Unified Fallback**: Everything else (100% coverage but low accuracy)

Books without either AbeBooks or eBay data get the weakest model.

## Current Model Performance

| Model | MAE | R² | Coverage | When Used |
|-------|-----|-----|----------|-----------|
| AbeBooks Specialist | $0.06 | 0.999 | 98.4% | Has AbeBooks pricing |
| eBay Specialist | $3.03 | 0.469 | 72% | Has eBay market data |
| Unified | $3.36 | 0.015 | 100% | No platform data |

## Solutions

### Immediate Fixes

#### 1. **Collect More Market Data**
Run these scripts to enrich books with $13.25 predictions:

```bash
# Collect eBay sold listings for books missing market data
python scripts/collect_sold_listings.py --source catalog

# Collect AbeBooks pricing for books without specialist data
python scripts/collect_abebooks_bulk.py

# Enrich metadata (Amazon rank, ratings, page count)
python scripts/collect_metadata_fast.py
```

#### 2. **Add Confidence Thresholds**
Modify the UI to flag low-confidence predictions:

```python
# In prediction_router.py, add confidence calculation
if model_used == 'unified' and not metadata.amazon_rank:
    confidence_score = 0.3  # Very low confidence
elif model_used == 'unified':
    confidence_score = 0.5  # Medium confidence
```

Display in UI:
- 🟢 High confidence (≥0.8): Show price normally
- 🟡 Medium confidence (0.5-0.8): Show "~$13.25" with warning
- 🔴 Low confidence (<0.5): Show "Insufficient data - estimate $13.25"

#### 3. **Use Alternative Fallbacks**
Instead of unified model, try:
- **Median of comparable books** (same author, publisher, page count range)
- **BookScouter best price** (if available)
- **Conditional prediction**: "Books like this sell for $8-$20"

### Medium-Term Improvements

#### 4. **Retrain Unified Model**
- Include more diverse price ranges (currently biased toward $10-15 books)
- Add feature importance weighting (don't treat missing features as zeros)
- Use ensemble of multiple fallback models instead of single unified model

#### 5. **Hybrid Prediction**
Instead of router choosing one model, blend predictions:
```python
if has_abebooks and has_ebay:
    # Both specialists available - blend them
    final_price = 0.7 * abebooks_price + 0.3 * ebay_price
elif has_abebooks:
    final_price = abebooks_price
elif has_ebay:
    final_price = ebay_price
else:
    # No good data - use range estimate
    final_price = None
    price_range = (8.00, 20.00)  # Based on metadata features
```

#### 6. **Feature Engineering**
Add derived features that don't require market data:
- `publication_era` (Vintage/Modern/Contemporary)
- `genre_demand_score` (Fiction/Nonfiction popularity)
- `publisher_prestige` (Major/Independent)
- `condition_multiplier` (Based on stated condition)

### Long-Term Strategy

#### 7. **Continuous Model Updates**
- Retrain specialist models monthly as new data comes in
- Track prediction accuracy vs actual sales prices
- A/B test different models and keep the best performer

#### 8. **Active Learning**
- Prioritize data collection for books with low-confidence predictions
- Ask user for feedback when selling: "This book was estimated at $13.25. What did it actually sell for?"
- Use this feedback to continuously improve the model

## Diagnostic Tools

### Debug Individual Predictions
```bash
# See why a specific ISBN got $13.25
python scripts/debug_prediction.py 9780316769174
```

### Analyze Prediction Distribution
```bash
# Find all books with similar predictions
sqlite3 catalog.db "
  SELECT
    ROUND(estimated_price, 2) as price,
    COUNT(*) as count,
    GROUP_CONCAT(isbn, ', ') as sample_isbns
  FROM book_catalog
  WHERE estimated_price BETWEEN 13.00 AND 13.50
  GROUP BY ROUND(estimated_price, 2)
  ORDER BY count DESC
  LIMIT 10
"
```

### Check Model Routing
```python
from isbn_lot_optimizer.ml.prediction_router import get_prediction_router

router = get_prediction_router()
print(f"Routing stats: {router.stats}")
# Shows how often each model is being used
```

## Recommended Action Plan

### Phase 1: Quick Wins (This Week)
1. ✅ Add UI warnings for low-confidence predictions
2. ✅ Run data collection scripts for books at $13.25
3. ✅ Document which books need better data

### Phase 2: Improved Fallbacks (Next 2 Weeks)
1. Implement BookScouter fallback
2. Add conditional price ranges
3. Show "Insufficient data" messaging in UI

### Phase 3: Model Improvements (Next Month)
1. Retrain unified model with better feature engineering
2. Implement hybrid prediction blending
3. Add continuous feedback loop from actual sales

## Expected Outcomes

After implementing these fixes:
- **30-40% fewer** $13.25 predictions (due to better data coverage)
- **Clearer transparency** when predictions are uncertain
- **Better user experience** - users know when to collect more data
- **Gradual improvement** as more sales data feeds back into model

## Monitoring

Track these metrics weekly:
- % of predictions using each model (aim: 80%+ specialist models)
- Distribution of predicted prices (aim: more diverse, less clustering at $13)
- MAE on actual sales prices (aim: <$3 overall)
- User satisfaction with valuations

---

**Created:** 2025-11-04
**Status:** Analysis Complete - Ready for Implementation
