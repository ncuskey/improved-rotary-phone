# Lot Specialist Model

## Overview

The Lot Specialist Model predicts total price for book lots (multi-book sets) based on lot characteristics, series information, and market patterns. It achieves exceptional accuracy with Test MAE of $1.67 and R² of 0.988.

## Model Performance

- **Test MAE**: $1.67 (predicts within $1.67 on average)
- **Test R²**: 0.988 (explains 98.8% of price variance)
- **Test RMSE**: $4.94
- **Training Data**: 2,432 lots from series_lot_comps table

## Key Features

The model uses 10 features ranked by importance:

1. **lot_size** (65.3%) - Number of books in the lot
2. **price_per_book** (27.1%) - Individual book value
3. **inferred_series_size** (2.3%) - Total books in series
4. **condition_score** (1.5%) - Overall condition rating
5. **is_sold** (1.4%) - Sold vs active listing
6. **completion_pct** (1.2%) - Percentage of complete series
7. **complete_set_premium** (0.5%) - Interaction term for marketed complete sets
8. **is_complete_set** (0.4%) - Whether marketed as complete
9. **series_id** (0.2%) - Series popularity proxy
10. **Lot size bins** (0.1%) - Categorical size indicators

## Completion Percentage Insights

Analysis of 567 lots revealed a **U-shaped pricing curve**:

| Completion % | Avg Price/Book | Pattern |
|-------------|----------------|---------|
| 0-25% | $6.50 | Small lots priced near singles |
| 25-50% | $5.63 | Bulk discount emerges (13% off) |
| 50-75% | $5.31 | Maximum discount (18% off) |
| 75-90% | $6.09 | Discount shrinks |
| 90-100% | $6.44 | Collector premium (only 1% off) |

### Complete Set Marketing Premium

Among 90%+ complete lots:
- **Not marketed as "complete"**: $5.29/book
- **Marketed as "complete set"**: $7.54/book
- **Premium**: +42% from marketing language alone

## API Endpoint

### `POST /api/lots/estimate_price`

Predict lot price using the trained model.

**Request Body:**
```json
{
  "series_id": 350,
  "series_title": "Six Tudor Queens",
  "lot_size": 6,
  "is_complete_set": true,
  "condition": "https://schema.org/UsedCondition",
  "is_sold": false,
  "price_per_book": 0.0,
  "inferred_series_size": 6
}
```

**Response:**
```json
{
  "estimated_price": 67.50,
  "price_per_book": 11.25,
  "completion_pct": 1.0,
  "is_near_complete": true,
  "model_version": "2025-11-08T...",
  "model_mae": 1.67,
  "model_r2": 0.988
}
```

## Training

### Training Script
```bash
./scripts/ml_train scripts/stacking/train_lot_model.py
```

### Model Artifacts
- **Model**: `isbn_lot_optimizer/models/stacking/lot_model.pkl`
- **Scaler**: `isbn_lot_optimizer/models/stacking/lot_scaler.pkl`
- **Metadata**: `isbn_lot_optimizer/models/stacking/lot_metadata.json`

### Hyperparameters
- **Model**: XGBRegressor
- **n_estimators**: 500
- **max_depth**: 4
- **learning_rate**: 0.1
- **subsample**: 0.6
- **colsample_bytree**: 1.0
- **min_child_weight**: 2
- **gamma**: 0.4
- **reg_alpha**: 0
- **reg_lambda**: 1

## Data Sources

The model trains on data from `metadata_cache.db`:
- **Table**: `series_lot_comps`
- **Requirements**:
  - Valid pricing data (price >= $2.00)
  - Reasonable lot sizes (1-50 books)
  - Both sold and active listings

## Buyer Behavior Patterns

The U-shaped pricing curve reveals two distinct buyer segments:

1. **Bulk Buyers (25-75% complete)**
   - Seeking volume discounts
   - Higher sell-through rates (6.5-8.2%)
   - Maximum discount at 50-75% completion

2. **Collectors (90-100% complete)**
   - Willing to pay premiums for completeness
   - Lower sell-through rates (5.4%)
   - Value "complete set" marketing significantly

## Usage Example

```python
import requests

# Estimate price for 6-book complete set
response = requests.post(
    "http://localhost:8000/api/lots/estimate_price",
    json={
        "series_id": 350,
        "series_title": "Six Tudor Queens",
        "lot_size": 6,
        "is_complete_set": True,
        "condition": "https://schema.org/UsedCondition",
        "inferred_series_size": 6
    }
)

result = response.json()
print(f"Estimated Price: ${result['estimated_price']}")
print(f"Price Per Book: ${result['price_per_book']}")
print(f"Completion: {result['completion_pct']*100:.1f}%")
```

## Model Evolution

### Version 1 (Basic Features)
- 10 features
- Test MAE: $1.67
- Test R²: 0.988

### Version 2 (With Completion Features) - Not Used
- 15 features including completion_pct, completion_pct_squared
- Test MAE: $1.93 (worse)
- Test R²: 0.950 (worse)
- **Conclusion**: Simpler model generalizes better

## Future Improvements

1. **Incorporate Individual ISBN Prices**: When available, sum individual book predictions
2. **Series Popularity Metrics**: Better proxy than series_id
3. **Market Trends**: Temporal features for trending series
4. **Condition Distribution**: Account for varied conditions within lots
5. **Shipping Costs**: Factor in lot weight/size for profit calculations

## Related Models

- **eBay Specialist**: Predicts single-book eBay prices (Test MAE: $3.61)
- **Amazon Specialist**: Predicts Amazon prices (Test MAE: $19.36)
- **Platform Specialists**: AbeBooks, Alibris, Biblio, Zvab
