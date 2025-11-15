# Edition Premium Calibration Model - Integration Complete

## Overview

Successfully trained and integrated an ML model to predict first edition price premiums using BookFinder paired edition data. This solves the issue where the main ML model (trained on sold_listings) was predicting negative premiums for first editions due to confounding factors.

## Model Performance

- **Training Data**: 478 ISBNs with paired first/non-first edition offers from BookFinder
- **Test MAE**: 1.07% (predictions within ~1% of actual premium)
- **Test RMSE**: 2.12%
- **Test R²**: 0.9987 (explains 99.87% of variance in edition premiums)

## Model Architecture

- **Algorithm**: XGBoost Regressor
- **Features**: 21 total
  - 14 BookFinder pricing statistics (price ratios, differences, ranges, offer counts)
  - 7 book metadata features (publication year, age, page count, binding)
- **Top 2 Features** (account for ~98% of predictive power):
  1. `price_ratio` (49.4%) - Ratio of first to non-first edition prices
  2. `price_difference` (48.5%) - Absolute price difference

## Files Created/Modified

### New Files

1. `scripts/train_edition_premium_model.py` (562 lines)
   - Training script for edition premium calibration model
   - Loads paired edition data from BookFinder
   - Extracts pricing statistics + metadata features
   - Trains XGBoost model with hyperparameter tuning

2. `isbn_lot_optimizer/ml/edition_premium_estimator.py` (277 lines)
   - Production estimator class for edition premium predictions
   - Loads trained model and makes predictions
   - Extracts features from BookFinder data on-the-fly
   - Provides fallback to 3% heuristic if model unavailable

3. `/tmp/test_edition_premium.py`
   - Test script to verify model loading and prediction

### Modified Files

1. `isbn_web/api/routes/books.py`
   - Lines 1369-1387: Integrated edition premium estimator
   - Replaced hardcoded 3% boost with ML calibration
   - Falls back to 3% if model not available

## Model Artifacts

Saved to: `isbn_lot_optimizer/models/edition_premium/`
- `model_v1.pkl` - Trained XGBoost model
- `scaler_v1.pkl` - StandardScaler for feature normalization
- `metadata_v1.json` - Model version, hyperparameters, performance metrics

## How It Works

### Training Process

1. Query BookFinder for ISBNs with both first and non-first edition offers (2+ of each)
2. Calculate actual premium percentage: `((first_avg - non_first_avg) / non_first_avg) * 100`
3. Extract features combining BookFinder pricing stats with metadata
4. Train XGBoost model to predict premium percentage
5. Save model artifacts

### Prediction Process

1. When user selects "First Edition" attribute in price estimation
2. API calls `edition_estimator.estimate_premium(isbn, baseline_price)`
3. Estimator queries BookFinder data for this ISBN
4. Extracts 21 features (pricing stats + metadata)
5. Model predicts premium percentage (e.g., +15%)
6. Convert to dollars: `baseline_price * (premium_pct / 100)`
7. Apply sanity checks: clamp between -10% and +100%
8. Return premium in dollars

### Fallback Behavior

If model unavailable or no BookFinder data:
- Falls back to conservative 3% heuristic
- Returns explanation of why fallback was used

## Python Version Requirement

**Important**: XGBoost model requires Python 3.11 or earlier due to architecture compatibility issues with Python 3.13.

Error with Python 3.13:
```
Library not loaded: @rpath/libomp.dylib
(have 'arm64', need 'x86_64')
```

**Solution**: Ensure API server runs with Python 3.11:
```bash
./.venv/bin/python3.11 -m uvicorn isbn_web.main:app
```

## Integration Testing

Test the integration:

```python
# Test with an ISBN that has BookFinder data
curl -X POST http://localhost:8000/api/books/9780060002480/estimate_price \
  -H "Content-Type: application/json" \
  -d '{"condition":"Good","is_first_edition":true}'
```

Expected response should show:
- `baseline_price`: Price without first edition
- `deltas`: Array with first edition delta using ML calibration
- `final_price`: baseline + deltas

## Training Data Statistics

- **Average premium**: 26.2%
- **Median premium**: 8.7%
- **Premium range**: -49.2% to +305.8%

The wide range shows that edition premiums vary significantly by book. Some first editions sell for less (negative premium), while collectible first editions can command 3x premiums.

## Next Steps

1. **Monitoring**: Track edition premium predictions vs actual sales
2. **Retraining**: Collect more BookFinder data and retrain quarterly
3. **Feature Engineering**: Explore additional features (author popularity, genre, awards)
4. **Python 3.13 Fix**: Wait for xgboost update or install compatible libomp.dylib

## Background Context

The main ML price estimation model (trained on eBay sold_listings) was consistently predicting negative premiums for first editions (-$0.99) despite:
- Loading only true 1st editions (not anniversary/collector's editions)
- Adding negative examples (2nd/3rd/later editions)
- High feature importance (3rd place, 7.85%)

**Root Cause**: 2nd editions in sold_listings data sold for MORE than 1st editions on average ($31.22 vs $30.84), likely due to:
- Condition differences (2nd editions in better condition)
- Selection bias (different books represented in each group)
- Confounding factors (listings with first editions might have other issues)

**Solution**: Train specialized model on BookFinder data which provides within-ISBN comparisons (same book, different editions, comparable conditions), eliminating confounding factors.

## Training Log

Final training run:
```
======================================================================
Edition Premium Calibration Model Training
======================================================================

1. Loading paired edition data from BookFinder...
Loaded 478 ISBNs with paired edition data and metadata
  Average premium: 26.2%
  Median premium: 8.7%
  Premium range: -49.2% to 305.8%

2. Extracting features...
  Extracted features for 478/478 ISBNs

3. Building feature matrix...
   Feature matrix: (478, 21)
   Target range: -49.2% to 305.8%
  Using all 21 features for edition premium model

2. Training edition premium model...
   Train: 382 samples
   Test:  96 samples

   Best hyperparameters:
     subsample            = 0.9
     reg_lambda           = 1
     reg_alpha            = 0
     n_estimators         = 150
     min_child_weight     = 1
     max_depth            = 3
     learning_rate        = 0.05
     gamma                = 0.1
     colsample_bytree     = 0.9
     Best CV MAE: 1.60%

Training Results:
  Train MAE: 0.45%
  Test MAE:  1.07%
  Train RMSE: 0.71%
  Test RMSE:  2.12%
  Test R²:    0.999

======================================================================
Training Complete!
======================================================================
Model version: v1_edition_premium
Test MAE: 1.07%
Test RMSE: 2.12%
Test R²: 0.999

Model ready for integration into price estimation endpoint.
```

## Date

Trained and integrated: 2025-11-05
