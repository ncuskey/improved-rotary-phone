# ML Pipeline Code Mapping

## Overview

This document provides a comprehensive map of all machine learning code in the ISBN Lot Optimizer project, organized by functionality and showing relationships between files.

**Last Updated:** November 9, 2025

---

## Training Scripts

### Main Model

**`scripts/train_price_model.py`**
- **Purpose:** Train primary price estimation model for all books
- **Algorithm:** XGBoost with RandomizedSearchCV
- **Features:** 50+ features from metadata, market data, bookscouter
- **Best Practices:** Log transform, GroupKFold, temporal weighting, MAPE
- **Output:**
  - `isbn_lot_optimizer/models/price_v1.pkl`
  - `isbn_lot_optimizer/models/scaler_v1.pkl`
  - `isbn_lot_optimizer/models/metadata.json`
- **Performance:** MAE $3.25, MAPE 44.5%, R² 0.087

### Specialist Models (Stacking Ensemble)

**`scripts/stacking/train_ebay_model.py`**
- **Purpose:** eBay sold comps specialist
- **Algorithm:** XGBoost with hyperparameter tuning
- **Features:** 24 eBay-specific features (sold_median, price spread, demand_score)
- **Output:** `isbn_lot_optimizer/models/stacking/ebay_model.pkl`
- **Performance:** MAE $1.62, MAPE 11.9%, R² 0.788
- **Data:** 11,022 samples

**`scripts/stacking/train_amazon_model.py`**
- **Purpose:** Amazon FBM pricing specialist
- **Algorithm:** GradientBoostingRegressor
- **Features:** 27 Amazon-specific features (amazon_fbm_median, vs_rank)
- **Output:** `isbn_lot_optimizer/models/stacking/amazon_model.pkl`
- **Performance:** MAE $0.18, MAPE 0.8%, R² 0.996 (best model!)
- **Data:** 14,449 samples
- **Note:** amazon_fbm features = 99% of feature importance

**`scripts/stacking/train_abebooks_model.py`**
- **Purpose:** AbeBooks marketplace specialist
- **Algorithm:** XGBoost with hyperparameter tuning
- **Features:** 24 AbeBooks features (has_new, min_price, seller_count)
- **Output:** `isbn_lot_optimizer/models/stacking/abebooks_model.pkl`
- **Performance:** MAE $3.08, MAPE 17.7%, R² 0.276
- **Data:** 1,254 samples

**`scripts/stacking/train_biblio_model.py`**
- **Purpose:** Biblio.com specialist
- **Algorithm:** GradientBoostingRegressor
- **Features:** 24 BookFinder-based features
- **Output:** `isbn_lot_optimizer/models/stacking/biblio_model.pkl`
- **Performance:** MAE $1.42, MAPE 16.9%, R² 0.256
- **Data:** 634 samples

**`scripts/stacking/train_alibris_model.py`**
- **Purpose:** Alibris marketplace specialist
- **Algorithm:** GradientBoostingRegressor
- **Features:** 24 BookFinder-based features
- **Output:** `isbn_lot_optimizer/models/stacking/alibris_model.pkl`
- **Performance:** MAE $2.89, MAPE 27.1%, R² 0.280
- **Data:** 627 samples

**`scripts/stacking/train_zvab_model.py`**
- **Purpose:** ZVAB (German AbeBooks) specialist
- **Algorithm:** GradientBoostingRegressor
- **Features:** 24 BookFinder-based features
- **Output:** `isbn_lot_optimizer/models/stacking/zvab_model.pkl`
- **Performance:** MAE $1.28, MAPE 15.4%, R² 0.371
- **Data:** 527 samples

### Ensemble Models

**`scripts/stacking/generate_oof_predictions.py`**
- **Purpose:** Generate out-of-fold predictions for meta-model training
- **Method:** 5-fold cross-validation for each specialist
- **Features:** Log transform applied to targets
- **Output:**
  - `isbn_lot_optimizer/models/stacking/oof_predictions.pkl`
  - `isbn_lot_optimizer/models/stacking/oof_metadata.json`
