# Fix: estimate_price Endpoint 500 Error

**Date:** 2025-11-05
**Status:** ✅ Fixed

## Problem

The `/api/books/{isbn}/estimate_price` endpoint was returning 500 Internal Server Error when users selected book attributes in the iOS app to see updated price estimates.

### Error Message
```
❌ POST /api/books/9780345485793/estimate_price failed — status: 500
Response body: Internal Server Error
```

## Root Cause

**Feature Mismatch Between ML Model and Feature Extraction Code**

- **ML Model:** Trained on Nov 4 with 53 features
- **Current Code:** Extracting 62 features (added BookFinder, Serper sold data, enhanced market features)

The StandardScaler was expecting 53 features but received 62, causing:
```python
ValueError: X has 62 features, but StandardScaler is expecting 53 features as input.
```

## Solution

### 1. Added Comprehensive Error Handling
**File:** `isbn_web/api/routes/books.py:1228-1450`

Wrapped the entire `estimate_price_with_attributes` function in try-except to capture detailed tracebacks:

```python
try:
    # All estimation logic
    return JSONResponse(content=response.dict())
except Exception as e:
    import traceback
    return JSONResponse(
        status_code=500,
        content={
            "error": f"Failed to estimate price: {str(e)}",
            "traceback": traceback.format_exc()
        }
    )
```

### 2. Retrained ML Model
**Script:** `scripts/train_price_model.py`

Retrained with current 62-feature set:
- **Training samples:** 5,518 books
- **Test MAE:** $3.42
- **Test R²:** 0.094
- **Top features:**
  1. `serper_sold_ebay_pct` (28.98%)
  2. `serper_sold_count` (16.17%)
  3. `serper_sold_hardcover_pct` (6.29%)
  4. `bookfinder_avg_desc_length` (3.78%)
  5. `amazon_lowest_price` (3.59%)

### 3. Fixed iOS Compilation Issue
**File:** `LotHelperApp/LotHelper/VendorsTabView.swift:293`

Changed from:
```swift
let url = BookAPI.baseURL.appendingPathComponent("/api/books/grouped_by_vendor")
```

To:
```swift
guard let url = URL(string: "\(BookAPI.baseURLString)/api/books/grouped_by_vendor") else {
    throw URLError(.badURL)
}
```

The property is named `baseURLString` (String), not `baseURL` (URL).

## Testing

### Endpoint Response (Working)
```json
{
  "estimated_price": 10.26,
  "baseline_price": 10.67,
  "confidence": 0.397,
  "deltas": [
    {"attribute": "is_hardcover", "label": "Hardcover", "delta": -0.35, "enabled": true},
    {"attribute": "is_signed", "label": "Signed/Autographed", "delta": -0.03, "enabled": true},
    {"attribute": "is_first_edition", "label": "First Edition", "delta": -0.02, "enabled": true}
  ],
  "model_version": "v3_xgboost_tuned",
  "profit_scenarios": [
    {"name": "Best Case", "revenue": 10.26, "fees": 1.39, "profit": 8.87, "margin_percent": 86.5},
    {"name": "ML Estimate", "revenue": 10.26, "fees": 1.39, "profit": 8.87, "margin_percent": 86.5}
  ]
}
```

### Features Tested
- ✅ Hardcover/Paperback/Mass Market selection
- ✅ Signed/Autographed selection
- ✅ First Edition selection
- ✅ Attribute delta calculations
- ✅ Profit scenario generation

## Impact

- **Backend:** Dynamic price estimation with user-selected attributes now works
- **iOS App:** Users can select book attributes and see real-time price updates
- **ML Model:** Updated to match current feature set (62 features)

## Files Changed

1. `isbn_web/api/routes/books.py` - Added error handling to estimate_price endpoint
2. `LotHelperApp/LotHelper/VendorsTabView.swift` - Fixed baseURL reference
3. `isbn_lot_optimizer/models/price_v1.pkl` - Retrained model
4. `isbn_lot_optimizer/models/scaler_v1.pkl` - Retrained scaler
5. `isbn_lot_optimizer/models/metadata.json` - Updated metadata

## Prevention

To prevent this in the future:
1. **Feature Count Validation:** Add check in model loading to validate feature count matches
2. **CI/CD Test:** Add test that verifies model can process current feature extraction
3. **Version Tracking:** Track feature schema version alongside model version

## Related Issues

- Initial testing revealed route ordering issue with `/grouped_by_vendor` endpoint (fixed separately)
- iOS compilation issue with `baseURL` vs `baseURLString` (fixed in this PR)