- **Data:** 11,134 books with predictions from 6 specialists
- **Coverage:** eBay 100%, Amazon 78%, others 5-20%

**`scripts/stacking/train_meta_model.py`**
- **Purpose:** Train Ridge regression meta-model to combine specialist predictions
- **Algorithm:** Ridge with RidgeCV for alpha selection
- **Features:** 6 specialist predictions (eBay, AbeBooks, Amazon, Biblio, Alibris, Zvab)
- **Best Alpha:** 1000.0 (high regularization)
- **Output:**
  - `isbn_lot_optimizer/models/stacking/meta_model.pkl`
  - `isbn_lot_optimizer/models/stacking/meta_metadata.json`
- **Performance:** MAE $10.20, MAPE 88.2%, R² -0.089
- **Note:** Currently worse than best specialist (eBay); not recommended for production

---

## Utility Modules

**`scripts/stacking/training_utils.py`**
- **Purpose:** Shared utilities implementing ML best practices
- **Functions:**
  - `apply_log_transform()` - Apply log1p to targets
  - `inverse_log_transform()` - Convert predictions back with expm1
  - `group_train_test_split()` - GroupKFold by ISBN wrapper
  - `calculate_temporal_weights()` - Exponential time decay
  - `compute_metrics()` - Calculate MAE, RMSE, R², MAPE
  - `remove_outliers()` - Z-score outlier removal
- **Used By:** All 6 specialist models

**`scripts/stacking/data_loader.py`**
- **Purpose:** Load platform-specific training data from databases
- **Functions:**
  - `load_platform_training_data()` - Returns dict of {platform: (records, targets)}
- **Data Sources:**
  - Unified training DB (in_training=1)
  - Catalog database
  - Amazon FBM pricing
  - BookFinder vendor prices
- **Output:** Platform-filtered datasets for each specialist
- **Used By:** All specialist models, OOF generation, meta-model

**`scripts/stacking/update_all_specialist_models.py`**
- **Purpose:** Automated script to apply best practices to all specialist models
- **Actions:**
  - Update imports to include training_utils
  - Modify extract_features to return ISBNs
  - Replace train_test_split with GroupKFold
  - Add log transform
  - Add MAPE metrics
- **Updated:** Amazon, eBay, Biblio, Alibris, Zvab models
- **Note:** One-time automation script, not part of regular pipeline

---

## Feature Engineering

**`isbn_lot_optimizer/ml/feature_extractor.py`**
- **Purpose:** Extract and engineer features for ML models
- **Key Classes:**
  - `PlatformFeatureExtractor` - Main feature extraction class
- **Methods:**
  - `extract_for_platform()` - Platform-specific feature extraction
  - `get_platform_feature_names()` - Static feature name lists
- **Platforms Supported:**
  - ebay: 24 features (sold comps, active listings, demand)
  - abebooks: 24 features (pricing, competition, condition spread)
  - amazon: 27 features (FBM data, sales rank, book attributes)
  - biblio: 24 features (BookFinder aggregates)
  - alibris: 24 features (BookFinder aggregates)
  - zvab: 24 features (BookFinder aggregates)
- **Feature Types:**
  - Price statistics (min, max, median, avg, spread)
  - Market indicators (seller count, competition, demand)
  - Book attributes (page count, age, rating, categories)
  - Platform scaling (vs rank, platform-specific premiums)
- **Special Features:**
  - `get_bookfinder_features()` - Query BookFinder vendor aggregates from DB

**`isbn_lot_optimizer/ml/edition_premium_estimator.py`**
- **Purpose:** Estimate price premium for first editions
- **Status:** Experimental, not yet integrated into main pipeline
- **Location:** `isbn_lot_optimizer/models/edition_premium/`

---

## Model Loading and Inference

**`isbn_lot_optimizer/ml_estimator.py`**
- **Purpose:** Load trained models and make predictions
- **Key Functions:**
  - `get_ml_estimator()` - Returns MLEstimator instance
  - `MLEstimator.predict()` - Make price predictions
  - `MLEstimator.predict_lot()` - Batch prediction for multiple books
- **Models Loaded:**
  - Main model: `models/price_v1.pkl`
  - Scaler: `models/scaler_v1.pkl`
  - Specialist models: `models/stacking/*_model.pkl` (if available)
- **Used By:**
  - Web API (`isbn_web/api/routes/books.py`)
  - iOS app via API
  - Batch prediction scripts

---

## Data Collection Scripts

### Market Data Collection

**`scripts/collect_bookfinder_prices.py`**
- **Purpose:** Scrape and aggregate vendor prices from BookFinder
- **Storage:** `~/.isbn_lot_optimizer/catalog.db` (bookfinder_vendors table)
- **Features Generated:** Used by BookFinder-based features in small platform models

**`scripts/collect_ebay_active_bulk.py`**
- **Purpose:** Collect active eBay listings for demand signals
- **Storage:** Metadata cache database
- **Features Generated:** ebay_active_count, active_median_price

**`scripts/collect_edition_data*.py`**
- **Purpose:** Collect first edition pricing data
- **Status:** Experimental, for edition premium model
- **Storage:** `isbn_lot_optimizer/data/`

**`scripts/collect_*_bulk.py` (AbeBooks, Alibris, Biblio, Zvab)**
- **Purpose:** Bulk collection of vendor pricing data
- **Status:** Ongoing enrichment (AbeBooks 60%, ZVAB 15%)
- **Storage:** Metadata cache database
- **Note:** Will improve specialist model coverage when complete

---

## Model Artifacts

### Main Model
```
isbn_lot_optimizer/models/
├── price_v1.pkl          # XGBoost model
├── scaler_v1.pkl         # StandardScaler
└── metadata.json         # Training metrics, hyperparameters
```

### Specialist Models
```
isbn_lot_optimizer/models/stacking/
├── ebay_model.pkl        # eBay specialist
├── ebay_scaler.pkl
├── ebay_metadata.json
├── abebooks_model.pkl    # AbeBooks specialist
├── abebooks_scaler.pkl
├── abebooks_metadata.json
├── amazon_model.pkl      # Amazon specialist
├── amazon_scaler.pkl
├── amazon_metadata.json
├── biblio_model.pkl      # Biblio specialist
├── biblio_scaler.pkl
├── biblio_metadata.json
├── alibris_model.pkl     # Alibris specialist
├── alibris_scaler.pkl
├── alibris_metadata.json
├── zvab_model.pkl        # Zvab specialist
├── zvab_scaler.pkl
├── zvab_metadata.json
├── meta_model.pkl        # Meta-model (stacking)
├── meta_metadata.json
├── oof_predictions.pkl   # OOF predictions for meta-model
└── oof_metadata.json
```

---

## Database Schema

### Metadata Cache (`~/.isbn_lot_optimizer/metadata_cache.db`)

**Books Table** (training data source)
- `isbn` - Primary key
- `in_training` - Flag for training set
- `sold_price` - Target variable for training
- `metadata` - JSON blob (page_count, published_year, ratings, etc.)
- `market` - JSON blob (sold_count, active_count, sell_through_rate)
- `bookscouter` - JSON blob (amazon_sales_rank, amazon_count)
- `abebooks` - JSON blob (AbeBooks pricing data)
- `amazon_fbm` - JSON blob (Amazon FBM pricing data)
- `cover_type`, `signed`, `printing` - Book attributes

**BookFinder Vendors Table** (catalog.db)
- `isbn` - Foreign key
- `source` - Vendor name
- `price` - Listed price
- `condition` - Book condition
- `is_first_edition` - Boolean
- `description_length` - Int
- Aggregated by `get_bookfinder_features()`

---

## Production Integration

### Web API

**`isbn_web/api/routes/books.py`**
- **Endpoints:**
  - `GET /api/books/{isbn}` - Get book info with ML price estimate
  - `POST /api/books/batch` - Batch prediction
- **Flow:**
  1. Query metadata_cache.db for book data
  2. Call `get_ml_estimator().predict()`
  3. Return JSON with prediction + confidence

### iOS App

**`LotHelperApp/LotHelper/`**
- **Views:**
  - `BookDetailViewRedesigned.swift` - Displays ML price estimate
  - API calls to web backend for predictions
- **Features:**
  - Shows predicted price range
  - Confidence indicators
  - Platform-specific estimates (when available)

---

## Testing and Validation

### Model Retraining Commands

```bash
# Main model
python3 scripts/train_price_model.py --no-oversample

# Specialist models (run individually)
python3 scripts/stacking/train_ebay_model.py
python3 scripts/stacking/train_amazon_model.py
python3 scripts/stacking/train_abebooks_model.py
python3 scripts/stacking/train_biblio_model.py
python3 scripts/stacking/train_alibris_model.py
python3 scripts/stacking/train_zvab_model.py

# Meta-model pipeline
python3 scripts/stacking/generate_oof_predictions.py
python3 scripts/stacking/train_meta_model.py
```

### Check Model Metadata

```bash
# Main model
cat isbn_lot_optimizer/models/metadata.json | python3 -m json.tool

# Specialist models
cat isbn_lot_optimizer/models/stacking/ebay_metadata.json | python3 -m json.tool
cat isbn_lot_optimizer/models/stacking/amazon_metadata.json | python3 -m json.tool

# Meta-model
cat isbn_lot_optimizer/models/stacking/meta_metadata.json | python3 -m json.tool
```

---

## Best Practices Checklist

All models now implement these best practices:

- ✅ **Log Transform** - `np.log1p()` on targets, `np.expm1()` on predictions
- ✅ **GroupKFold by ISBN** - No ISBN in both train and test sets
- ✅ **MAPE Metric** - Percentage error for interpretability
- ✅ **Temporal Weighting** - Infrastructure for time decay (needs timestamp extraction)
- ✅ **Feature Scaling** - StandardScaler on all features
- ✅ **Outlier Removal** - Z-score based filtering
- ✅ **Hyperparameter Tuning** - RandomizedSearchCV (XGBoost) or manual config (GradientBoosting)
- ✅ **Cross-Validation** - 3-fold or 5-fold for validation
- ✅ **Metadata Tracking** - All metrics saved to JSON files

---

## Performance Summary

| Model | Use Case | MAE | MAPE | R² | Samples |
|-------|----------|-----|------|-----|---------|
| **Amazon** | FBM pricing | $0.18 | 0.8% | 0.996 | 14,449 |
| **eBay** | Sold comps | $1.62 | 11.9% | 0.788 | 11,022 |
| **Zvab** | German market | $1.28 | 15.4% | 0.371 | 527 |
| **Biblio** | Biblio.com | $1.42 | 16.9% | 0.256 | 634 |
| **AbeBooks** | AbeBooks | $3.08 | 17.7% | 0.276 | 1,254 |
| **Alibris** | Alibris | $2.89 | 27.1% | 0.280 | 627 |
| **Main** | General fallback | $3.25 | 44.5% | 0.087 | 5,115 |
| **Meta** | Ensemble | $10.20 | 88.2% | -0.089 | 11,134 |

**Recommendation:** Use Amazon specialist for FBM, eBay specialist for sold comps, main model for fallback. Skip meta-model currently.

---

## Future Improvements

### High Priority
1. Extract real timestamps for temporal weighting
2. Separate sold vs listing prices in data loader
3. Improve meta-model ensemble strategy
4. Wait for bulk collection to complete (more data)

### Medium Priority
5. Add SHAP analysis for feature importance validation
6. Implement condition segmentation (New vs Used models)
7. Add drift monitoring in production

### Long Term
8. Collect 20K+ training samples for main model
9. Add more sold comps data (not just listings)
10. Explore neural network architectures

---

**Document Version:** 1.0
**Last Updated:** 2025-11-09
**Maintained By:** ML Pipeline Team
